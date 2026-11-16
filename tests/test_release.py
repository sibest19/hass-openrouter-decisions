"""Keep release version calculation predictable."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "release", Path(__file__).parents[1] / "scripts/prepare_release.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.mark.parametrize(
    ("tags", "commits", "kind", "expected"),
    [
        ([], ["feat: initial component"], "beta", "0.1.0-beta.1"),
        (["v0.1.0-beta.1"], ["fix: handle errors"], "beta", "0.1.0-beta.2"),
        (["v0.1.0-beta.2"], ["feat: initial component"], "none", "0.1.0"),
        (["v0.1.0"], ["fix: handle errors"], "beta", "0.1.1-beta.1"),
        (["v0.1.0"], ["feat: add a feature"], "none", "0.2.0"),
        (["v0.1.0"], ["feat!: incompatible change"], "none", "1.0.0"),
        (["v0.1.0", "v0.2.0-beta.1"], ["feat: add a feature"], "beta", "0.2.0-beta.2"),
        (["v0.9.0", "v0.10.0"], ["fix: test"], "none", "0.10.1"),
    ],
)
def test_next_version(tags, commits, kind, expected):
    """Handle initial beta, promotion, bumps, and numerical tag ordering."""
    assert (
        release.next_version("0.1.0-beta.1", tags, commits, prerelease=kind) == expected
    )
