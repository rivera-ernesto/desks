"""#89: a light respawn. The state is saved, `/clear` reopens the topic by itself, lessons wait for the full close."""
import json
import os
import subprocess
import sys
import time
import unittest

os.environ["DESK_CLOUD"] = "0"  # these are the user's own machine; test_cloud.py covers the cloud

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_desk import DESK, Base, desk, get, put, sh  # noqa: E402


def hook(cwd, source):
    return subprocess.run([sys.executable, DESK, "hook", "session-start"], cwd=cwd, capture_output=True, text=True,
                          input=json.dumps({"source": source}))


class Respawn(Base):
    git = False

    def setUp(self):
        super().setUp()
        self.assertEqual(desk(self.root, "open", "sell-bike").returncode, 0)
        self.marker = os.path.join(self.root, ".desk-respawn")

    def test_respawn_prints_its_line_and_the_next_clear_reopens_the_topic_once(self):
        r = desk(self.root, "respawn", "sell-bike")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Respawn line: Desk `sell-bike` saved for a respawn", r.stdout)
        h = hook(self.root, "clear")
        self.assertIn("continue Desk `sell-bike`", h.stdout)
        self.assertIn("desk.py open sell-bike", h.stdout)
        self.assertFalse(os.path.exists(self.marker), "one-shot: the marker is gone once read")
        self.assertNotIn("Respawn:", hook(self.root, "clear").stdout, "a second /clear reopens nothing")

    def test_a_startup_or_compact_does_not_use_the_marker(self):
        desk(self.root, "respawn", "sell-bike")
        for source in ("startup", "resume", "compact"):
            self.assertNotIn("Respawn:", hook(self.root, source).stdout, source)
        self.assertTrue(os.path.exists(self.marker))

    def test_a_marker_from_another_day_reopens_nothing_and_is_removed(self):
        put(self.marker, f"sell-bike\t{int(time.time()) - 13 * 3600}\n")
        self.assertNotIn("Respawn:", hook(self.root, "clear").stdout)
        self.assertFalse(os.path.exists(self.marker))

    def test_a_broken_marker_never_breaks_the_hook(self):
        put(self.marker, "nonsense")
        h = hook(self.root, "clear")
        self.assertEqual(h.returncode, 0)
        self.assertNotIn("Respawn:", h.stdout)

    def test_the_hook_without_input_still_answers(self):
        p = subprocess.run([sys.executable, DESK, "hook", "session-start"], cwd=self.root, capture_output=True,
                           text=True, stdin=subprocess.DEVNULL)
        self.assertIn("This folder uses Desks", p.stdout)

    def test_respawn_of_a_topic_that_is_not_there_stops(self):
        r = desk(self.root, "respawn", "nothing-here")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.marker))

    def test_the_full_close_refuses_pending_lessons(self):
        desk(self.root, "set", "Close", "merge")
        folder = self.fill("sell-bike")
        readme = os.path.join(folder, "README.md")
        put(readme, get(readme) + "\n## Pending lessons\n\n- the buyer wants photos first\n")
        r = desk(self.root, "close", "sell-bike")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Pending lessons", r.stderr)
        put(readme, get(readme).replace("- the buyer wants photos first\n", ""))
        r = desk(self.root, "close", "sell-bike")
        self.assertNotIn("Pending lessons", r.stderr)


class RespawnGit(Base):
    def test_unsaved_files_stop_a_respawn_and_leave_no_marker(self):
        self.assertEqual(desk(self.root, "open", "sell-bike").returncode, 0)
        folder = os.path.join(self.work("sell-bike"), "desks", "sell-bike")
        put(os.path.join(folder, "draft.md"), "not saved\n")
        r = desk(self.root, "respawn", "sell-bike")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("uncommitted", r.stderr)
        self.assertNotIn("Respawn:", hook(self.root, "clear").stdout)

    def test_a_saved_topic_respawns_and_the_marker_is_outside_the_history(self):
        self.assertEqual(desk(self.root, "open", "sell-bike").returncode, 0)
        self.fill("sell-bike")
        r = desk(self.root, "respawn", "sell-bike")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sh(["git", "status", "--porcelain"], self.root).stdout.strip(), "")
        self.assertIn("continue Desk `sell-bike`", hook(self.root, "clear").stdout)


class HooklessRespawn(Base):
    """#106: with two repositories attached the hooks never load. The marker is still used, once, without them."""
    git = False

    def setUp(self):
        super().setUp()
        self.assertEqual(desk(self.root, "open", "sell-bike").returncode, 0)
        self.marker = os.path.join(self.root, ".desk-respawn")
        self.stamp = os.path.join(self.root, ".desk-hook-seen")

    def test_open_with_no_topic_uses_a_fresh_marker_once(self):
        desk(self.root, "respawn", "sell-bike")
        r = desk(self.root, "open")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Boot line: Desk `sell-bike`", r.stdout)
        self.assertFalse(os.path.exists(self.marker))
        again = desk(self.root, "open")
        self.assertEqual(again.returncode, 0)
        self.assertIn("no pending respawn", again.stdout)
        self.assertNotIn("Boot line:", again.stdout)

    def test_a_stale_marker_is_ignored(self):
        put(self.marker, f"sell-bike\t{int(time.time()) - 13 * 3600}\n")
        r = desk(self.root, "open")
        self.assertIn("no pending respawn", r.stdout)
        self.assertNotIn("Boot line:", r.stdout)

    def test_no_marker_lists_the_topics_and_succeeds(self):
        r = desk(self.root, "open")
        self.assertEqual(r.returncode, 0)
        self.assertIn("sell-bike", r.stdout)

    def test_open_with_a_topic_drops_a_marker_for_that_topic_only(self):
        desk(self.root, "respawn", "sell-bike")
        self.assertEqual(desk(self.root, "open", "sell-bike", "--reopen").returncode, 0)
        self.assertFalse(os.path.exists(self.marker))
        put(self.marker, f"other\t{int(time.time())}\n")
        desk(self.root, "open", "sell-bike", "--reopen")
        self.assertTrue(os.path.exists(self.marker))

    def test_status_reports_a_pending_respawn_without_using_it(self):
        desk(self.root, "respawn", "sell-bike")
        self.assertIn("respawn is pending", desk(self.root, "status").stdout)
        self.assertTrue(os.path.exists(self.marker))

    def test_the_session_start_hook_leaves_a_stamp(self):
        self.assertFalse(os.path.exists(self.stamp))
        hook(self.root, "startup")
        self.assertTrue(os.path.exists(self.stamp))

    def cloud_open(self, start):
        old = {k: os.environ.get(k) for k in ("DESK_CLOUD", "DESK_MACHINE_START")}
        os.environ["DESK_CLOUD"], os.environ["DESK_MACHINE_START"] = "1", str(start)
        try:
            return desk(self.root, "open", "sell-bike", "--reopen")
        finally:
            for k, v in old.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    def test_cloud_open_warns_without_a_stamp_and_is_quiet_with_a_fresh_one(self):
        self.assertIn("hooks unverified", self.cloud_open(time.time() - 100).stdout)
        put(self.stamp, "1\n")
        self.assertNotIn("hooks unverified", self.cloud_open(time.time() - 100).stdout)
        self.assertIn("hooks unverified", self.cloud_open(time.time() + 100).stdout, "a stamp from before the machine started")

    def test_a_local_open_never_warns(self):
        self.assertNotIn("hooks unverified", desk(self.root, "open", "sell-bike", "--reopen").stdout)


if __name__ == "__main__":
    unittest.main()
