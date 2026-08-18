from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any

from .models import DependencyReport


class DependencyAnalyzer:
    """Conservatively slice field reads that influence returns and return branches."""

    def analyze(self, function: Any) -> DependencyReport:
        try:
            source = textwrap.dedent(inspect.getsource(function))
            module = ast.parse(source)
        except (OSError, TypeError, IndentationError, SyntaxError):
            return DependencyReport(paths=())

        function_node = next(
            (
                node
                for node in ast.walk(module)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ),
            None,
        )
        if function_node is None:
            return DependencyReport(paths=())

        assignments: dict[str, ast.AST] = {}
        resource_roots: set[str] = set()
        for argument in function_node.args.args:
            if argument.arg not in {"self", "cls"} and not argument.arg.endswith("_id"):
                resource_roots.add(argument.arg)
        for node in ast.walk(function_node):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        assignments[target.id] = value
                        if isinstance(value, (ast.Call, ast.Await)):
                            resource_roots.add(target.id)

        return_dependencies: set[str] = set()
        branch_dependencies: set[str] = set()
        for node in ast.walk(function_node):
            if isinstance(node, ast.Return) and node.value is not None:
                return_dependencies.update(
                    self._dependencies(node.value, assignments, resource_roots, set())
                )
            elif isinstance(node, ast.If) and self._contains_return(node):
                branch_dependencies.update(
                    self._dependencies(node.test, assignments, resource_roots, set())
                )

        paths = return_dependencies | branch_dependencies
        return DependencyReport(
            paths=tuple(sorted(paths)),
            return_paths=tuple(sorted(return_dependencies)),
            branch_paths=tuple(sorted(branch_dependencies)),
        )

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
        resource_roots: set[str],
        resolving: set[str],
    ) -> set[str]:
        chain = self._access_chain(node)
        if chain is not None:
            root, parts = chain
            if root in resource_roots and parts:
                return {".".join(parts)}
            if root in assignments and root not in resolving:
                base_dependencies = self._dependencies(
                    assignments[root], assignments, resource_roots, resolving | {root}
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
                resolving | {node.id},
            )

        dependencies: set[str] = set()
        if isinstance(node, ast.Call):
            children = [*node.args, *(keyword.value for keyword in node.keywords)]
        else:
            children = list(ast.iter_child_nodes(node))
        for child in children:
            dependencies.update(
                self._dependencies(child, assignments, resource_roots, resolving)
            )
        return dependencies

    def _access_chain(self, node: ast.AST) -> tuple[str, list[str]] | None:
        if isinstance(node, ast.Name):
            return node.id, []
        if isinstance(node, ast.Attribute):
            parent = self._access_chain(node.value)
            if parent is None:
                return None
            return parent[0], [*parent[1], node.attr]
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if not isinstance(node.slice.value, str):
                return None
            parent = self._access_chain(node.value)
            if parent is None:
                return None
            return parent[0], [*parent[1], node.slice.value]
        return None

