"""Guard: package layers only import inward.

See ARCHITECTURE.md. Imports are read statically with ``ast``, so imports
inside functions or ``if TYPE_CHECKING:`` blocks count too.

If this fails: move the code to the layer it belongs in, or add a port in
``application/ports.py`` rather than importing the adapter directly.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_PACKAGE = Path(__file__).resolve().parent.parent / "finance_redactor"

# Which finance_redactor subpackages each layer may import from.
_ALLOWED = {
    "domain": {"domain"},
    "application": {"application", "domain"},
    "infrastructure": {"infrastructure", "domain", "config"},
    "presentation": {"presentation", "application", "domain", "config"},
}


def _imports(path: Path) -> list[tuple[int, str]]:
    """Return ``(line, dotted module)`` for every import in ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            # `from finance_redactor import config` names the submodule in
            # the alias, not in node.module.
            if node.module == "finance_redactor":
                found.extend(
                    (node.lineno, f"finance_redactor.{alias.name}")
                    for alias in node.names
                )
            else:
                found.append((node.lineno, node.module))
    return found


def _modules(layer: str) -> list[Path]:
    return sorted((_PACKAGE / layer).rglob("*.py"))


@pytest.mark.parametrize("layer", sorted(_ALLOWED))
def test_layer_imports_point_inward(layer):
    assert _modules(layer), f"no modules found for layer {layer!r}"
    violations = []
    for path in _modules(layer):
        for line, module in _imports(path):
            parts = module.split(".")
            if parts[0] != "finance_redactor" or len(parts) < 2:
                continue
            if parts[1] not in _ALLOWED[layer]:
                rel = path.relative_to(_PACKAGE.parent).as_posix()
                violations.append(f"{rel}:{line} imports {module}")
    assert not violations, "\n".join(violations)


def test_domain_imports_only_the_standard_library():
    violations = []
    for path in _modules("domain"):
        for line, module in _imports(path):
            top = module.split(".")[0]
            if top not in sys.stdlib_module_names and top != "finance_redactor":
                rel = path.relative_to(_PACKAGE.parent).as_posix()
                violations.append(f"{rel}:{line} imports {module}")
    assert not violations, "\n".join(violations)
