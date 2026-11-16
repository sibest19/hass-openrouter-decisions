"""Prepare a human-reviewed release without publishing it."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

MANIFEST = Path("custom_components/openrouter_decisions/manifest.json")


def next_version(current, tags, commits, bump="auto", prerelease="beta"):
    """Calculate a version from stable tags and conventional commits."""
    stable = [
        tag.removeprefix("v") for tag in tags if re.fullmatch(r"v?\d+\.\d+\.\d+", tag)
    ]
    if stable:
        major, minor, patch = max(tuple(map(int, tag.split("."))) for tag in stable)
        if bump == "auto":
            bump = (
                "major"
                if any(
                    re.search(r"^\w+(?:\([^)]*\))?!:|BREAKING CHANGE", msg)
                    for msg in commits
                )
                else "minor"
                if any(re.match(r"feat(?:\([^)]*\))?:", msg) for msg in commits)
                else "patch"
            )
        if bump == "major":
            major, minor, patch = major + 1, 0, 0
        elif bump == "minor":
            minor, patch = minor + 1, 0
        else:
            patch += 1
        base = f"{major}.{minor}.{patch}"
    else:
        base = current.split("-")[0]
    if prerelease == "none":
        return base
    prefix = f"v{base}-beta."
    numbers = [
        int(tag[len(prefix) :])
        for tag in tags
        if tag.startswith(prefix) and tag[len(prefix) :].isdigit()
    ]
    return f"{base}-beta.{max(numbers, default=0) + 1}"


def main():
    """Update versions and output release notes for the workflow."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bump", choices=["auto", "patch", "minor", "major"], default="auto"
    )
    parser.add_argument("--prerelease", choices=["none", "beta"], default="beta")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    tags = subprocess.check_output(["git", "tag", "-l"], text=True).splitlines()
    stable = [tag for tag in tags if re.fullmatch(r"v?\d+\.\d+\.\d+", tag)]
    previous = (
        max(stable, key=lambda tag: tuple(map(int, tag.removeprefix("v").split("."))))
        if stable
        else None
    )
    ref = f"{previous}..HEAD" if previous else "HEAD"
    commits = subprocess.check_output(
        ["git", "log", "--format=%s", ref], text=True
    ).splitlines()
    if not commits:
        raise SystemExit("No changes since the last stable release")
    version = next_version(
        manifest["version"], tags, commits, args.bump, args.prerelease
    )
    if f"v{version}" in tags:
        raise SystemExit("This release tag already exists")
    manifest["version"] = version
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    project = Path("pyproject.toml")
    project.write_text(
        re.sub(
            r'^version = ".*"$',
            f'version = "{version}"',
            project.read_text(),
            count=1,
            flags=re.MULTILINE,
        )
    )
    banner = (
        "Beta release for testing; the upstream Decisions API is in alpha."
        if args.prerelease == "beta"
        else "Review compatibility and the changes below before updating."
    )
    notes = f"{banner}\n\n" + "\n".join(f"- {commit}" for commit in commits) + "\n"
    Path("release_notes.md").write_text(notes)
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a") as stream:
            stream.write(
                f"version={version}\nprerelease={str(args.prerelease == 'beta').lower()}\n"
            )
    print(version)


if __name__ == "__main__":
    main()
