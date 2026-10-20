"""The version is written in several files a person copies from. They must agree."""
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class VersionAgrees(unittest.TestCase):
    def setUp(self):
        self.version = json.loads(read(".claude-plugin", "plugin.json"))["version"]
        self.tag = "v" + self.version

    def test_install_prompts_name_the_plugin_version(self):
        for parts in (("README.md",), ("docs", "es", "inicio-rapido.md"), ("site", "src", "data", "site.ts")):
            found = set(re.findall(r"v\d+\.\d+\.\d+", read(*parts)))
            self.assertEqual(found, {self.tag}, os.path.join(*parts))

    def test_install_steps_name_the_plugin_version(self):
        text = read("INSTALL.md")
        self.assertIn("--branch " + self.tag + " ", text)
        self.assertIn("- Version: " + self.version + "\n", text)
        self.assertEqual(set(re.findall(r"v\d+\.\d+\.\d+", text)), {self.tag})

    def test_changelog_has_the_version(self):
        self.assertIn("## " + self.version + " ", read("CHANGELOG.md"))

    def test_site_release_date_is_the_changelog_date(self):
        # The footer shows when VERSION was released; it must not drift from the changelog.
        m = re.search(r"^## " + re.escape(self.version) + r" \((\d{4}-\d{2}-\d{2})\)", read("CHANGELOG.md"), re.M)
        site = re.search(r"RELEASED = '(\d{4}-\d{2}-\d{2})'", read("site", "src", "data", "site.ts"))
        self.assertTrue(m and site)
        self.assertEqual(site.group(1), m.group(1))


if __name__ == "__main__":
    unittest.main()
