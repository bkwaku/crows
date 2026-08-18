from __future__ import annotations

import ast
import inspect
import textwrap
import types
from dataclasses import dataclass
from typing import Any, Union, get_args, get_origin, get_type_hints

from .models import DependencyReport


@dataclass(frozen=True)
class _ClassSource:
    methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
    properties: set[str]


class DependencyAnalyzer:
    """Conservatively slice field reads that influence returns and return branches."""

    def __init__(self, *, max_call_depth: int = 3) -> None:
        self.max_call_depth = max_call_depth

    def analyze(self, function: Any) -> DependencyReport:
        source_context = self._class_source(function)
        function_node = self._function_node(function, source_context)
        if function_node is None:
            return DependencyReport(paths=())

        root_types = self._argument_types(function)
        return_paths, branch_paths = self._analyze_node(
            function_node,
            function=function,
            source_context=source_context,
            inherited_roots=None,
            root_types=root_types,
            depth=0,
            call_stack={function_node.name},
        )
        paths = return_paths | branch_paths
        return DependencyReport(
            paths=tuple(sorted(paths)),
            return_paths=tuple(sorted(return_paths)),
            branch_paths=tuple(sorted(branch_paths)),
        )

    def _analyze_node(
        self,
        function_node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        function: Any,
        source_context: _ClassSource,
        inherited_roots: dict[str, str] | None,
        root_types: dict[str, Any],
        depth: int,
        call_stack: set[str],
    ) -> tuple[set[str], set[str]]:
        assignments: dict[str, ast.AST] = {}
        resource_roots: dict[str, str] = dict(inherited_roots or {})

        for argument in function_node.args.args:
            if (
                argument.arg not in {"self", "cls"}
                and not argument.arg.endswith("_id")
                and argument.arg not in resource_roots
            ):
                resource_roots[argument.arg] = ""

        for node in ast.walk(function_node):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        assignments[target.id] = value
                        if isinstance(value, (ast.Call, ast.Await)):
                            resource_roots.setdefault(target.id, "")
                            inferred = self._infer_call_return_type(value, function)
                        else:
                            inferred = self._expression_type(value, assignments, root_types)
                        if inferred is not None:
                            root_types[target.id] = inferred

        return_dependencies: set[str] = set()
        branch_dependencies: set[str] = set()
        for node in ast.walk(function_node):
            if isinstance(node, ast.Return) and node.value is not None:
                return_dependencies.update(
                    self._dependencies(
                        node.value,
                        assignments,
                        resource_roots,
                        root_types,
                        function,
                        source_context,
                        depth,
                        call_stack,
                        set(),
                    )
                )
            elif isinstance(node, ast.If) and self._contains_return(node):
                branch_dependencies.update(
                    self._dependencies(
                        node.test,
                        assignments,
                        resource_roots,
                        root_types,
                        function,
                        source_context,
                        depth,
                        call_stack,
                        set(),
                    )
                )
        return return_dependencies, branch_dependencies

    @staticmethod
    def _contains_return(node: ast.If) -> bool:
        return any(
            isinstance(child, ast.Return)
            for statement in (*node.body, *node.orelse)
            for child in ast.walk(statement)
        )

    def _dependencies(
        self,
        node: ast.AST,
        assignments: dict[str, ast.AST],
        resource_roots: dict[str, str],
        root_types: dict[str, Any],
        function: Any,
        source_context: _ClassSource,
        depth: int,
        call_stack: set[str],
        resolving: set[str],
    ) -> set[str]:
        property_dependencies = self._property_dependencies(
            node,
            assignments,
            resource_roots,
            root_types,
            function,
            depth,
            call_stack,
        )
        if property_dependencies is not None:
            return property_dependencies

        chain = self._access_chain(node)
        if chain is not None:
            root, parts = chain
            if root in resource_roots:
                prefix = resource_roots[root]
                path = self._join_path(prefix, parts)
                if path:
                    return {path}
            if root in assignments and root not in resolving:
                base_dependencies = self._dependencies(
                    assignments[root],
                    assignments,
                    resource_roots,
                    root_types,
                    function,
                    source_context,
                    depth,
                    call_stack,
                    resolving | {root},
                )
                suffix = ".".join(parts)
                return {
                    f"{base}.{suffix}" if suffix else base
                    for base in base_dependencies
                }

        if isinstance(node, ast.Name) and node.id in assignments and node.id not in resolving:
            return self._dependencies(
                assignments[node.id],
                assignments,
                resource_roots,
                root_types,
                function,
                source_context,
                depth,
                call_stack,
                resolving | {node.id},
            )

        if isinstance(node, ast.Call):
            dependencies = self._call_dependencies(
                node,
                assignments,
                resource_roots,
                root_types,
                function,
                source_context,
                depth,
                call_stack,
                resolving,
            )
            return dependencies

        dependencies: set[str] = set()
        for child in ast.iter_child_nodes(node):
            dependencies.update(
                self._dependencies(
                    child,
                    assignments,
                    resource_roots,
                    root_types,
                    function,
                    source_context,
                    depth,
                    call_stack,
                    resolving,
                )
            )
        return dependencies

    def _call_dependencies(
        self,
        node: ast.Call,
        assignments: dict[str, ast.AST],
        resource_roots: dict[str, str],
        root_types: dict[str, Any],
        function: Any,
        source_context: _ClassSource,
        depth: int,
        call_stack: set[str],
        resolving: set[str],
    ) -> set[str]:
        dependencies: set[str] = set()

        # Follow same-class helper calls first. The helper body tells us which
        # arguments actually matter, so merely passing a broad object to a
        # helper does not force that entire object into the projection.
        helper_name = self._local_helper_name(node.func)
        if (
            helper_name is not None
            and helper_name in source_context.methods
            and helper_name not in call_stack
            and depth < self.max_call_depth
        ):
            helper = source_context.methods[helper_name]
            inherited = self._bind_helper_roots(
                helper,
                node,
                assignments,
                resource_roots,
            )
            helper_types = dict(root_types)
            parameters = [
                arg.arg for arg in helper.args.args if arg.arg not in {"self", "cls"}
            ]
            for parameter, argument in zip(parameters, node.args, strict=False):
                inferred_type = self._expression_type(argument, assignments, root_types)
                if inferred_type is not None:
                    helper_types[parameter] = inferred_type
            for keyword in node.keywords:
                if keyword.arg in parameters:
                    inferred_type = self._expression_type(keyword.value, assignments, root_types)
                    if inferred_type is not None:
                        helper_types[keyword.arg] = inferred_type
            helper_return, helper_branch = self._analyze_node(
                helper,
                function=function,
                source_context=source_context,
                inherited_roots=inherited,
                root_types=helper_types,
                depth=depth + 1,
                call_stack=call_stack | {helper_name},
            )
            dependencies.update(helper_return)
            dependencies.update(helper_branch)
            return dependencies

        # Arguments can themselves be data dependencies when the callee is opaque.
        for child in [*node.args, *(keyword.value for keyword in node.keywords)]:
            dependencies.update(
                self._dependencies(
                    child,
                    assignments,
                    resource_roots,
                    root_types,
                    function,
                    source_context,
                    depth,
                    call_stack,
                    resolving,
                )
            )

        # Common mapping access: user.get("status") -> status.
        mapping_path = self._mapping_get_path(node, assignments, resource_roots)
        if mapping_path:
            dependencies.add(mapping_path)

        # For opaque method calls, retain the receiver. This turns
        # customer.status.lower() into status and subscription.is_active() into
        # subscription rather than silently dropping the call receiver.
        if isinstance(node.func, ast.Attribute):
            receiver = node.func.value
            dependencies.update(
                self._dependencies(
                    receiver,
                    assignments,
                    resource_roots,
                    root_types,
                    function,
                    source_context,
                    depth,
                    call_stack,
                    resolving,
                )
            )
        return dependencies

    def _bind_helper_roots(
        self,
        helper: ast.FunctionDef | ast.AsyncFunctionDef,
        call: ast.Call,
        assignments: dict[str, ast.AST],
        resource_roots: dict[str, str],
    ) -> dict[str, str]:
        parameters = [arg.arg for arg in helper.args.args if arg.arg not in {"self", "cls"}]
        bound: dict[str, str] = {}
        for parameter, argument in zip(parameters, call.args, strict=False):
            path = self._root_path(argument, assignments, resource_roots, set())
            if path is not None:
                bound[parameter] = path
        parameter_names = set(parameters)
        for keyword in call.keywords:
            if keyword.arg in parameter_names:
                path = self._root_path(keyword.value, assignments, resource_roots, set())
                if path is not None:
                    bound[keyword.arg] = path
        return bound

    def _root_path(
        self,
        node: ast.AST,
        assignments: dict[str, ast.AST],
        resource_roots: dict[str, str],
        resolving: set[str],
    ) -> str | None:
        chain = self._access_chain(node)
        if chain is not None:
            root, parts = chain
            if root in resource_roots:
                return self._join_path(resource_roots[root], parts)
            if root in assignments and root not in resolving:
                base = self._root_path(
                    assignments[root], assignments, resource_roots, resolving | {root}
                )
                if base is not None:
                    return self._join_path(base, parts)
        if isinstance(node, ast.Name) and node.id in resource_roots:
            return resource_roots[node.id]
        return None

    def _expression_type(
        self,
        node: ast.AST,
        assignments: dict[str, ast.AST],
        root_types: dict[str, Any],
        resolving: set[str] | None = None,
    ) -> Any | None:
        resolving = resolving or set()
        chain = self._access_chain(node)
        if chain is not None:
            root, parts = chain
            if root in root_types:
                return self._type_at_path(root_types[root], parts)
            if root in assignments and root not in resolving:
                return self._expression_type(
                    assignments[root], assignments, root_types, resolving | {root}
                )
        if isinstance(node, ast.Name) and node.id in root_types:
            return root_types[node.id]
        return None

    def _property_dependencies(
        self,
        node: ast.AST,
        assignments: dict[str, ast.AST],
        resource_roots: dict[str, str],
        root_types: dict[str, Any],
        function: Any,
        depth: int,
        call_stack: set[str],
    ) -> set[str] | None:
        if not isinstance(node, ast.Attribute) or depth >= self.max_call_depth:
            return None
        parent_chain = self._access_chain(node.value)
        if parent_chain is None:
            return None
        root, parent_parts = parent_chain
        root_type = root_types.get(root)
        if root_type is None:
            return None
        parent_type = self._type_at_path(root_type, parent_parts)
        if parent_type is None:
            return None
        descriptor = getattr(parent_type, node.attr, None)
        if not isinstance(descriptor, property) or descriptor.fget is None:
            return None
        try:
            source = textwrap.dedent(inspect.getsource(descriptor.fget))
            module = ast.parse(source)
        except (OSError, TypeError, IndentationError, SyntaxError):
            return None
        property_node = next(
            (n for n in ast.walk(module) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))),
            None,
        )
        if property_node is None or property_node.name in call_stack:
            return None
        prefix = self._join_path(resource_roots.get(root, ""), parent_parts)
        return_paths, branch_paths = self._analyze_node(
            property_node,
            function=descriptor.fget,
            source_context=_ClassSource(methods={property_node.name: property_node}, properties={property_node.name}),
            inherited_roots={"self": prefix},
            root_types={"self": parent_type},
            depth=depth + 1,
            call_stack=call_stack | {property_node.name},
        )
        return return_paths | branch_paths

    def _mapping_get_path(
        self,
        node: ast.Call,
        assignments: dict[str, ast.AST],
        resource_roots: dict[str, str],
    ) -> str | None:
        if not (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            return None
        base = self._root_path(node.func.value, assignments, resource_roots, set())
        if base is None:
            return None
        return self._join_path(base, [node.args[0].value])

    @staticmethod
    def _local_helper_name(func: ast.AST) -> str | None:
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in {"self", "cls"}
        ):
            return func.attr
        return None

    def _function_node(
        self, function: Any, source_context: _ClassSource
    ) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        name = getattr(function, "__name__", None)
        if name in source_context.methods:
            return source_context.methods[name]
        try:
            source = textwrap.dedent(inspect.getsource(function))
            module = ast.parse(source)
        except (OSError, TypeError, IndentationError, SyntaxError):
            return None
        return next(
            (n for n in ast.walk(module) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))),
            None,
        )

    def _class_source(self, function: Any) -> _ClassSource:
        owner = getattr(function, "__self__", None)
        if owner is None or inspect.isclass(owner):
            return _ClassSource(methods={}, properties=set())
        try:
            source = textwrap.dedent(inspect.getsource(owner.__class__))
            module = ast.parse(source)
        except (OSError, TypeError, IndentationError, SyntaxError):
            return _ClassSource(methods={}, properties=set())
        class_node = next((n for n in module.body if isinstance(n, ast.ClassDef)), None)
        if class_node is None:
            return _ClassSource(methods={}, properties=set())
        methods = {
            n.name: n
            for n in class_node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        properties = {
            n.name
            for n in methods.values()
            if any(
                isinstance(d, ast.Name) and d.id == "property"
                for d in n.decorator_list
            )
        }
        return _ClassSource(methods=methods, properties=properties)

    @staticmethod
    def _argument_types(function: Any) -> dict[str, Any]:
        try:
            hints = get_type_hints(function)
        except (NameError, TypeError):
            hints = {}
        return {
            name: annotation
            for name, annotation in hints.items()
            if name != "return" and name not in {"self", "cls"} and not name.endswith("_id")
        }

    @staticmethod
    def _infer_call_return_type(node: ast.AST, function: Any) -> Any | None:
        call = node.value if isinstance(node, ast.Await) else node
        if not isinstance(call, ast.Call):
            return None
        owner = getattr(function, "__self__", None)
        if owner is None:
            return None
        target: Any = owner
        chain: list[str] = []
        current = call.func
        while isinstance(current, ast.Attribute):
            chain.append(current.attr)
            current = current.value
        if not (isinstance(current, ast.Name) and current.id == "self"):
            return None
        try:
            for part in reversed(chain):
                target = getattr(target, part)
            hints = get_type_hints(target)
        except (AttributeError, NameError, TypeError):
            return None
        return hints.get("return")

    @staticmethod
    def _type_at_path(root_type: Any, parts: list[str]) -> Any | None:
        current = root_type
        for part in parts:
            origin = get_origin(current)
            args = get_args(current)
            if origin in (list, tuple, set, frozenset):
                current = args[0] if args else Any
            if get_origin(current) in (Union, types.UnionType):
                candidates = [a for a in get_args(current) if a is not type(None)]
                current = candidates[0] if len(candidates) == 1 else Any
            try:
                hints = get_type_hints(current)
            except (NameError, TypeError):
                return None
            if part not in hints:
                return None
            current = hints[part]
        return current

    @staticmethod
    def _join_path(prefix: str, parts: list[str]) -> str:
        suffix = ".".join(part for part in parts if part)
        if prefix and suffix:
            return f"{prefix}.{suffix}"
        return prefix or suffix

    def _access_chain(self, node: ast.AST) -> tuple[str, list[str]] | None:
        if isinstance(node, ast.Name):
            return node.id, []
        if isinstance(node, ast.Attribute):
            parent = self._access_chain(node.value)
            if parent is None:
                return None
            return parent[0], [*parent[1], node.attr]
        if isinstance(node, ast.Subscript):
            parent = self._access_chain(node.value)
            if parent is None:
                return None
            # String keys are semantic paths. Numeric/slice indices select an
            # element but do not become a projection key; orders[0].status -> orders.status.
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                return parent[0], [*parent[1], node.slice.value]
            if isinstance(node.slice, (ast.Constant, ast.Slice, ast.UnaryOp)):
                return parent
        return None
