#!/usr/bin/env python3
"""Prepare and safely apply a review-gated WatchNixtoons2 upstream update."""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
MWO = ROOT / "mwodevelop"
STATE = MWO / "upstream.json"
TRANSFORM = MWO / "transforms" / "addon_identity.json"
ADDON = "mwodevelop/plugin.video.watchnixtoons2.mwodevelop"
MANAGED_FILES = (
    "mwodevelop/README.md",
    "mwodevelop/import-manifest.json",
    "mwodevelop/transforms/addon_identity.json",
    "mwodevelop/upstream.json",
)
SCHEMA = 1
MAX_FILES = 4096
MAX_UNCOMPRESSED = 256 * 1024 * 1024


def _run(*args, cwd=ROOT, check=True, text=True):
    result = subprocess.run(
        list(args),
        cwd=cwd,
        check=False,
        text=text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode:
        stdout = result.stdout if text else result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr if text else result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(
            "command failed (%s): %s\n%s"
            % (result.returncode, " ".join(args), (stdout + stderr).strip())
        )
    return result


def _git_bytes(root, commit, path):
    result = _run(
        "git", "show", "%s:%s" % (commit, path), cwd=root, check=False, text=False
    )
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def _sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def _canonical(payload):
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _safe_relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or not value or ".." in path.parts:
        raise ValueError("unsafe candidate path: %r" % value)
    return path.as_posix()


def _archive_details(payload, expected_root):
    import io

    count = 0
    total = 0
    addon_xml = None
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
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
            if path.as_posix() == expected_root + "/addon.xml":
                addon_xml = archive.read(item)
    if addon_xml is None:
        raise ValueError("archive does not contain the expected addon.xml")
    return {"files": count, "uncompressed_bytes": total, "addon_xml": addon_xml}


def _next_downstream_version(upstream_version, current_version):
    upstream = tuple(int(part) for part in upstream_version.split("."))
    current = tuple(int(part) for part in current_version.split("."))
    base = ".".join(str(part) for part in upstream)
    if len(current) == len(upstream) + 1 and current[:-1] == upstream:
        return base + "." + str(current[-1] + 1)
    return base + ".1"


def discover(root=ROOT, repository=None, branch="master"):
    state = json.loads((root / "mwodevelop/upstream.json").read_text(encoding="utf-8"))
    repository = repository or state["repository"]
    observed = _run("git", "ls-remote", repository, "refs/heads/" + branch, cwd=root)
    fields = observed.stdout.split()
    if not fields or not re.fullmatch(r"[0-9a-f]{40}", fields[0]):
        raise ValueError("upstream branch did not resolve to an immutable commit")
    observed_commit = fields[0]
    accepted_commit = state["commit"]
    commit_present = _run(
        "git",
        "cat-file",
        "-e",
        observed_commit + "^{commit}",
        cwd=root,
        check=False,
    ).returncode == 0
    if not commit_present:
        _run(
            "git",
            "fetch",
            "--no-tags",
            repository.rstrip("/") + ".git",
            observed_commit,
            cwd=root,
        )
    if observed_commit != accepted_commit:
        ancestry = _run(
            "git",
            "merge-base",
            "--is-ancestor",
            accepted_commit,
            observed_commit,
            cwd=root,
            check=False,
        )
        if ancestry.returncode:
            raise ValueError("upstream history was rewritten; automatic update is blocked")
    descriptor_path = state["addon_id"] + "/addon.xml"
    descriptor_payload = _git_bytes(root, observed_commit, descriptor_path)
    try:
        descriptor = ET.fromstring(descriptor_payload)
    except ET.ParseError as error:
        raise ValueError("invalid upstream addon.xml: %s" % error) from error
    if descriptor.attrib.get("id") != state["addon_id"]:
        raise ValueError("upstream add-on ID changed")
    version = descriptor.attrib.get("version")
    if not version or not all(part.isdigit() for part in version.split(".")):
        raise ValueError("unsupported upstream version: %r" % version)
    archive = "%s/%s-%s.zip" % (state["addon_id"], state["addon_id"], version)
    archive_payload = _git_bytes(root, observed_commit, archive)
    details = _archive_details(archive_payload, state["addon_id"])
    archive_descriptor = ET.fromstring(details["addon_xml"])
    if (
        archive_descriptor.attrib.get("id") != state["addon_id"]
        or archive_descriptor.attrib.get("version") != version
    ):
        raise ValueError("archive identity differs from the repository descriptor")
    digest = _sha256(archive_payload)
    unchanged = (
        observed_commit == accepted_commit
        and version == state["version"]
        and archive == state["archive"]
        and digest == state["archive_sha256"]
    )
    return {
        "schema": SCHEMA,
        "action": "noop" if unchanged else "prepare",
        "accepted": {
            "commit": accepted_commit,
            "version": state["version"],
            "archive": state["archive"],
            "archive_sha256": state["archive_sha256"],
        },
        "observed": {
            "repository": repository,
            "branch": branch,
            "commit": observed_commit,
            "version": version,
            "archive": archive,
            "archive_sha256": digest,
            "files": details["files"],
            "uncompressed_bytes": details["uncompressed_bytes"],
        },
    }


def _update_transform(path, archive_addon_xml, upstream_version, downstream_version):
    transform = json.loads(path.read_text(encoding="utf-8"))
    upstream_opening = next(
        line
        for line in archive_addon_xml.decode("utf-8").splitlines()
        if line.startswith("<addon ")
    )
    identity = transform["text_replacements"]["addon.xml"][0]
    downstream_opening = re.sub(
        r' version="[^"]+"',
        ' version="%s"' % downstream_version,
        identity[1],
        count=1,
    )
    identity[:] = [upstream_opening, downstream_opening]
    transform["downstream_version"] = downstream_version

    news_header = (
        "        <news>[COLOR orange][B]WatchNixtoons2[/B][/COLOR] "
        "- Cartoons &amp; Anime\n"
    )
    news_operation = next(
        operation
        for operation in transform["text_replacements"]["addon.xml"]
        if operation[0] == news_header
    )
    if ("[B]%s[/B]" % downstream_version) not in news_operation[1]:
        old_body = news_operation[1][len(news_header) :]
        section = (
            "\n[B]%s[/B]\n"
            "- Rebased the isolated mwoDevelop package on upstream %s\n"
            "- Preserved downstream identity, Python 3 resolver fixes and optional "
            "InputStream Adaptive fallback\n"
            % (downstream_version, upstream_version)
        )
        news_operation[1] = news_header + section + old_body
    path.write_text(json.dumps(transform, indent=2) + "\n", encoding="utf-8")


def _inventory(tree):
    files = {}
    paths = sorted(path for path in tree.rglob("*") if path.is_file() or path.is_symlink())
    if len(paths) > MAX_FILES:
        raise ValueError("candidate contains too many files")
    for path in paths:
        relative = _safe_relative(path.relative_to(tree).as_posix())
        if path.is_symlink():
            raise ValueError("candidate symlink is forbidden: %s" % relative)
        payload = path.read_bytes()
        files[relative] = {
            "sha256": _sha256(payload),
            "size": len(payload),
            "executable": bool(path.stat().st_mode & 0o111),
        }
    return files


def _build_bundle(tree, output, metadata):
    output = Path(output)
    if output.exists():
        raise ValueError("candidate output already exists")
    files = _inventory(tree)
    body = {"schema": SCHEMA, "metadata": metadata, "files": files}
    candidate_id = _sha256(_canonical(body))
    document = {**body, "candidate_id": candidate_id}
    (output / "tree").mkdir(parents=True)
    for relative, item in files.items():
        source = tree / relative
        target = output / "tree" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        os.chmod(target, 0o755 if item["executable"] else 0o644)
    payload = _canonical(document)
    (output / "candidate.json").write_bytes(payload)
    (output / "candidate.json.sha256").write_text(_sha256(payload) + "\n")
    return document


def prepare(discovery, output, root=ROOT):
    if discovery.get("action") != "prepare":
        raise ValueError("discovery does not contain an update to prepare")
    current = discover(
        root,
        repository=discovery["observed"]["repository"],
        branch=discovery["observed"]["branch"],
    )
    if current != discovery:
        raise ValueError("upstream changed between discovery and preparation")
    base = _run("git", "rev-parse", "HEAD", cwd=root).stdout.strip()
    current_transform = json.loads(
        (root / "mwodevelop/transforms/addon_identity.json").read_text(
            encoding="utf-8"
        )
    )
    downstream_version = _next_downstream_version(
        discovery["observed"]["version"],
        current_transform["downstream_version"],
    )
    archive_payload = _git_bytes(
        root, discovery["observed"]["commit"], discovery["observed"]["archive"]
    )
    details = _archive_details(archive_payload, "plugin.video.watchnixtoons2.kodi19")

    with tempfile.TemporaryDirectory(prefix="watch-update-") as temporary:
        temporary = Path(temporary)
        worktree = temporary / "checkout"
        _run("git", "worktree", "add", "--detach", str(worktree), base, cwd=root)
        try:
            state_path = worktree / "mwodevelop/upstream.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state.update(
                {
                    "commit": discovery["observed"]["commit"],
                    "version": discovery["observed"]["version"],
                    "archive": discovery["observed"]["archive"],
                    "archive_sha256": discovery["observed"]["archive_sha256"],
                }
            )
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            _update_transform(
                worktree / "mwodevelop/transforms/addon_identity.json",
                details["addon_xml"],
                discovery["observed"]["version"],
                downstream_version,
            )
            readme = worktree / "mwodevelop/README.md"
            readme.write_text(
                re.sub(
                    r"^- Imported release: .+$",
                    "- Imported release: `%s`" % discovery["observed"]["version"],
                    readme.read_text(encoding="utf-8"),
                    flags=re.MULTILINE,
                ),
                encoding="utf-8",
            )
            generated = temporary / "generated-addon"
            manifest = temporary / "import-manifest.json"
            _run(
                "python3",
                "tools/import_mwodevelop_watchnixtoons2.py",
                "--output",
                str(generated),
                "--manifest",
                str(manifest),
                cwd=worktree,
            )
            target = worktree / ADDON
            shutil.rmtree(target)
            shutil.copytree(generated, target)
            shutil.copyfile(manifest, worktree / "mwodevelop/import-manifest.json")

            candidate_tree = temporary / "candidate-tree"
            candidate_tree.mkdir()
            for relative in MANAGED_FILES:
                source = worktree / relative
                target_file = candidate_tree / relative
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target_file)
            shutil.copytree(worktree / ADDON, candidate_tree / ADDON)
            _run(
                "git",
                "add",
                *MANAGED_FILES,
                ADDON,
                cwd=worktree,
            )
            expected_tree = _run("git", "write-tree", cwd=worktree).stdout.strip()
            document = _build_bundle(
                candidate_tree,
                output,
                {
                    "base_commit": base,
                    "expected_tree": expected_tree,
                    "upstream": discovery["observed"],
                    "downstream_version": downstream_version,
                    "managed_addon": ADDON,
                    "managed_files": list(MANAGED_FILES),
                },
            )
        finally:
            _run(
                "git",
                "worktree",
                "remove",
                "--force",
                str(worktree),
                cwd=root,
                check=False,
            )
    return document


