import importlib.util
import inspect
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "watch_update",
    ROOT / "tools/prepare_mwodevelop_watchnixtoons2_update.py",
)
UPDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UPDATE)


class UpdateCycleTests(unittest.TestCase):
    def test_downstream_version_resets_for_new_upstream(self):
        self.assertEqual(UPDATE._next_downstream_version("0.26", "0.25.2"), "0.26.1")

    def test_downstream_version_increments_for_same_upstream(self):
        self.assertEqual(UPDATE._next_downstream_version("0.25", "0.25.2"), "0.25.3")

    def test_bundle_rejects_an_unmanaged_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            tree = temporary / "tree"
            (tree / ".github/workflows").mkdir(parents=True)
            (tree / ".github/workflows/pwn.yml").write_text("name: unsafe\n")
            bundle = temporary / "bundle"
            UPDATE._build_bundle(
                tree,
                bundle,
                {
                    "base_commit": "0" * 40,
                    "upstream": {},
                    "downstream_version": "0.26.1",
                    "managed_addon": UPDATE.ADDON,
                    "managed_files": list(UPDATE.MANAGED_FILES),
                },
            )
            with self.assertRaisesRegex(ValueError, "unmanaged path"):
                UPDATE.verify_bundle(bundle)

    def test_bundle_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            tree = temporary / "tree"
            target = tree / UPDATE.MANAGED_FILES[0]
            target.parent.mkdir(parents=True)
            target.write_text("original\n")
            bundle = temporary / "bundle"
            UPDATE._build_bundle(
                tree,
                bundle,
                {
                    "base_commit": "0" * 40,
                    "upstream": {},
                    "downstream_version": "0.26.1",
                    "managed_addon": UPDATE.ADDON,
                    "managed_files": list(UPDATE.MANAGED_FILES),
                },
            )
            (bundle / "tree" / UPDATE.MANAGED_FILES[0]).write_text("tampered\n")
            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                UPDATE.verify_bundle(bundle)

    def test_raw_upstream_archive_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            tree = temporary / "tree"
            target = tree / UPDATE.MANAGED_FILES[0]
            target.parent.mkdir(parents=True)
            target.write_text("original\n")
            archive = b"trusted raw upstream archive"
            bundle = temporary / "bundle"
            UPDATE._build_bundle(
                tree,
                bundle,
                {
                    "base_commit": "0" * 40,
                    "upstream": {
                        "archive_sha256": UPDATE._sha256(archive),
                    },
                    "downstream_version": "0.26.1",
                    "managed_addon": UPDATE.ADDON,
                    "managed_files": list(UPDATE.MANAGED_FILES),
                },
            )
            (bundle / "upstream-archive.zip").write_bytes(archive + b"tampered")
            with self.assertRaisesRegex(ValueError, "archive digest mismatch"):
                UPDATE.verify_bundle(bundle)

    def test_prepare_never_executes_candidate_tests(self):
        source = inspect.getsource(UPDATE.prepare)
        self.assertNotIn('"unittest"', source)
        self.assertNotIn('"--check"', source)

    def test_tests_are_deferred_until_after_the_scanner_gate(self):
        source = inspect.getsource(UPDATE.test_bundle)
        self.assertIn('"unittest"', source)
        self.assertIn('"--check"', source)
        workflow = (
            ROOT
            / ".github/workflows/mwodevelop-watchnixtoons2-update.yml"
        ).read_text(encoding="utf-8")
        scan = workflow.index("Scan exact candidate before executing tests")
        execute = workflow.index("Test the scanned content-addressed candidate")
        self.assertLess(scan, execute)
        self.assertIn(
            "mwoDevelop/kodi/.github/actions/upstream-malware-scan@"
            "304964cf75011827758dfb994f9811367cab89f3",
            workflow,
        )

    def test_exact_pr_head_is_scanned_before_downstream_tests(self):
        workflow = (
            ROOT / ".github/workflows/mwodevelop-watchnixtoons2.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("test:\n    needs: malware-scan", workflow)
        self.assertIn("git archive HEAD -- mwodevelop tools", workflow)
        self.assertIn(
            "Scan exact head before executing addon code",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
