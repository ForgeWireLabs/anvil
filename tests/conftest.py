"""Shared test safety net.

``AnvilStore()`` / ``Anvil()`` with no explicit root now resolve to the *real*
user-scoped data directory. A test that constructs one and writes would touch
the developer's actual ledger. The autouse fixture below points
``ANVIL_DATA_DIR`` at a per-test temporary directory so nothing can escape,
regardless of what a test forgets to pass.

Tests that specifically exercise the platform default must delete the variable
themselves (``monkeypatch.delenv``), which is explicit and local.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forgewire_anvil.paths import DATA_DIR_ENV_VAR


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(tmp_path / "anvil-data"))