def test_bundle(bundle, root=ROOT):
    """Execute candidate-dependent checks only after the scanner gate."""
    document = verify_bundle(bundle)
    base = document["metadata"]["base_commit"]
    with tempfile.TemporaryDirectory(prefix="watch-candidate-test-") as temporary:
        checkout = Path(temporary) / "checkout"
        _run("git", "worktree", "add", "--detach", str(checkout), base, cwd=root)
        try:
            apply_bundle(bundle, checkout)
            _run(
                "python3",
                "tools/import_mwodevelop_watchnixtoons2.py",
                "--check",
                cwd=checkout,
            )
            _run(
                "python3",
                "-m",
                "unittest",
                "discover",
                "-s",
                "mwodevelop/tests",
                "-v",
                cwd=checkout,
            )
        finally:
            _run(
                "git",
                "worktree",
                "remove",
                "--force",
                str(checkout),
                cwd=root,
                check=False,
            )
    return document


def verify_bundle(bundle):
    bundle = Path(bundle).resolve()
    payload = (bundle / "candidate.json").read_bytes()
    expected = (bundle / "candidate.json.sha256").read_text().strip()
    if _sha256(payload) != expected:
        raise ValueError("candidate document digest mismatch")
    document = json.loads(payload)
    candidate_id = document.pop("candidate_id", None)
    if candidate_id != _sha256(_canonical(document)):
        raise ValueError("candidate ID mismatch")
    document["candidate_id"] = candidate_id
    if document.get("schema") != SCHEMA:
        raise ValueError("unsupported candidate schema")
    if _inventory(bundle / "tree") != document.get("files"):
        raise ValueError("candidate tree inventory mismatch")
    metadata = document["metadata"]
    allowed_files = set(metadata["managed_files"])
    addon = metadata["managed_addon"].rstrip("/")
    for relative in document["files"]:
        if relative not in allowed_files and not relative.startswith(addon + "/"):
            raise ValueError("candidate contains an unmanaged path: %s" % relative)
    return document


