"""desk.py against real scratch repositories. Standard library only.

    python3 -m unittest discover tests
"""
import os
import json
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

DESK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "desk", "scripts", "desk.py")
BLOCK = "# Mine\n\nMy own rule.\n\n<!-- desk:start -->\n## Desk\n\nA paragraph.\n\n- Desk root: `desks/`\n- Version: 0\n<!-- desk:end -->\n"


def put(path, text, mode="w"):
    with open(path, mode, encoding="utf-8") as f:
        f.write(text)


def get(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def sh(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def desk(cwd, *args):
    return sh([sys.executable, DESK, *args], cwd)


class Base(unittest.TestCase):
    git = True

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)
        put(os.path.join(self.root, "CLAUDE.md"), BLOCK)
        if self.git:
            for a in (["init", "-q", "-b", "main"], ["config", "user.email", "t@example.invalid"],
                      ["config", "user.name", "t"], ["add", "CLAUDE.md"], ["commit", "-qm", "init"]):
                self.assertEqual(sh(["git", *a], self.root).returncode, 0)

        # what the user confirmed lives outside the folder; keep the tests out of the real one
        self._conf = tempfile.TemporaryDirectory()
        self._old_conf = os.environ.get("DESK_CONFIG_DIR")
        os.environ["DESK_CONFIG_DIR"] = self._conf.name

    def tearDown(self):
        if self._old_conf is None:
            os.environ.pop("DESK_CONFIG_DIR", None)
        else:
            os.environ["DESK_CONFIG_DIR"] = self._old_conf
        self._conf.cleanup()
        self._tmp.cleanup()

    def block_line(self, line):
        """A line that reached the block without `desk.py set`: by hand, a clone or a pull."""
        p = os.path.join(self.root, "CLAUDE.md")
        put(p, get(p).replace("<!-- desk:end -->", line + "\n<!-- desk:end -->"))
        if self.git:
            self.assertEqual(sh(["git", "commit", "-qam", "block"], self.root).returncode, 0)

    def work(self, topic):
        return os.path.join(self.root, ".claude", "worktrees", f"desk-{topic}") if self.git else self.root

    def fill(self, topic, root="desks"):
        """What a session does before closing: fill the README, write a note, save."""
        folder = os.path.join(self.work(topic), root, topic)
        p = os.path.join(folder, "README.md")
        put(p, re.sub(r"\{\{[^}]*\}\}", "x", get(p)))
        put(os.path.join(folder, "sessions", "2026-01-01-first.md"), "# note\n")
        if self.git:
            sh(["git", "add", root], self.work(topic))
            self.assertEqual(sh(["git", "commit", "-qm", "desk"], self.work(topic)).returncode, 0)
        return folder


class FolderLevel(Base):
    git = False

    def test_open_creates_topic_without_git(self):
        r = desk(self.root, "open", "Sell Camera!")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("level:  folder", r.stdout)
        self.assertIn("topic:  sell-camera (new)", r.stdout)
        for f in ("README.md", "decisions.md", "sessions", "reviews"):
            self.assertTrue(os.path.exists(os.path.join(self.root, "desks", "sell-camera", f)), f)

    def test_open_twice_continues_and_keeps_the_readme(self):
        desk(self.root, "open", "trip")
        p = os.path.join(self.root, "desks", "trip", "README.md")
        put(p, "\nMINE\n", "a")
        r = desk(self.root, "open", "trip")
        self.assertIn("(continued)", r.stdout)
        self.assertIn("MINE", get(p))

    def test_close_refuses_without_a_session_note(self):
        desk(self.root, "open", "trip")
        r = desk(self.root, "close", "trip", "--merge")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no session note", r.stderr)

    def test_close_refuses_placeholders_then_passes(self):
        desk(self.root, "open", "trip")
        folder = os.path.join(self.root, "desks", "trip")
        put(os.path.join(folder, "sessions", "2026-01-01-a.md"), "# n\n")
        r = desk(self.root, "close", "trip", "--merge")
        self.assertIn("unfilled placeholders", r.stderr)
        self.fill("trip")
        self.assertEqual(desk(self.root, "close", "trip", "--merge").returncode, 0)

    def test_close_refuses_an_empty_readme(self):
        desk(self.root, "open", "trip")
        folder = self.fill("trip")
        put(os.path.join(folder, "README.md"), "\n")
        r = desk(self.root, "close", "trip", "--merge")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is empty", r.stderr)

    def test_close_of_an_unknown_topic_says_so(self):
        r = desk(self.root, "close", "nope", "--merge")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no topic 'nope'", r.stderr)

    def test_empty_topic_name_is_refused(self):
        self.assertEqual(desk(self.root, "open", "!!!").returncode, 2)


class GitLevel(Base):
    def test_open_makes_a_branch_and_working_copy_and_leaves_main_alone(self):
        r = desk(self.root, "open", "trip")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("level:  git", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.work("trip"), "desks", "trip", "README.md")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "desks")))
        self.assertEqual(sh(["git", "status", "--porcelain"], self.root).stdout, "")  # working copies are excluded
        self.assertEqual(sh(["git", "branch", "--show-current"], self.root).stdout.strip(), "main")

    def test_open_twice_reattaches(self):
        desk(self.root, "open", "trip")
        r = desk(self.root, "open", "trip")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("(continued)", r.stdout)

    def test_close_refuses_unsaved_files(self):
        desk(self.root, "open", "trip")
        folder = os.path.join(self.work("trip"), "desks", "trip")
        p = os.path.join(folder, "README.md")
        put(p, re.sub(r"\{\{[^}]*\}\}", "x", get(p)))
        put(os.path.join(folder, "sessions", "2026-01-01-a.md"), "# n\n")
        r = desk(self.root, "close", "trip", "--merge")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("uncommitted", r.stderr)

    def test_close_merges_tidies_and_prints_the_undo(self):
        desk(self.root, "open", "trip")
        self.fill("trip")
        r = desk(self.root, "close", "trip", "--merge", "--title", "Trip First Plan")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"to undo this whole desk later: git revert -m 1 [0-9a-f]{7,}")
        self.assertTrue(os.path.isfile(os.path.join(self.root, "desks", "trip", "README.md")))
        self.assertFalse(os.path.exists(self.work("trip")))
        self.assertNotIn("desk/trip", sh(["git", "branch"], self.root).stdout)
        self.assertIn("desk Trip First Plan", sh(["git", "log", "--oneline", "-1"], self.root).stdout)

    def test_the_undo_really_undoes(self):
        desk(self.root, "open", "trip")
        self.fill("trip")
        out = desk(self.root, "close", "trip", "--merge").stdout
        sha = re.search(r"git revert -m 1 ([0-9a-f]+)", out).group(1)
        self.assertEqual(sh(["git", "revert", "--no-edit", "-m", "1", sha], self.root).returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.root, "desks", "trip")))

    def test_close_refuses_when_main_has_half_finished_changes_and_changes_nothing(self):
        desk(self.root, "open", "trip")
        self.fill("trip")
        put(os.path.join(self.root, "CLAUDE.md"), "edit\n", "a")
        r = desk(self.root, "close", "trip", "--merge")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Nothing was changed", r.stderr)
        self.assertTrue(os.path.exists(self.work("trip")))

    def test_a_conflicting_merge_is_undone(self):
        desk(self.root, "open", "trip")
        folder = self.fill("trip")
        os.makedirs(os.path.join(self.root, "desks", "trip"))
        put(os.path.join(self.root, "desks", "trip", "README.md"), "other\n")
        self.assertEqual(sh(["git", "add", "desks"], self.root).returncode, 0)
        c = sh(["git", "commit", "-qm", "clash"], self.root)
        self.assertEqual(c.returncode, 0, c.stdout + c.stderr)
        r = desk(self.root, "close", "trip", "--merge")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("was undone", r.stderr)
        self.assertEqual(sh(["git", "status", "--porcelain"], self.root).stdout, "")
        self.assertTrue(os.path.isdir(folder))

    def test_pr_close_without_github_is_refused(self):
        desk(self.root, "open", "trip")
        self.fill("trip")
        r = desk(self.root, "close", "trip", "--pr")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no GitHub remote", r.stderr)

    def test_two_desks_side_by_side_both_merge(self):
        for t in ("a", "b"):
            desk(self.root, "open", t)
            self.fill(t)
        for t in ("a", "b"):
            self.assertEqual(desk(self.root, "close", t, "--merge").returncode, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "desks", "b", "README.md")))

    def test_notes_from_two_desks_for_one_topic_never_collide(self):
        for t in ("a", "b"):
            desk(self.root, "open", t)
            r = desk(self.root, "note", t, "taxes", f"from {t}")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.fill(t)
        for t in ("a", "b"):
            self.assertEqual(desk(self.root, "close", t, "--merge").returncode, 0)
        inbox = os.path.join(self.root, "desks", "taxes", "inbox")
        self.assertEqual(len(os.listdir(inbox)), 2)
        self.assertIn("notes waiting: taxes (2)", desk(self.root, "status").stdout)
        self.assertIn("inbox:  2 note(s)", desk(self.root, "open", "taxes").stdout)

    def test_tidy_keeps_unmerged_work(self):
        desk(self.root, "open", "trip")
        self.fill("trip")
        desk(self.root, "tidy")
        self.assertTrue(os.path.exists(self.work("trip")))


