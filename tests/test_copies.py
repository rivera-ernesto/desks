"""A cloud session on this repository loads the skill and agents from .claude/. Those are copies,
not symlinks (symlinks break on Windows clones), so they must match their sources byte for byte.
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYNC = ("rm -rf .claude/skills/desk .claude/agents/desk-*.md && mkdir -p .claude/skills .claude/agents"
        " && cp -R skills/desk .claude/skills/desk && cp agents/*.md .claude/agents/")
IGNORED = {"__pycache__", ".DS_Store"}  # the same as .gitignore


def files(top):
    """Paths under top, relative to it, without what git ignores."""
    found = set()
    for d, dirs, names in os.walk(os.path.join(ROOT, top)):
        dirs[:] = [x for x in dirs if x not in IGNORED]
        for n in names:
            if n not in IGNORED and not n.endswith(".pyc"):
                found.add(os.path.relpath(os.path.join(d, n), os.path.join(ROOT, top)))
    return found


def same(a, b):
    with open(os.path.join(ROOT, a), "rb") as f, open(os.path.join(ROOT, b), "rb") as g:
        return f.read() == g.read()


class CopiesMatch(unittest.TestCase):
    def check(self, source, copy, extra):
        """extra: copies with no source, as found by the caller."""
        src = files(source)
        self.assertTrue(src, source + " is empty")
        dst = files(copy) if os.path.isdir(os.path.join(ROOT, copy)) else set()
        wrong = [os.path.join(copy, p) + " is missing" for p in sorted(src - dst)]
        wrong += [os.path.join(copy, p) + " differs" for p in sorted(src & dst)
                  if not same(os.path.join(source, p), os.path.join(copy, p))]
        wrong += [p + " has no source" for p in sorted(extra(src, dst))]
        if wrong:
            self.fail("\n  " + "\n  ".join(wrong) + "\nRe-sync from the repository root with:\n  " + SYNC)

    def test_skill_copy(self):
        self.check(os.path.join("skills", "desk"), os.path.join(".claude", "skills", "desk"),
                   lambda src, dst: {os.path.join(".claude", "skills", "desk", p) for p in dst - src})

    def test_agent_front_matter_is_plain_yaml(self):
        """An unquoted ": " or " #" in a value is not valid YAML; a strict loader would skip the agent."""
        for name in sorted(files("agents")):
            with open(os.path.join(ROOT, "agents", name), encoding="utf-8") as f:
                head = f.read().split("---\n")[1]
            for line in head.splitlines():
                value = line.split(": ", 1)[1] if ": " in line else ""
                if value[:1] not in ("'", '"', ">", "|"):
                    self.assertFalse(": " in value or " #" in value,
                                     f"agents/{name}: quote this value: {line[:60]}...")

    def test_agent_copies(self):
        self.check("agents", os.path.join(".claude", "agents"),
                   lambda src, dst: {os.path.join(".claude", "agents", p) for p in dst - src
                                     if p.startswith("desk-") and p.endswith(".md")})


if __name__ == "__main__":
    unittest.main()
