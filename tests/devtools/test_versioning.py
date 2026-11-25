from __future__ import annotations

import pytest
from packaging.version import Version

from yomil.devtools.versioning import (
    Versions,
    bumped,
    dev_versions,
    latest_release,
    release_versions,
)

SHA = "abc1234def5678abc1234def5678abc1234def56"


def test_latest_release_picks_highest_numerically() -> None:
    tags = ["v1.9.0", "v1.10.0", "v1.2.3", "v2.0.0-rc1", "vnext", "1.11.0", "v01.0.0"]
    assert latest_release(tags) == (1, 10, 0)


def test_latest_release_defaults_to_zero() -> None:
    assert latest_release([]) == (0, 0, 0)


@pytest.mark.parametrize(
    ("bump", "expected"),
    [("patch", (1, 3, 1)), ("minor", (1, 4, 0)), ("major", (2, 0, 0))],
)
def test_bumped(bump: str, expected: tuple[int, int, int]) -> None:
    assert bumped((1, 3, 0), bump) == expected  # type: ignore[arg-type]


def test_dev_versions() -> None:
    assert dev_versions((1, 3, 0), 118, SHA) == Versions("1.3.1.dev118+abc1234", "1.3.0.118")
    assert dev_versions((0, 0, 0), 5, SHA[:7]) == Versions("0.0.1.dev5+abc1234", "0.0.0.5")


def test_release_versions() -> None:
    assert release_versions((1, 3, 0), "minor") == Versions("1.4.0", "1.4.0.0", "v1.4.0")
    assert release_versions((0, 0, 0), "major") == Versions("1.0.0", "1.0.0.0", "v1.0.0")


@pytest.mark.parametrize("bump", ["patch", "minor", "major"])
def test_dev_builds_sort_between_releases(bump: str) -> None:
    last = (1, 3, 0)
    nxt = release_versions(last, bump)  # type: ignore[arg-type]
    devs = [dev_versions(last, run, SHA) for run in (1, 2, 118)]
    ordered = [Version("1.3.0"), *(Version(d.version) for d in devs), Version(nxt.version)]
    assert ordered == sorted(ordered)
    files = ["1.3.0.0", *(d.file_version for d in devs), nxt.file_version]
    as_tuples = [tuple(map(int, f.split("."))) for f in files]
    assert as_tuples == sorted(as_tuples)


def test_dev_versions_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="hash"):
        dev_versions((1, 0, 0), 1, "main")
    with pytest.raises(ValueError, match="positive"):
        dev_versions((1, 0, 0), 0, SHA)
    with pytest.raises(ValueError, match="65535"):
        dev_versions((1, 0, 0), 65536, SHA)
