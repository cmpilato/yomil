"""Work out the version numbers CI stamps into a build, from the repository's release tags.

Releases are the ``vX.Y.Z`` tags. Every build gets two versions:

* the package version (PEP 440), which the app, its log and the installer report, and
* the Windows file version (four numbers, each at most 65535), which Inno Setup needs.

======================  ========================  ==============
Build                   Package version           File version
======================  ========================  ==============
Release                 ``1.3.0``                 ``1.3.0.0``
Dev build after v1.3.0  ``1.3.1.dev118+abc1234``  ``1.3.0.118``
======================  ========================  ==============

Both columns sort correctly: last release < dev builds (by run number) < next release,
whichever part the next release bumps. Before the first release the last one is 0.0.0.

Usage (prints ``key=value`` lines, ready to append to ``$GITHUB_OUTPUT``)::

    python -m yomil.devtools.versioning dev --run 118 --sha abc1234...
    python -m yomil.devtools.versioning release --bump minor
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable

Bump = Literal["patch", "minor", "major"]
Release = tuple[int, int, int]

_TAG = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
_FIELD_MAX = 65535  # each part of a Windows file version is 16 bits
SHA_LENGTH = 7


@dataclass(frozen=True)
class Versions:
    version: str
    file_version: str
    tag: str | None = None  # releases only

    def lines(self) -> list[str]:
        out = [f"version={self.version}", f"file_version={self.file_version}"]
        if self.tag is not None:
            out.append(f"tag={self.tag}")
        return out


def latest_release(tags: Iterable[str]) -> Release:
    """The highest ``vX.Y.Z`` among ``tags`` (others are ignored), or 0.0.0 if none."""
    releases = [m.groups() for m in map(_TAG.fullmatch, tags) if m]
    if not releases:
        return (0, 0, 0)
    return max((int(x), int(y), int(z)) for x, y, z in releases)


def bumped(release: Release, bump: Bump) -> Release:
    x, y, z = release
    if bump == "major":
        return (x + 1, 0, 0)
    if bump == "minor":
        return (x, y + 1, 0)
    return (x, y, z + 1)


def _check_fields(*fields: int) -> None:
    if any(f > _FIELD_MAX for f in fields):
        raise ValueError(f"Windows file versions allow at most {_FIELD_MAX} in each part")


def dev_versions(last: Release, run: int, sha: str) -> Versions:
    if run < 1:
        raise ValueError("the run number must be positive")
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        raise ValueError(f"not a git commit hash: {sha!r}")
    x, y, z = last
    _check_fields(x, y, z, run)
    return Versions(f"{x}.{y}.{z + 1}.dev{run}+{sha[:SHA_LENGTH]}", f"{x}.{y}.{z}.{run}")


def release_versions(last: Release, bump: Bump) -> Versions:
    x, y, z = bumped(last, bump)
    _check_fields(x, y, z)
    return Versions(f"{x}.{y}.{z}", f"{x}.{y}.{z}.0", tag=f"v{x}.{y}.{z}")


def _git_tags(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", "tag", "--list", "v*", *args], capture_output=True, text=True, check=True
    )
    return result.stdout.split()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    dev = commands.add_parser("dev", help="versions for a development build")
    dev.add_argument("--run", type=int, required=True, help="the CI run number")
    dev.add_argument("--sha", required=True, help="the commit being built")
    release = commands.add_parser("release", help="versions for the next release")
    release.add_argument("--bump", choices=["patch", "minor", "major"], required=True)
    args = parser.parse_args(argv)

    last = latest_release(_git_tags())
    try:
        if args.command == "dev":
            versions = dev_versions(last, args.run, args.sha)
        else:
            already = [t for t in _git_tags("--points-at", "HEAD") if _TAG.fullmatch(t)]
            if already:
                raise ValueError(f"this commit is already released as {', '.join(already)}")
            versions = release_versions(last, args.bump)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)  # noqa: T201
        return 1
    print("\n".join(versions.lines()))  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