class Settings(Base):
    def block(self):
        return get(os.path.join(self.root, "CLAUDE.md"))

    def test_set_replaces_one_line_and_keeps_everything_else(self):
        self.assertEqual(desk(self.root, "set", "Close", "merge").returncode, 0)
        self.assertEqual(desk(self.root, "set", "Close", "review").returncode, 0)
        text = self.block()
        self.assertIn("- Close: review", text)
        self.assertNotIn("- Close: merge", text)
        self.assertIn("My own rule.", text)
        self.assertIn("A paragraph.\n\n- Desk root", text)  # the blank line survives
        self.assertTrue(text.rstrip().endswith("<!-- desk:end -->"))

    def test_add_keeps_earlier_lines_and_does_not_duplicate(self):
        for v in ("one", "two", "two"):
            desk(self.root, "add", "Setup", v)
        self.assertEqual(self.block().count("- Setup:"), 2)

    def test_set_saves_only_claude_md(self):
        put(os.path.join(self.root, "other.txt"), "x")
        sh(["git", "add", "other.txt"], self.root)
        desk(self.root, "set", "Close", "merge")
        self.assertIn("other.txt", sh(["git", "status", "--porcelain"], self.root).stdout)
        self.assertEqual(sh(["git", "show", "--stat", "--format=", "HEAD"], self.root).stdout.count("|"), 1)

    def test_desk_root_setting_moves_the_topics(self):
        desk(self.root, "set", "Desk root", "clients/")
        r = desk(self.root, "open", "acme")
        self.assertIn(os.path.join("clients", "acme"), r.stdout)

    def test_an_existing_readme_is_kept_and_flagged(self):
        os.makedirs(os.path.join(self.root, "desks", "acme"))
        put(os.path.join(self.root, "desks", "acme", "README.md"), "# Acme\n\nTheirs.\n")
        sh(["git", "add", "desks"], self.root)
        sh(["git", "commit", "-qm", "theirs"], self.root)
        r = desk(self.root, "open", "acme")
        self.assertIn("(continued)", r.stdout)
        self.assertIn("readme:", r.stdout)
        self.assertIn("Theirs.", get(os.path.join(self.work("acme"), "desks", "acme", "README.md")))

    def test_git_off_falls_back_to_folders(self):
        desk(self.root, "set", "Git", "off")
        self.assertIn("level:  folder", desk(self.root, "open", "trip").stdout)

    def test_a_local_block_wins_and_the_shared_file_is_never_touched(self):
        shared = get(os.path.join(self.root, "CLAUDE.md"))
        local = os.path.join(self.root, "CLAUDE.local.md")
        put(local, "<!-- desk:start -->\n## Desk\n\n- Desk root: `mine/`\n- Git: off\n<!-- desk:end -->\n")
        r = desk(self.root, "open", "trip")
        self.assertIn("level:  folder", r.stdout)
        self.assertIn(os.path.join("mine", "trip"), r.stdout)
        self.assertEqual(desk(self.root, "set", "Close", "merge").returncode, 0)
        self.assertIn("- Close: merge", get(local))
        self.assertEqual(get(os.path.join(self.root, "CLAUDE.md")), shared)
        self.assertEqual(sh(["git", "log", "--oneline"], self.root).stdout.count("\n"), 1)  # nothing saved to their history

    def test_set_without_a_block_is_refused(self):
        put(os.path.join(self.root, "CLAUDE.md"), "# nothing\n")
        self.assertNotEqual(desk(self.root, "set", "Close", "merge").returncode, 0)


