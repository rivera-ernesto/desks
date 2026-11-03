"""A session on this repository, a cloud one included, loads the skill and the workers from .claude/.
They are symlinks to the sources, so there is nothing to keep in sync (a copy drifts). On a Windows
clone without symlink support they are plain files and this repository's own sessions do not load
Desks from them; installing it the usual way still works there. Users' folders are never affected.
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Links(unittest.TestCase):
    def test_the_skill_is_the_source(self):
        link = os.path.join(ROOT, ".claude", "skills", "desk")
        self.assertTrue(os.path.islink(link), ".claude/skills/desk must be a symlink to skills/desk")
        self.assertEqual(os.path.realpath(link), os.path.realpath(os.path.join(ROOT, "skills", "desk")))

    def test_every_worker_is_linked_to_its_source(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "agents")) if n.endswith(".md"))
        self.assertTrue(names)
        for n in names:
            link = os.path.join(ROOT, ".claude", "agents", n)
            self.assertTrue(os.path.islink(link), f".claude/agents/{n} is missing: ln -s ../../agents/{n} .claude/agents/{n}")
            self.assertEqual(os.path.realpath(link), os.path.realpath(os.path.join(ROOT, "agents", n)))

    def test_agent_front_matter_is_plain_yaml(self):
        """An unquoted ": " or " #" in a value is not valid YAML; a strict loader would skip the agent."""
        for n in sorted(os.listdir(os.path.join(ROOT, "agents"))):
            with open(os.path.join(ROOT, "agents", n), encoding="utf-8") as f:
                head = f.read().split("---\n")[1]
            for line in head.splitlines():
                value = line.split(": ", 1)[1] if ": " in line else ""
                if value[:1] not in ("'", '"', ">", "|"):
                    self.assertFalse(": " in value or " #" in value, f"agents/{n}: quote this value: {line[:60]}...")


if __name__ == "__main__":
    unittest.main()
