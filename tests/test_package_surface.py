from __future__ import annotations

from pathlib import Path

import forgewire_anvil

# Upward imports that would break the standalone package boundary: the package
# owns planning state only and must remain independently importable, so it may
# not reach back into the ForgeWire application tree.
_FORBIDDEN_IMPORT_ROOTS = ("core", "shell", "modules", "forgewire_fabric", "forgewire_core")


def test_package_identity() -> None:
    assert forgewire_anvil.__version__ == "0.1.0a0"
    assert "__version__" in forgewire_anvil.__all__
    # The domain vocabulary, an entity, a serializer, and the protocol are all
    # part of the developer-preview surface.
    for name in ("Issue", "IssueStatus", "issue_to_dict", "IssueTrackerProvider"):
        assert name in forgewire_anvil.__all__
        assert hasattr(forgewire_anvil, name)


def test_public_surface_matches_all() -> None:
    for name in forgewire_anvil.__all__:
        assert hasattr(forgewire_anvil, name), f"__all__ lists {name} but it is not exported"


def test_package_source_has_no_forgewire_application_imports() -> None:
    package_root = Path(forgewire_anvil.__file__).resolve().parent
    for path in sorted(package_root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for root in _FORBIDDEN_IMPORT_ROOTS:
            assert f"from {root}" not in source, f"{path.name} imports from {root}"
            assert f"import {root}" not in source, f"{path.name} imports {root}"