class HouseClose(Base):
    """The folder has its own closing routine: that routine is the close."""
    git = False
    RAN = "printf '%s' \"$DESK_TOPIC\" > house-ran"

    def ready(self, topic="a"):
        desk(self.root, "open", topic)
        return self.fill(topic)

    def test_a_confirmed_routine_runs_and_the_script_writes_nothing(self):
        folder = self.ready()
        self.assertEqual(desk(self.root, "set", "Close", "house run " + self.RAN).returncode, 0)
        before = sorted(os.listdir(os.path.join(folder, "sessions")))
        r = desk(self.root, "close", "a")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(get(os.path.join(self.root, "house-ran")), "a")  # it ran, from the main folder, knowing the topic
        self.assertEqual(sorted(os.listdir(os.path.join(folder, "sessions"))), before)
        self.assertIn("wrote nothing", r.stdout)

    def test_a_failing_routine_stops_the_close(self):
        self.ready()
        desk(self.root, "set", "Close", "house run exit 7")
        r = desk(self.root, "close", "a")
        self.assertEqual(r.returncode, 1)
        self.assertIn("failed (exit 7)", r.stderr)
        self.assertNotIn("closed with", r.stdout)

    def test_a_routine_that_waits_for_an_answer_fails_instead_of_hanging(self):
        self.ready()
        desk(self.root, "set", "Close", "house run read answer")
        self.assertEqual(desk(self.root, "close", "a").returncode, 1)

    def test_a_line_the_user_never_confirmed_does_not_run(self):
        self.ready()
        self.block_line("- Close: house run " + self.RAN)
        r = desk(self.root, "close", "a")
        self.assertEqual(r.returncode, 1)
        self.assertIn("has not been confirmed", r.stderr)
        self.assertIn(self.RAN, r.stderr)  # the exact text, so the user can be shown it
        hint = [x for x in r.stderr.splitlines() if "desk.py set Close" in x][0]  # and a command safe to paste
        self.assertEqual(shlex.split(hint)[-1], "house run " + self.RAN)
        self.assertFalse(os.path.exists(os.path.join(self.root, "house-ran")))

    def test_a_backslash_in_the_command_is_kept_as_written(self):
        self.ready()
        desk(self.root, "set", "Close", "merge")  # so the next set replaces a line instead of adding one
        cmd = "printf 'a\\n' > house-ran"
        self.assertEqual(desk(self.root, "set", "Close", "house run " + cmd).returncode, 0)
        self.assertIn("- Close: house run " + cmd + "\n", get(os.path.join(self.root, "CLAUDE.md")))
        self.assertEqual(desk(self.root, "close", "a").returncode, 0)
        self.assertEqual(get(os.path.join(self.root, "house-ran")), "a\n")

    def test_a_setting_of_two_lines_is_refused(self):
        r = desk(self.root, "set", "Close", "house run true\n- Git: off")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Git: off", get(os.path.join(self.root, "CLAUDE.md")))

    def test_a_procedure_outside_the_folder_is_refused(self):
        self.ready()
        outside = os.path.join(self._conf.name, "steps.md")
        put(outside, "do things\n")
        for path in (outside, os.path.join("..", os.path.basename(self._conf.name), "steps.md")):
            r = desk(self.root, "set", "Close", "house follow " + path)
            self.assertEqual(r.returncode, 2, path)
            self.assertIn("outside this folder", r.stderr)
        self.assertNotIn("Close:", get(os.path.join(self.root, "CLAUDE.md")))

    def test_changing_the_close_forgets_the_old_yes(self):
        self.ready()
        desk(self.root, "set", "Close", "house run " + self.RAN)
        desk(self.root, "set", "Close", "merge")
        self.block_line("- Close: house run " + self.RAN)  # the old line comes back with a pull
        p = os.path.join(self.root, "CLAUDE.md")
        put(p, get(p).replace("- Close: merge\n", ""))
        r = desk(self.root, "close", "a")
        self.assertEqual(r.returncode, 1)
        self.assertIn("has not been confirmed", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.root, "house-ran")))

    def test_an_unreadable_list_of_confirmations_is_not_replaced(self):
        store = os.path.join(self._conf.name, "house-close.json")
        for broken in ("{not json", "[]"):
            put(store, broken)
            r = desk(self.root, "set", "Close", "house run true")
            self.assertNotEqual(r.returncode, 0, broken)
            self.assertEqual(get(store), broken)
            self.assertNotIn("Close:", get(os.path.join(self.root, "CLAUDE.md")))
            self.ready()
            self.block_line("- Close: house run " + self.RAN)
            self.assertEqual(desk(self.root, "close", "a").returncode, 1)  # and nothing runs on it
            p = os.path.join(self.root, "CLAUDE.md")
            put(p, get(p).replace("- Close: house run " + self.RAN + "\n", ""))

    def test_a_line_changed_only_in_its_backticks_does_not_run(self):
        self.ready()
        desk(self.root, "set", "Close", "house run `" + self.RAN + "`")
        p = os.path.join(self.root, "CLAUDE.md")
        put(p, get(p).replace("house run `" + self.RAN + "`", "house run " + self.RAN))
        r = desk(self.root, "close", "a")
        self.assertEqual(r.returncode, 1)
        self.assertIn("has not been confirmed", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.root, "house-ran")))

    def test_a_line_changed_after_it_was_confirmed_does_not_run(self):
        self.ready()
        desk(self.root, "set", "Close", "house run true")
        p = os.path.join(self.root, "CLAUDE.md")
        put(p, get(p).replace("house run true", "house run " + self.RAN))
        r = desk(self.root, "close", "a")
        self.assertEqual(r.returncode, 1)
        self.assertIn("house run true", r.stderr)  # says what was confirmed
        self.assertFalse(os.path.exists(os.path.join(self.root, "house-ran")))

    def test_a_flag_does_not_override_the_routine(self):
        self.ready()
        desk(self.root, "set", "Close", "house run " + self.RAN)
        for flag in ("--merge", "--pr"):
            r = desk(self.root, "close", "a", flag)
            self.assertEqual(r.returncode, 1)
            self.assertIn("does not override", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.root, "house-ran")))

    def test_a_close_line_that_is_not_understood_stops_instead_of_being_ignored(self):
        self.ready()
        self.block_line("- Close: our own way, see the handbook")
        for args in (("close", "a"), ("close", "a", "--merge")):
            r = desk(self.root, *args)
            self.assertEqual(r.returncode, 1)
            self.assertIn("not one this script understands", r.stderr)
        self.assertEqual(desk(self.root, "set", "Close", "sometimes").returncode, 2)
        self.assertNotIn("sometimes", get(os.path.join(self.root, "CLAUDE.md")))

    def test_a_command_written_in_backticks_is_read(self):
        self.ready()
        desk(self.root, "set", "Close", "house run `" + self.RAN + "`")
        self.assertEqual(desk(self.root, "close", "a").returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(self.root, "house-ran")))

    def test_the_gate_on_desk_notes_comes_before_the_routine(self):
        desk(self.root, "open", "a")  # README still has its placeholders, no session note
        desk(self.root, "set", "Close", "house run " + self.RAN)
        self.assertEqual(desk(self.root, "close", "a").returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(self.root, "house-ran")))

    def test_follow_runs_nothing_and_says_it_checked_nothing(self):
        self.ready()
        put(os.path.join(self.root, "closing.md"), "1. Do the thing.\n")
        desk(self.root, "set", "Close", "house follow closing.md")
        r = desk(self.root, "close", "a")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("not checked by this script", r.stdout)

    def test_follow_refuses_a_procedure_that_is_not_there(self):
        self.ready()
        desk(self.root, "set", "Close", "house follow closing.md")
        r = desk(self.root, "close", "a")
        self.assertEqual(r.returncode, 1)
        self.assertIn("is not there", r.stderr)

    def test_a_long_session_note_is_warned_about_not_refused(self):
        folder = self.ready()
        put(os.path.join(folder, "sessions", "2026-01-01-first.md"), "line\n" * 21)
        desk(self.root, "set", "Close", "house run true")
        r = desk(self.root, "close", "a")
        self.assertEqual(r.returncode, 0)
        self.assertIn("21 lines", r.stdout)

    def test_a_recorded_merge_or_review_needs_no_flag(self):
        self.ready()
        self.assertEqual(desk(self.root, "close", "a").returncode, 2)  # nothing recorded, nothing passed
        desk(self.root, "set", "Close", "merge")
        self.assertEqual(desk(self.root, "close", "a").returncode, 0)


