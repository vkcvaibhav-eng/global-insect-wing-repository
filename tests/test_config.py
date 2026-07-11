from __future__ import annotations

import pytest

from wing_repository.config import Settings


@pytest.mark.parametrize("value", ["true", "1", "YES", "on"])
def test_demo_bootstrap_truthy_environment(monkeypatch, value: str) -> None:
    monkeypatch.setenv("WBR_AUTO_BOOTSTRAP_DEMO", value)
    assert Settings.from_env().auto_bootstrap_demo


@pytest.mark.parametrize("value", ["false", "0", "NO", "off"])
def test_demo_bootstrap_falsey_environment(monkeypatch, value: str) -> None:
    monkeypatch.setenv("WBR_AUTO_BOOTSTRAP_DEMO", value)
    assert not Settings.from_env().auto_bootstrap_demo


def test_demo_bootstrap_rejects_ambiguous_environment(monkeypatch) -> None:
    monkeypatch.setenv("WBR_AUTO_BOOTSTRAP_DEMO", "sometimes")
    with pytest.raises(ValueError, match="must be true or false"):
        Settings.from_env()
