import importlib.util
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


if __name__ == "__main__":
    unittest.main()