class HouseCloseWithGit(Base):
    def test_a_recorded_review_opens_a_pull_request_and_never_merges(self):
        desk(self.root, "open", "a")
        folder = self.fill("a")
        desk(self.root, "set", "Close", "review")
        r = desk(self.root, "close", "a")
        self.assertNotEqual(r.returncode, 0)  # no GitHub here, so the pull request path stops
        self.assertIn("no GitHub remote", r.stderr)
        self.assertTrue(os.path.isdir(folder))  # the working copy is still there
        self.assertNotIn("Merge", sh(["git", "log", "--oneline", "main"], self.root).stdout)  # and nothing was merged

    def test_desk_does_no_git_of_its_own(self):
        desk(self.root, "open", "a")
        self.fill("a")
        desk(self.root, "set", "Close", "house run true")
        head = sh(["git", "rev-parse", "HEAD"], self.root).stdout
        put(os.path.join(self.work("a"), "unsaved.txt"), "x")  # saving is the routine's business now
        r = desk(self.root, "close", "a")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sh(["git", "rev-parse", "HEAD"], self.root).stdout, head)  # nothing merged
        self.assertTrue(os.path.isdir(self.work("a")))  # working copy left alone
        self.assertIn("desk/a", sh(["git", "branch"], self.root).stdout)

    def test_git_off_with_a_remark_is_still_off(self):
        self.block_line("- Git: off (this folder makes its own branches)")
        r = desk(self.root, "open", "a")
        self.assertIn("level:  folder", r.stdout)
        self.assertNotIn("desk/a", sh(["git", "branch"], self.root).stdout)


