"""A Desk in a cloud session: open, review and close on the session's own branch, which must be
pushed before the close counts. Real scratch repositories; the reviewers are fake servers on
this machine. Standard library only.
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "desk", "scripts")
sys.path.insert(0, HERE)
from fake_openai import Fake  # noqa: E402

BLOCK = "<!-- desk:start -->\n## Desk\n\n- Desk root: `desks/`\n- Close: merge\n<!-- desk:end -->\n"
SECRET = "endpoint-key-" + "4" * 24


def sh(args, cwd, env=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)


class CloudDesk(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        top = os.path.realpath(self._tmp.name)
        self.remote, self.root = os.path.join(top, "remote.git"), os.path.join(top, "work")
        self.conf = os.path.join(top, "conf")
        os.makedirs(self.conf)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("DESK_") and k not in ("OPENROUTER_API_KEY", "CLAUDE_CODE_REMOTE")}
        self.env.update(DESK_CLOUD="1", DESK_CONFIG_DIR=self.conf, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        sh(["git", "init", "-q", "--bare", "-b", "main", self.remote], top)
        sh(["git", "clone", "-q", self.remote, self.root], top)
        for a in (["config", "user.email", "t@example.invalid"], ["config", "user.name", "t"]):
            sh(["git", *a], self.root)
        with open(os.path.join(self.root, "CLAUDE.md"), "w") as f:
            f.write(BLOCK)
        for a in (["add", "CLAUDE.md"], ["commit", "-qm", "init"], ["push", "-q", "origin", "main"],
                  ["checkout", "-q", "-b", "claude/session-branch"]):
            self.assertEqual(sh(["git", *a], self.root).returncode, 0, a)
        self.fakes = []

    def tearDown(self):
        for f in self.fakes:
            f.close()
        self._tmp.cleanup()

    def desk(self, *args):
        return sh([sys.executable, os.path.join(SCRIPTS, "desk.py"), *args], self.root, self.env)

    def git(self, *args):
        p = sh(["git", *args], self.root)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_open_works_on_the_session_branch_with_no_worktree(self):
        p = self.desk("open", "sell-bike")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(f"work in: {os.path.join(self.root, 'desks', 'sell-bike')}", p.stdout)
        self.assertIn("claude/session-branch (this cloud session's branch", p.stdout)
        self.assertNotIn("desk/sell-bike", self.git("branch", "--list"))
        self.assertFalse(os.path.exists(os.path.join(self.root, ".claude", "worktrees")))
        self.assertIn("environment: cloud session", self.desk("status").stdout)

    def test_a_note_for_another_topic_lands_on_the_session_branch(self):
        self.desk("open", "sell-bike")
        p = self.desk("note", "sell-bike", "move-house", "the bike rack stays")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(os.listdir(os.path.join(self.root, "desks", "move-house", "inbox")))

    def test_the_close_waits_until_everything_is_pushed(self):
        self.desk("open", "sell-bike")
        folder = os.path.join(self.root, "desks", "sell-bike")
        self.write("desks/sell-bike/README.md", "# sell-bike\n\n## Next step\n\nList it.\n")
        self.write("desks/sell-bike/sessions/2026-01-01-price.md", "# Price\n\nSet at the median.\n")
        p = self.desk("close", "sell-bike")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("uncommitted", p.stderr)
        self.git("add", folder)
        self.git("commit", "-qm", "sell-bike: price")
        p = self.desk("close", "sell-bike")
        self.assertIn("never been pushed", p.stderr)
        self.assertNotIn("Closed line", p.stdout)
        self.git("push", "-q", "-u", "origin", "claude/session-branch")
        self.write("desks/sell-bike/decisions.md", "# Decisions\n\n2026-01-01 median price.\n")
        self.git("commit", "-qam", "decision")
        p = self.desk("close", "sell-bike")
        self.assertIn("1 commit(s)", p.stderr)
        self.git("push", "-q")
        p = self.desk("close", "sell-bike")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Closed line: Desk `sell-bike` closed · saved and pushed on claude/session-branch", p.stdout)
        self.assertEqual(self.git("branch", "--show-current").strip(), "claude/session-branch", "nothing merged or switched")
        self.assertNotIn("sell-bike", sh(["git", "log", "--oneline", "main"], self.root).stdout)

    def test_open_review_close_end_to_end(self):
        """The whole Desk, as a cloud session runs it: two reviewers of other families are endpoints
        declared by environment variables, one with a key; the key goes nowhere but its request."""
        a, b = Fake(model="alpha/m", key=SECRET, echo_auth=True), Fake(model="beta/m")
        self.fakes += [a, b]
        self.env.update(DESK_ENDPOINT_ALPHA_URL=a.url, DESK_ENDPOINT_ALPHA_MODEL=a.model, DESK_ENDPOINT_ALPHA_KEY=SECRET,
                        DESK_ENDPOINT_BETA_URL=b.url, DESK_ENDPOINT_BETA_MODEL=b.model, DESK_PRIVATE_TERMS="Mara")

        p = self.desk("open", "sell-bike")
        self.assertEqual(p.returncode, 0, p.stderr)
        dash = sh([sys.executable, os.path.join(SCRIPTS, "providers.py")], self.root, self.env)
        self.assertRegex(dash.stdout, r"alpha\s+ok")
        self.assertRegex(dash.stdout, r"beta\s+ok")
        self.assertNotIn(SECRET, dash.stdout + dash.stderr)

        packet = self.write("desks/sell-bike/reviews/2026-01-01-price.md",
                            "Question: what price for a used city bike in a mid-size town?\nProposal: the median of ten recent sales.\n")
        r = sh([sys.executable, os.path.join(SCRIPTS, "review.py"), packet, "is the median right?"], self.root, self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[converged] · 2 vendors", r.stdout)
        self.assertEqual(a.seen_auth[-1], "Bearer " + SECRET)
        rid = r.stdout.split("receipt ")[-1].split()[0]

        refused = self.write("desks/sell-bike/reviews/2026-01-01-names.md", "Should Mara keep the bike?\n")
        r2 = sh([sys.executable, os.path.join(SCRIPTS, "review.py"), refused], self.root, self.env)
        self.assertEqual(r2.returncode, 1)
        self.assertIn('your private term "Mara"', r2.stderr)
        os.remove(refused)

        self.write("desks/sell-bike/reviews/2026-01-01-price-dispositions.md", "| finding | disposition |\n|---|---|\n| demand | adopted |\n")
        v = sh([sys.executable, os.path.join(SCRIPTS, "review.py"), "--verify", rid, "desks"], self.root, self.env)
        self.assertIn("dispositions present", v.stdout)

        self.write("desks/sell-bike/README.md", "# sell-bike\n\n## State\n\nPriced.\n\n## Next step\n\nList it.\n")
        self.write("desks/sell-bike/sessions/2026-01-01-price.md", "# Price\n\nMedian of ten sales, reviewed.\n")
        self.git("add", "desks/sell-bike")
        self.git("commit", "-qm", "sell-bike: price, reviewed")
        self.git("push", "-q", "-u", "origin", "claude/session-branch")
        c = self.desk("close", "sell-bike")
        self.assertEqual(c.returncode, 0, c.stderr)
        self.assertIn("Closed line:", c.stdout)

        tracked = self.git("ls-files")
        self.assertIn("desks/sell-bike/reviews/2026-01-01-price-reviews/alpha.txt", tracked)
        for rel in tracked.split():
            with open(os.path.join(self.root, rel), encoding="utf-8", errors="ignore") as f:
                self.assertNotIn(SECRET, f.read(), rel)
        with open(os.path.join(self.root, "desks/sell-bike/reviews/2026-01-01-price-reviews/alpha.txt")) as f:
            self.assertIn("[key hidden]", f.read())


class LocalUnchanged(unittest.TestCase):
    def test_off_the_cloud_open_still_makes_a_branch_and_working_copy(self):
        with tempfile.TemporaryDirectory() as top:
            root = os.path.realpath(top)
            env = dict(os.environ, DESK_CLOUD="0", DESK_CONFIG_DIR=os.path.join(root, "c"),
                       GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
            sh(["git", "init", "-q", "-b", "main"], root)
            for a in (["config", "user.email", "t@example.invalid"], ["config", "user.name", "t"]):
                sh(["git", *a], root)
            with open(os.path.join(root, "CLAUDE.md"), "w") as f:
                f.write(BLOCK)
            sh(["git", "add", "CLAUDE.md"], root)
            sh(["git", "commit", "-qm", "init"], root)
            p = sh([sys.executable, os.path.join(SCRIPTS, "desk.py"), "open", "t"], root, env)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("branch: desk/t", p.stdout)


if __name__ == "__main__":
    unittest.main()
