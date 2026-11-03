"""The lines a session copies into its reply (Boot, Label, Closed) and the two Claude Code hooks:
SessionStart says a folder uses Desks, Stop blocks once when a reply lost a line its turn printed.
Standard library only.
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESK = os.path.join(ROOT, "skills", "desk", "scripts", "desk.py")
spec = importlib.util.spec_from_file_location("desk", DESK)
desk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desk)
os.environ["DESK_CLOUD"] = "0"


def row(kind, *blocks):
    return json.dumps({"type": kind, "message": {"role": kind, "content": list(blocks)}})


def text(t):
    return {"type": "text", "text": t}


def result(t, as_list=False):
    return {"type": "tool_result", "tool_use_id": "x", "content": [text(t)] if as_list else t}


REVIEW_OUT = "Asking 3 reviewers...\n\nLabel line: Review: [converged] · 3 families · receipt 0123456789\n  Earn it first: ..."


class Turn(unittest.TestCase):
    def transcript(self, *rows):
        f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
        f.write("\n".join(rows) + "\n")
        f.close()
        self.addCleanup(os.remove, f.name)
        return f.name

    def stop(self, path, active=False):
        p = subprocess.run([sys.executable, DESK, "hook", "stop"], input=json.dumps(
            {"transcript_path": path, "stop_hook_active": active}), capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout) if p.stdout.strip() else None

    def test_a_reply_without_the_label_its_review_printed_is_blocked_once(self):
        path = self.transcript(row("user", text("is 165 a good price?")),
                               row("assistant", text("Running the review."), {"type": "tool_use", "id": "x", "name": "Bash", "input": {}}),
                               row("user", result(REVIEW_OUT, as_list=True)),
                               row("assistant", text("Ask 165, accept 140.")))
        out = self.stop(path)
        self.assertEqual(out["decision"], "block")
        self.assertIn("Review: [converged] · 3 families · receipt 0123456789", out["reason"])
        self.assertIsNone(self.stop(path, active=True), "never a second block on its own continuation")

    def test_a_reply_that_carries_it_passes(self):
        path = self.transcript(row("user", text("price?")), row("user", result(REVIEW_OUT)),
                               row("assistant", text("Ask 165.\n\nReview: [converged] · 3 families · receipt 0123456789")))
        self.assertIsNone(self.stop(path))

    def test_a_line_printed_in_an_earlier_turn_is_not_asked_for_again(self):
        path = self.transcript(row("user", text("price?")), row("user", result(REVIEW_OUT)),
                               row("assistant", text("Ask 165. Review: [converged] · 3 families · receipt 0123456789")),
                               row("user", text("thanks!")), row("assistant", text("You're welcome.")))
        self.assertIsNone(self.stop(path))

    def test_talk_with_no_script_output_is_never_blocked(self):
        path = self.transcript(row("user", text("hello")), row("assistant", text("Hi.")))
        self.assertIsNone(self.stop(path))

    def test_boot_and_closed_lines_are_checked_by_topic(self):
        path = self.transcript(row("user", text("desk sell-bike")),
                               row("user", result("topic: sell-bike (new)\nBoot line: Desk `sell-bike` · new · folder level · review same-vendor · nothing waiting")),
                               row("assistant", text("Opened.")))
        self.assertIn("Desk `sell-bike` · new", self.stop(path)["reason"])
        path = self.transcript(row("user", text("close it")),
                               row("user", result("Closed line: Desk `sell-bike` closed · folder level, the README is the state")),
                               row("assistant", text("Desk `sell-bike` closed · folder level, the README is the state")))
        self.assertIsNone(self.stop(path))

    def test_a_broken_input_never_breaks_the_session(self):
        p = subprocess.run([sys.executable, DESK, "hook", "stop"], input="not json", capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertIsNone(self.stop("/nonexistent/transcript.jsonl"))


class SessionStart(unittest.TestCase):
    def run_in(self, folder):
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        return subprocess.run([sys.executable, DESK, "hook", "session-start"], cwd=folder, capture_output=True, text=True, env=env)

    def test_silent_in_a_folder_without_desks(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.run_in(d)
            self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_names_the_topics_and_no_next_steps(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "desks", "sell-bike"))
            with open(os.path.join(d, "desks", "sell-bike", "README.md"), "w") as f:
                f.write("# sell-bike\n\n## Next step\n\nList it on Saturday.\n")
            p = self.run_in(d)
            self.assertIn("This folder uses Desks", p.stdout)
            self.assertIn("sell-bike", p.stdout)
            self.assertNotIn("Saturday", p.stdout, "next steps can be stale; they come from status, not the hook")
            self.assertLessEqual(len(p.stdout.splitlines()), 2)


class BootLine(unittest.TestCase):
    def test_open_prints_a_line_to_copy(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, DESK_CONFIG_DIR=os.path.join(d, "conf"), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
            env.pop("OPENROUTER_API_KEY", None)
            p = subprocess.run([sys.executable, DESK, "open", "sell-bike"], cwd=d, capture_output=True, text=True, env=env)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("Boot line: Desk `sell-bike` · new · folder level · review same-vendor · nothing waiting", p.stdout)
            env["OPENROUTER_API_KEY"] = "k"
            p = subprocess.run([sys.executable, DESK, "open", "sell-bike"], cwd=d, capture_output=True, text=True, env=env)
            self.assertIn("Boot line: Desk `sell-bike` · continued · folder level · review cross-vendor", p.stdout)


class Wiring(unittest.TestCase):
    def test_the_plugin_and_this_repository_run_both_hooks(self):
        for path, var in ((os.path.join(ROOT, "hooks", "hooks.json"), "${CLAUDE_PLUGIN_ROOT}"),
                          (os.path.join(ROOT, ".claude", "settings.json"), "$CLAUDE_PROJECT_DIR")):
            with open(path, encoding="utf-8") as f:
                hooks = json.load(f)["hooks"]
            for event, kind in (("SessionStart", "session-start"), ("Stop", "stop")):
                cmd = hooks[event][0]["hooks"][0]["command"]
                self.assertIn(var, cmd, path)
                self.assertTrue(cmd.endswith(f"desk.py\" hook {kind}"), cmd)


if __name__ == "__main__":
    unittest.main()
