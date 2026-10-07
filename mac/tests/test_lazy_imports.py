from __future__ import annotations

import sys

import pytest

from s2t.core.lazy_imports import (
    _LazyModule,
    defer_unused_imports,
    disable_unused_transformers_integrations,
)


@pytest.fixture
def clean_module():
    """Yield a module name that is absent from sys.modules, and restore after."""
    name = "json"  # stdlib, cheap, certain to exist
    saved = sys.modules.pop(name, None)
    try:
        yield name
    finally:
        if saved is not None:
            sys.modules[name] = saved
        else:
            sys.modules.pop(name, None)


def test_proxy_installed_without_importing(clean_module):
    defer_unused_imports((clean_module,))
    assert isinstance(sys.modules[clean_module], _LazyModule)


def test_proxy_resolves_on_attribute_access(clean_module):
    defer_unused_imports((clean_module,))
    # Touching a real attribute swaps the proxy for the genuine module.
    assert sys.modules[clean_module].dumps({"a": 1}) == '{"a": 1}'
    assert not isinstance(sys.modules[clean_module], _LazyModule)


def test_proxy_has_a_real_spec(clean_module):
    # transformers probes optional deps with find_spec(); a None spec raises.
    import importlib.util

    defer_unused_imports((clean_module,))
    assert importlib.util.find_spec(clean_module) is not None
    assert isinstance(sys.modules[clean_module], _LazyModule)  # probe stayed lazy


def test_proxy_does_not_resolve_on_dunder_access(clean_module):
    defer_unused_imports((clean_module,))
    with pytest.raises(AttributeError):
        sys.modules[clean_module].__all__
    assert isinstance(sys.modules[clean_module], _LazyModule)


def test_already_imported_module_is_left_alone():
    assert "sys" in sys.modules
    defer_unused_imports(("sys",))
    assert sys.modules["sys"] is sys


class _FakeImportUtils:
    _sklearn_available = True
    _scipy_available = True


def test_clears_known_integration_flags(monkeypatch):
    fake = _FakeImportUtils()
    monkeypatch.setattr("transformers.utils.import_utils", fake, raising=False)
    assert disable_unused_transformers_integrations(("sklearn", "scipy")) == ["sklearn", "scipy"]
    assert fake._sklearn_available is False
    assert fake._scipy_available is False


def test_already_false_flag_is_not_reported(monkeypatch):
    fake = _FakeImportUtils()
    fake._scipy_available = False
    monkeypatch.setattr("transformers.utils.import_utils", fake, raising=False)
    assert disable_unused_transformers_integrations(("sklearn", "scipy")) == ["sklearn"]


def test_unknown_flag_is_tolerated(monkeypatch):
    # A transformers version that renames or drops a flag must not break startup.
    fake = _FakeImportUtils()
    monkeypatch.setattr("transformers.utils.import_utils", fake, raising=False)
    assert disable_unused_transformers_integrations(("not_a_real_dep",)) == []


def test_failed_real_import_leaves_proxy_in_place():
    name = "s2t_definitely_not_installed"
    defer_unused_imports((name,))
    with pytest.raises(ModuleNotFoundError):
        sys.modules[name].anything
    try:
        # The proxy must survive, not leave a hole in sys.modules.
        assert isinstance(sys.modules[name], _LazyModule)
    finally:
        sys.modules.pop(name, None)