class Messages(Base):
    """What the script says when something is missing: enough to fix it in one go."""
    git = False

    def test_help_is_not_an_error(self):
        for h in ("--help", "-h"):
            r = desk(self.root, h)
            self.assertEqual(r.returncode, 0)
            self.assertIn("open", r.stdout)
        self.assertEqual(desk(self.root).returncode, 2)

    def test_status_does_not_show_a_placeholder_as_the_next_step(self):
        desk(self.root, "open", "a")
        r = desk(self.root, "status")
        self.assertIn("no next step written yet", r.stdout)
        self.assertNotIn("{{", r.stdout)

    def test_close_names_the_template_and_lists_every_placeholder_at_once(self):
        desk(self.root, "open", "a")
        r = desk(self.root, "close", "a", "--merge")
        self.assertIn(os.path.join("templates", "session.md"), r.stderr)
        self.assertIn(os.path.join("desks", "a", "sessions"), r.stderr)
        folder = os.path.join(self.root, "desks", "a")
        put(os.path.join(folder, "sessions", "2026-01-01-first.md"), "# note {{title}}\n")
        r = desk(self.root, "close", "a", "--merge")
        self.assertIn("README.md", r.stderr)
        self.assertIn("2026-01-01-first.md", r.stderr)

    def test_a_repository_with_no_commit_says_why_it_is_folder_level(self):
        sh(["git", "init", "-q"], self.root)
        r = desk(self.root, "status")
        self.assertIn("no commit yet", r.stdout)


