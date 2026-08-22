import json
import py_compile
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "plugin.video.watchnixtoons2.mwodevelop"
ADDON_ID = "plugin.video.watchnixtoons2.mwodevelop"


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.addon = ET.parse(ADDON / "addon.xml").getroot()
        self.transform = json.loads(
            (ROOT / "transforms/addon_identity.json").read_text(encoding="utf-8")
        )

    def test_identity_and_provenance_are_downstream_specific(self):
        self.assertEqual(self.addon.attrib["id"], ADDON_ID)
        self.assertEqual(
            self.addon.attrib["version"], self.transform["downstream_version"]
        )
        self.assertIn("mwoDevelop", self.addon.attrib["name"])

        metadata = self.addon.find("extension[@point='xbmc.addon.metadata']")
        self.assertEqual(metadata.findtext("license"), "GPL-3.0-only")
        self.assertEqual(metadata.findtext("source"), "https://github.com/mwoDevelop/ch.repo")

        provenance = json.loads((ROOT / "upstream.json").read_text(encoding="utf-8"))
        identity_anchor = self.transform["text_replacements"]["addon.xml"][0][0]
        upstream_version = ET.fromstring(identity_anchor + "</addon>").attrib["version"]
        self.assertEqual(provenance["version"], upstream_version)
        self.assertEqual(len(provenance["archive_sha256"]), 64)

    def test_runtime_dependencies_are_declared(self):
        imports = {
            node.attrib["addon"]: node.attrib.get("version")
            for node in self.addon.findall("./requires/import")
        }
        self.assertEqual(imports["xbmc.python"], "3.0.0")
        self.assertIn("script.module.requests", imports)
        self.assertIn("script.module.six", imports)
        self.assertIn("inputstream.adaptive", imports)
        adaptive = self.addon.find(
            "./requires/import[@addon='inputstream.adaptive']"
        )
        self.assertEqual(adaptive.attrib.get("optional"), "true")

    def test_settings_actions_target_this_addon(self):
        settings = ET.parse(ADDON / "resources/settings.xml").getroot()
        actions = [
            node.attrib["action"]
            for node in settings.iter("setting")
            if node.attrib.get("type") == "action"
        ]
        self.assertTrue(actions)
        for action in actions:
            self.assertTrue(
                action.startswith("RunPlugin(plugin://%s/" % ADDON_ID),
                action,
            )

    def test_python_sources_compile(self):
        with tempfile.TemporaryDirectory() as bytecode_dir:
            for source in ADDON.rglob("*.py"):
                target = Path(bytecode_dir) / (source.name + "c")
                py_compile.compile(str(source), cfile=str(target), doraise=True)

    def test_declared_assets_exist(self):
        metadata = self.addon.find("extension[@point='xbmc.addon.metadata']")
        assets = metadata.find("assets")
        for node in assets:
            self.assertTrue((ADDON / node.text).is_file(), node.text)

    def test_package_contains_no_upstream_catalog_archives(self):
        self.assertFalse(list(ADDON.rglob("*.zip")))

    def test_python3_resolver_regressions_are_fixed(self):
        plugin_source = (ADDON / "lib/plugin.py").read_text(encoding="utf-8")
        network_source = (ADDON / "lib/network.py").read_text(encoding="utf-8")
        self.assertNotIn("html.find(b'jw.onError')", plugin_source)
        self.assertIn("html.find('jw.onError')", plugin_source)
        self.assertIn("pair.split('=', 1)", network_source)
        self.assertIn(
            "System.HasAddon(inputstream.adaptive)",
            plugin_source,
        )

    def test_https_requests_keep_certificate_verification_enabled(self):
        network_source = (ADDON / "lib/network.py").read_text(encoding="utf-8")
        plugin_source = (ADDON / "lib/plugin.py").read_text(encoding="utf-8")
        self.assertNotIn("verify=False", network_source)
        self.assertNotIn("verify=False", plugin_source)
        self.assertNotIn("disable_warnings", network_source)
        self.assertNotIn("PROTOCOL_TLSv1_1", network_source)

    def test_menu_labels_have_runtime_fallbacks(self):
        plugin_source = (ADDON / "lib/plugin.py").read_text(encoding="utf-8")
        self.assertIn("LANGUAGE_FALLBACKS", plugin_source)
        self.assertIn("30050: 'Latest Releases'", plugin_source)
        self.assertIn("ADDON.getLocalizedString(string_id) or", plugin_source)

    def test_import_is_reproducible(self):
        import subprocess
        import sys

        subprocess.run(
            [
                sys.executable,
                str(ROOT.parent / "tools" / "import_mwodevelop_watchnixtoons2.py"),
                "--check",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    unittest.main()
