"""User-scoped data directory resolution for ForgeWire Anvil.

Anvil is local-first, so where it keeps data is part of its contract. The
resolution order is deliberate and explicit:

1. an explicit path passed by the caller;
2. the ``ANVIL_DATA_DIR`` environment variable;
3. a platform-appropriate per-user data directory.

There is intentionally **no** repository-relative default: an operational data
directory that depends on the process's working directory silently scatters
ledgers across checkouts. Paths are resolved lazily (per call, not at import)
so ``ANVIL_DATA_DIR`` can be set by a launcher or a test after import.

The platform locations are hand-rolled rather than taken from a dependency to
keep the package dependency-free.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Environment variable that overrides the platform default.
DATA_DIR_ENV_VAR = "ANVIL_DATA_DIR"

#: Vendor/application names used to build the per-user directory.
_VENDOR = "ForgeWire"
_APP = "Anvil"

#: POSIX uses lowercase path segments by convention.
_POSIX_VENDOR = "forgewire"
_POSIX_APP = "anvil"


def default_data_dir() -> Path:
    """Return the platform-appropriate per-user Anvil data directory.

    - Windows: ``%LOCALAPPDATA%\\ForgeWire\\Anvil``
    - macOS: ``~/Library/Application Support/ForgeWire/Anvil``
    - Other (Linux/BSD): ``$XDG_DATA_HOME/forgewire/anvil``, defaulting to
      ``~/.local/share/forgewire/anvil``

    This only computes a path; it does not create anything on disk.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / _VENDOR / _APP

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _VENDOR / _APP

    xdg = os.environ.get("XDG_DATA_HOME")
    root = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return root / _POSIX_VENDOR / _POSIX_APP


def resolve_data_dir(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the Anvil data directory.

    Precedence: *explicit* argument, then ``ANVIL_DATA_DIR``, then
    :func:`default_data_dir`. An empty or whitespace-only value — whether passed
    in or set in the environment — is ignored rather than resolving to the
    current directory, which would recreate the working-directory-relative
    behavior this function exists to avoid.
    """
    if explicit is not None and str(explicit).strip():
        return Path(explicit)

    from_env = os.environ.get(DATA_DIR_ENV_VAR)
    if from_env and from_env.strip():
        return Path(from_env)

    return default_data_dir()