class GitIdentity(Base):
    def test_no_git_identity_is_not_called_a_conflict(self):
        desk(self.root, "open", "a")
        self.fill("a")
        for k in ("user.name", "user.email"):
            sh(["git", "config", "--unset", k], self.root)
        sh(["git", "config", "user.useConfigOnly", "true"], self.root)
        old = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")}
        os.environ.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        try:
            r = desk(self.root, "close", "a", "--merge")
        finally:
            for k, v in old.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not know who you are", r.stderr)
        self.assertNotIn("conflicts", r.stderr)


class HouseOpen(Base):
    """#28: a folder that opens topics its own way gets no second home for the topic from Desks."""

    def snapshot(self):
        return sorted(os.path.relpath(os.path.join(d, f), self.root)
                      for d, _, fs in os.walk(self.root) if ".git" not in d.split(os.sep) for f in fs)

    def test_follow_creates_nothing_and_says_where_to_look(self):
        put(os.path.join(self.root, "opening.md"), "1. Run our opener.\n")
        self.assertEqual(desk(self.root, "set", "Open", "house follow opening.md").returncode, 0)
        before, branches = self.snapshot(), sh(["git", "branch"], self.root).stdout
        r = desk(self.root, "open", "a")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("follow opening.md", r.stdout)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(sh(["git", "branch"], self.root).stdout, branches)

    def test_an_unknown_open_line_stops(self):
        put(os.path.join(self.root, "CLAUDE.md"), BLOCK.replace("- Version: 0", "- Version: 0\n- Open: our way"))
        r = desk(self.root, "open", "a")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not one this script understands", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.root, "desks", "a")))

    def test_a_missing_procedure_stops_and_set_refuses_outside(self):
        put(os.path.join(self.root, "CLAUDE.md"), BLOCK.replace("- Version: 0", "- Version: 0\n- Open: house follow gone.md"))
        self.assertEqual(desk(self.root, "open", "a").returncode, 1)
        self.assertEqual(desk(self.root, "set", "Open", "house follow ../elsewhere.md").returncode, 2)

    def test_note_goes_where_the_session_works_or_stops(self):
        put(os.path.join(self.root, "opening.md"), "1. Run our opener.\n")
        desk(self.root, "set", "Open", "house follow opening.md")
        r = desk(self.root, "note", "a", "b", "something for b")
        self.assertEqual(r.returncode, 1)
        self.assertIn("keeps its topics its own way", r.stderr)
        os.makedirs(os.path.join(self.root, "desks"))
        r = desk(self.root, "note", "a", "b", "something for b")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(os.listdir(os.path.join(self.root, "desks", "b", "inbox"))), 1)

    def test_without_the_line_open_is_unchanged(self):
        self.assertEqual(desk(self.root, "open", "a").returncode, 0)
        self.assertIn("desk/a", sh(["git", "branch"], self.root).stdout)


if __name__ == "__main__":
    unittest.main()
