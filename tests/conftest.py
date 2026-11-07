"""Load the plugin folder as a package named `raiseplug` ("raise" is a Python keyword),
so the plugin's relative imports work the same way they do under Hermes."""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if "raiseplug" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "raiseplug", os.path.join(ROOT, "__init__.py"), submodule_search_locations=[ROOT])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["raiseplug"] = mod
    spec.loader.exec_module(mod)

from raiseplug import store  # noqa: E402


def fresh():
    return store.connect(":memory:")
