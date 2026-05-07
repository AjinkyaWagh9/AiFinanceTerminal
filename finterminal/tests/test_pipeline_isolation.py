# tests/test_pipeline_isolation.py
import pathlib
import ast
from pathlib import Path

ROOT = pathlib.Path(__file__).parents[1] / "src" / "finterminal" / "market_data"
SRC = Path(__file__).parents[1] / "src" / "finterminal"

def test_market_data_does_not_import_outcomes():
    offenders = []
    for p in ROOT.rglob("*.py"):
        text = p.read_text()
        if "from finterminal.outcomes" in text or "import finterminal.outcomes" in text:
            offenders.append(str(p))
    assert not offenders, f"market_data must not import outcomes: {offenders}"


def _imports(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
    return out

def _all_imports_in(pkg: str) -> set[str]:
    out = set()
    for f in (SRC / pkg).rglob("*.py"):
        out |= _imports(f)
    return out

def test_market_data_does_not_import_features():
    bad = {m for m in _all_imports_in("market_data")
           if m.startswith("finterminal.features")}
    assert bad == set(), f"market_data must not import features: {bad}"

def test_outcomes_does_not_import_features_at_module_level():
    # ledger.py imports inside emit_signal (function-local) to avoid circular import.
    # AST-walk catches ImportFrom at module level only via a top-level filter.
    for f in (SRC / "outcomes").rglob("*.py"):
        tree = ast.parse(f.read_text())
        for node in tree.body:   # top-level only
            if isinstance(node, ast.ImportFrom) and node.module \
                    and node.module.startswith("finterminal.features"):
                raise AssertionError(f"{f} imports features at module level")

def test_news_does_not_import_features():
    bad = {m for m in _all_imports_in("news")
           if m.startswith("finterminal.features")}
    assert bad == set(), f"news must not import features: {bad}"
