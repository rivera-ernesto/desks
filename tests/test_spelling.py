"""#95: a topic folder whose name is not its slug is found, never silently doubled. Standard library only."""
import os
import shlex
import sys
import unittest

# These tests are of the user's own machine; a cloud session runs them too (test_cloud.py sets its own).
os.environ["DESK_CLOUD"] = "0"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_desk import Base, desk, put, sh  # noqa: E402


class Spelling(Base):
    def topic(self, name, save=True):
        folder = os.path.join(self.root, "desks", name)
        os.makedirs(folder, exist_ok=True)
        put(os.path.join(folder, "README.md"), f"# {name}\n\nnotes\n")
        if save:
            sh(["git", "add", "desks"], self.root)
            sh(["git", "commit", "-qm", "topic"], self.root)
        return folder

    def branches(self):
        return sh(["git", "branch", "--list"], self.root).stdout

    def test_open_stops_on_a_dotted_folder_and_creates_nothing(self):
        self.topic("a.b")
        before = self.branches()
        r = desk(self.root, "open", "a.b")
        self.assertEqual(r.returncode, 8, r.stderr)
        self.assertIn("a.b/ has the same name in another spelling", r.stderr)
        self.assertIn("git mv a.b a-b", r.stderr)  # tracked, so git mv
        self.assertFalse(os.path.exists(os.path.join(self.root, "desks", "a-b")))
        self.assertEqual(self.branches(), before)  # no branch or working copy either

    def test_control_the_slug_folder_opens(self):
        self.topic("a-b")
        r = desk(self.root, "open", "a-b")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("(continued)", r.stdout)

    def test_an_unsaved_folder_gets_a_plain_mv(self):
        self.topic("a.b", save=False)
        r = desk(self.root, "open", "a.b")
        self.assertEqual(r.returncode, 8)
        self.assertIn("&& mv a.b a-b", r.stderr)

    def test_several_spellings_stop_and_are_listed(self):
        self.topic("a.b")
        self.topic("A_B")
        r = desk(self.root, "open", "a-b")
        self.assertEqual(r.returncode, 8)
        self.assertIn("A_B/, a.b/", r.stderr)

    def test_a_case_only_difference_renames_through_a_temporary_name(self):
        self.topic("Trip-Japan")
        r = desk(self.root, "open", "trip-japan")
        self.assertEqual(r.returncode, 8)
        self.assertIn("git mv Trip-Japan trip-japan.tmp && git mv trip-japan.tmp trip-japan", r.stderr)

    def test_a_symlink_gets_no_move_command(self):
        real = self.topic("real-notes")
        os.symlink(real, os.path.join(self.root, "desks", "a.b"))
        r = desk(self.root, "open", "a.b")
        self.assertEqual(r.returncode, 8)
        self.assertIn("is a symlink", r.stderr)
        self.assertNotIn("mv ", r.stderr)

    def test_a_folder_name_with_no_letter_or_digit_is_no_match_and_no_stop(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("desk_mod", os.path.join(os.path.dirname(__file__), "..", "skills", "desk", "scripts", "desk.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        base = os.path.join(self.root, "desks")
        os.makedirs(os.path.join(base, "---"), exist_ok=True)
        os.makedirs(os.path.join(base, "Trip-Japan"), exist_ok=True)
        self.assertEqual(mod.near_matches(base, "trip-japan"), ["Trip-Japan"])

    def test_hidden_folders_are_not_topics(self):
        os.makedirs(os.path.join(self.root, "desks", ".a-b"))
        r = desk(self.root, "open", "a-b")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("(new)", r.stdout)

    def test_a_note_for_a_dotted_topic_stops(self):
        self.topic("a.b")
        self.assertEqual(desk(self.root, "open", "here").returncode, 0)
        r = desk(self.root, "note", "here", "a.b", "something")
        self.assertEqual(r.returncode, 1)
        self.assertIn("a.b/ has the same name in another spelling", r.stderr)

    def test_a_root_with_a_space_gets_a_quoted_command(self):  # a pasted rename must survive `/Users/First Last/`
        spaced = os.path.join(self.root, "First Last")
        os.makedirs(os.path.join(spaced, "desks", "a.b"))
        put(os.path.join(spaced, "desks", "a.b", "README.md"), "# a.b\n")
        sh(["git", "init", "-q"], spaced)
        r = desk(spaced, "open", "a.b")
        self.assertEqual(r.returncode, 8, r.stderr)
        cmd = r.stderr.split("(", 1)[1].split("), then", 1)[0]
        self.assertIn(shlex.quote(os.path.join(spaced, "desks")), cmd)
        sh(["bash", "-c", cmd], spaced)  # the printed command, run as pasted, does the rename
        self.assertTrue(os.path.isdir(os.path.join(spaced, "desks", "a-b")))

    def test_status_warns_and_carries_on(self):
        self.topic("a.b")
        r = desk(self.root, "status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("warning: a.b/ is not in the form desk.py opens", r.stdout)


if __name__ == "__main__":
    unittest.main()
