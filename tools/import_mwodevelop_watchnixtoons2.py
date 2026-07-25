#!/usr/bin/env python3
"""Rebuild the isolated mwoDevelop add-on from an immutable upstream ZIP."""

import argparse
import hashlib
import json
import shutil
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).parents[1]
MWO = ROOT / "mwodevelop"
TARGET = MWO / "plugin.video.watchnixtoons2.mwodevelop"
STATE = MWO / "upstream.json"
TRANSFORM = MWO / "transforms" / "addon_identity.json"
SERIES = MWO / "patches" / "series"
MAX_FILES = 4096
MAX_UNCOMPRESSED = 256 * 1024 * 1024


def _git_bytes(commit, path):
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", "%s:%s" % (commit, path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def _ensure_commit(repository, commit):
    exists = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", "%s^{commit}" % commit],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if exists.returncode == 0:
        return
    subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "fetch",
            "--no-tags",
            repository.rstrip("/") + ".git",
            commit,
        ],
        check=True,
    )


def _extract_safe(payload, destination, expected_root):
    total = 0
    count = 0
    with tempfile.NamedTemporaryFile(suffix=".zip") as handle:
        handle.write(payload)
        handle.flush()
        with zipfile.ZipFile(handle.name) as archive:
            for item in archive.infolist():
                path = PurePosixPath(item.filename.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("unsafe archive path: %s" % path)
                if not path.parts or path.parts[0] != expected_root:
                    raise ValueError("unexpected archive root: %s" % path)
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ValueError("archive symlink is forbidden: %s" % path)
                count += 1
                total += item.file_size
                if count > MAX_FILES or total > MAX_UNCOMPRESSED:
                    raise ValueError("archive exceeds extraction limits")
            archive.extractall(destination)
    return count, total


def _apply_replacements(tree, replacements):
    transformed = set()
    for relative, operations in sorted(replacements.items()):
        path = tree / relative
        payload = path.read_text(encoding="utf-8")
        for before, after in operations:
            if payload.count(before) < 1:
                raise ValueError("transform anchor missing in %s: %r" % (relative, before))
            payload = payload.replace(before, after)
        path.write_text(payload, encoding="utf-8")
        transformed.add(relative)
    return transformed


def _apply_patches(tree):
    patched = set()
    for name in SERIES.read_text(encoding="utf-8").splitlines():
        name = name.strip()
        if not name or name.startswith("#"):
            continue
        patch = MWO / "patches" / name
        subprocess.run(
            ["patch", "--batch", "--forward", "-p1", "-i", str(patch)],
            cwd=tree,
            check=True,
        )
        for line in patch.read_text(encoding="utf-8").splitlines():
            if line.startswith("+++ b/"):
                patched.add(line[len("+++ b/") :])
    return patched


def _inventory(tree, transformed, patched, overlays):
    files = {}
    for path in sorted(tree.rglob("*")):
        if path.is_symlink():
            raise ValueError("generated tree contains a symlink")
        if not path.is_file():
            continue
        relative = path.relative_to(tree).as_posix()
        kind = (
            "overlay"
            if relative in overlays
            else "patch"
            if relative in patched
            else "transform"
            if relative in transformed
            else "upstream"
        )
        files[relative] = {
            "kind": kind,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        }
    return files


def rebuild(output):
    state = json.loads(STATE.read_text(encoding="utf-8"))
    transform = json.loads(TRANSFORM.read_text(encoding="utf-8"))
    _ensure_commit(state["repository"], state["commit"])
    archive = _git_bytes(state["commit"], state["archive"])
    if hashlib.sha256(archive).hexdigest() != state["archive_sha256"]:
        raise ValueError("upstream archive SHA-256 mismatch")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    extracted = output.parent / (output.name + "-extracted")
    extracted.mkdir()
    count, total = _extract_safe(archive, extracted, transform["upstream_root"])
    source = extracted / transform["upstream_root"]
    shutil.copytree(source, output, dirs_exist_ok=True)
    transformed = _apply_replacements(output, transform["text_replacements"])
    patched = _apply_patches(output)
    overlays = set()
    for relative, source_relative in transform["overlay_files"].items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MWO / source_relative, target)
        overlays.add(relative)
    for relative, repository_path in transform["repository_files"].items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_git_bytes(state["commit"], repository_path))
        overlays.add(relative)
    return {
        "schema": 1,
        "upstream": {
            "commit": state["commit"],
            "archive": state["archive"],
            "archive_sha256": state["archive_sha256"],
            "files": count,
            "uncompressed_bytes": total,
        },
        "files": _inventory(output, transformed, patched, overlays),
    }


def compare_tree(expected, actual):
    expected_files = {
        path.relative_to(expected).as_posix(): path
        for path in expected.rglob("*")
        if path.is_file()
    }
    actual_files = {
        path.relative_to(actual).as_posix(): path
        for path in actual.rglob("*")
        if path.is_file()
    }
    if set(expected_files) != set(actual_files):
        missing = sorted(set(expected_files) - set(actual_files))
        extra = sorted(set(actual_files) - set(expected_files))
        raise ValueError("tree inventory differs; missing=%r extra=%r" % (missing, extra))
    changed = [
        relative
        for relative in sorted(expected_files)
        if expected_files[relative].read_bytes() != actual_files[relative].read_bytes()
    ]
    if changed:
        raise ValueError("rebuilt files differ: %s" % ", ".join(changed))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--manifest")
    args = parser.parse_args()
    if not args.check and not args.output:
        parser.error("use --check or --output")
    with tempfile.TemporaryDirectory(prefix="mwodevelop-watch-import-") as temporary:
        generated = Path(temporary) / "addon"
        manifest = rebuild(generated)
        if args.check:
            compare_tree(TARGET, generated)
            expected_manifest = MWO / "import-manifest.json"
            if expected_manifest.is_file():
                expected = json.loads(expected_manifest.read_text(encoding="utf-8"))
                if expected != manifest:
                    raise ValueError("import manifest differs from rebuilt inventory")
        if args.output:
            destination = Path(args.output)
            if destination.exists():
                raise ValueError("output already exists")
            shutil.copytree(generated, destination)
        if args.manifest:
            Path(args.manifest).write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
