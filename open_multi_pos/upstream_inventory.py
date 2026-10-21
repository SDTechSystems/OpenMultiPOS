"""Static declarations in the pinned dependency, without importing upstream APIs."""

import ast
from pathlib import Path


def inventory(root):
    root = Path(root)
    entries = []
    for file in sorted((root / "xpos").rglob("*.py")):
        if "tests" in file.parts or file.name.startswith("test_"):
            continue
        tree = ast.parse(file.read_text())
        module = ".".join(file.relative_to(root).with_suffix("").parts)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "frappe"
                and decorator.func.attr == "whitelist"
                for decorator in node.decorator_list
            ):
                continue
            parent = next(
                (
                    item
                    for item in tree.body
                    if isinstance(item, ast.ClassDef) and node in item.body
                ),
                None,
            )
            entries.append(
                {
                    "method": module + "." + node.name,
                    "line": node.lineno,
                    "controller": parent.name if parent else None,
                }
            )
    return entries