def apply_bundle(bundle, checkout):
    document = verify_bundle(bundle)
    checkout = Path(checkout).resolve()
    head = _run("git", "rev-parse", "HEAD", cwd=checkout).stdout.strip()
    if head != document["metadata"]["base_commit"]:
        raise ValueError("candidate base commit differs from the writer checkout")
    target = checkout / document["metadata"]["managed_addon"]
    if target.exists():
        shutil.rmtree(target)
    for relative in sorted(document["files"]):
        source = Path(bundle).resolve() / "tree" / relative
        destination = checkout / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        os.chmod(destination, 0o755 if document["files"][relative]["executable"] else 0o644)
    return document


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    discovery_parser = subparsers.add_parser("discover")
    discovery_parser.add_argument("--repository")
    discovery_parser.add_argument("--branch", default="master")
    discovery_parser.add_argument("--output", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--discovery", required=True)
    prepare_parser.add_argument("--output", required=True)
    test_parser = subparsers.add_parser("test")
    test_parser.add_argument("--bundle", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--bundle", required=True)
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--bundle", required=True)
    apply_parser.add_argument("--checkout", default=".")
    args = parser.parse_args()

    if args.command == "discover":
        result = discover(repository=args.repository, branch=args.branch)
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    elif args.command == "prepare":
        result = prepare(
            json.loads(Path(args.discovery).read_text(encoding="utf-8")),
            args.output,
        )
    elif args.command == "test":
        result = test_bundle(args.bundle)
    elif args.command == "verify":
        result = verify_bundle(args.bundle)
    else:
        result = apply_bundle(args.bundle, args.checkout)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
