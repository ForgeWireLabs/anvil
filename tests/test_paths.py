"""Tests for user-scoped data directory resolution.

These pin the precedence contract (explicit > ANVIL_DATA_DIR > platform
default) and the rule that Anvil never resolves to a working-directory-relative
path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from forgewire_anvil.paths import (DATA_DIR_ENV_VAR, default_data_dir,
                                   resolve_data_dir)
from forgewire_anvil.store import AnvilStore


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------


def test_explicit_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATA_DIR_ENV_VAR, "/from/env")
    assert resolve_data_dir("/explicit") == Path("/explicit")


def test_env_wins_over_platform_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATA_DIR_ENV_VAR, "/from/env")
    assert resolve_data_dir() == Path("/from/env")


def test_platform_default_used_when_nothing_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATA_DIR_ENV_VAR, raising=False)
    assert resolve_data_dir() == default_data_dir()


def test_blank_env_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blank value must not resolve to the current directory."""
    monkeypatch.setenv(DATA_DIR_ENV_VAR, "   ")
    monkeypatch.setattr("forgewire_anvil.paths.default_data_dir", lambda: Path("/fallback"))
    assert resolve_data_dir() == Path("/fallback")


def test_blank_explicit_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """AnvilStore(root='') must not silently become the working directory."""
    monkeypatch.setenv(DATA_DIR_ENV_VAR, "/from/env")
    assert resolve_data_dir("") == Path("/from/env")


def test_resolution_is_lazy_not_import_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting the env var after import still takes effect."""
    monkeypatch.setenv(DATA_DIR_ENV_VAR, "/first")
    assert AnvilStore().root == Path("/first")
    monkeypatch.setenv(DATA_DIR_ENV_VAR, "/second")
    assert AnvilStore().root == Path("/second")


# ---------------------------------------------------------------------------
# Platform defaults
# ---------------------------------------------------------------------------


def test_default_is_never_relative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATA_DIR_ENV_VAR, raising=False)
    assert default_data_dir().is_absolute()


def test_default_is_not_under_the_working_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point of the change: no repository-relative ledger."""
    monkeypatch.delenv(DATA_DIR_ENV_VAR, raising=False)
    assert default_data_dir() != Path("data") / "issue_tracker"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows layout")
def test_windows_default_uses_localappdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\test\AppData\Local")
    assert default_data_dir() == Path(r"C:\Users\test\AppData\Local\ForgeWire\Anvil")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows layout")
def test_windows_default_falls_back_without_localappdata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path(r"C:\Users\test")))
    assert default_data_dir() == Path(r"C:\Users\test\AppData\Local\ForgeWire\Anvil")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS layout")
def test_macos_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/Users/test")))
    assert default_data_dir() == Path(
        "/Users/test/Library/Application Support/ForgeWire/Anvil"
    )


@pytest.mark.skipif(sys.platform in ("win32", "darwin"), reason="XDG layout")
def test_linux_default_honors_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "/custom/share")
    assert default_data_dir() == Path("/custom/share/forgewire/anvil")


@pytest.mark.skipif(sys.platform in ("win32", "darwin"), reason="XDG layout")
def test_linux_default_without_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/home/test")))
    assert default_data_dir() == Path("/home/test/.local/share/forgewire/anvil")
