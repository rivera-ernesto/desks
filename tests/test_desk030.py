"""Desks 0.3.0: one opener, hooks, labels from receipts, state only where versioned, the delegation
contract, receive, digest. Each guard has a negative control: the same step without the guard's
condition succeeds, so a pass is not an accident of the setup. Standard library only.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_desk import Base, desk, get, sh, DESK  # noqa: E402
import test_desk  # noqa: E402


def put(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    test_desk.put(path, text)

TRAILER = "Desk-Status: ready"
HERE = os.path.dirname(os.path.abspath(__file__))


def commit(cwd, msg, *paths):
    if paths:
        sh(["git", "add", *paths], cwd)
    r = sh(["git", "commit", "-q", "--allow-empty", "-m", msg], cwd)
    assert r.returncode == 0, r.stderr


class Topics(Base):
    def ready(self, topic, files=None, parent_cwd=None):
        """Open `topic`, give it work and a note, and hand it over: the trailer on the head."""
        r = desk(self.root, "open", topic)
        self.assertEqual(r.returncode, 0, r.stderr)
        work = self.work(topic)
        for name, text in (files or {f"{topic}.txt": "work\n"}).items():
            os.makedirs(os.path.dirname(os.path.join(work, name)) or work, exist_ok=True)
            put(os.path.join(work, name), text)
            sh(["git", "add", name], work)
        self.fill(topic)
        commit(work, f"desk: {topic} ready\n\n{TRAILER}")
        return work

    def branches(self):
        return sh(["git", "branch", "--format=%(refname:short)"], self.root).stdout.split()


class OneOpener(Topics):
    def test_open_cuts_from_the_configured_base_and_prints_the_working_copy(self):
        remote = tempfile.mkdtemp()
        sh(["git", "init", "-q", "--bare", remote], remote)
        sh(["git", "remote", "add", "origin", remote], self.root)
        sh(["git", "push", "-q", "origin", "main:development"], self.root)
        put(os.path.join(self.root, "later.txt"), "x")  # local main moves on; development does not
        commit(self.root, "later", "later.txt")
        self.block_line("- Base: origin/development")
        r = desk(self.root, "open", "a")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"worktree: {self.work('a')}", r.stdout)
        dev = sh(["git", "rev-parse", "origin/development"], self.root).stdout
        self.assertEqual(sh(["git", "rev-parse", "desk/a"], self.root).stdout, dev)
        self.assertNotEqual(dev, sh(["git", "rev-parse", "main"], self.root).stdout)  # not cut from the checked-out branch

    def test_a_missing_base_refuses_instead_of_falling_back(self):
        self.block_line("- Base: origin/development")
        r = desk(self.root, "open", "a")
        self.assertEqual(r.returncode, 3)
        self.assertNotIn("desk/a", self.branches())

    def test_a_branch_prefix_is_configurable(self):
        self.block_line("- Branch prefix: topic/")
        self.assertEqual(desk(self.root, "open", "a").returncode, 0)
        self.assertIn("topic/a", self.branches())

    def test_nothing_is_created_in_the_main_folder(self):
        desk(self.root, "open", "a")
        self.assertFalse(os.path.exists(os.path.join(self.root, "desks")))

    def test_a_received_topic_is_not_reopened_at_its_old_head(self):
        self.ready("a")
        sh(["git", "merge", "-q", "--no-ff", "desk/a", "-m", "m"], self.root)
        sh(["git", "worktree", "remove", "--force", self.work("a")], self.root)
        r = desk(self.root, "open", "a")
        self.assertEqual(r.returncode, 4)
        self.assertIn("desk.py open a-2", r.stderr)

    def test_control_a_branch_without_the_trailer_reattaches(self):
        self.assertEqual(desk(self.root, "open", "a").returncode, 0)
        sh(["git", "worktree", "remove", "--force", self.work("a")], self.root)
        r = desk(self.root, "open", "a")  # merged or not, it was never handed over
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_closed_unmerged_topic_needs_one_explicit_yes(self):
        self.ready("a")
        sh(["git", "worktree", "remove", "--force", self.work("a")], self.root)
        r = desk(self.root, "open", "a")
        self.assertEqual(r.returncode, 5)
        self.assertIn("--reopen", r.stderr)
        self.assertEqual(desk(self.root, "open", "a", "--reopen").returncode, 0)

    def test_a_renamed_closed_branch_is_the_same_topic(self):
        self.ready("a")
        sh(["git", "branch", "-m", "desk/a", "desk/a--some-title"], self.work("a"))
        r = desk(self.root, "open", "a")  # already open in its working copy: says where, does not make a second
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sh(["git", "worktree", "list"], self.root).stdout.count("desk-a"), 1)

    def test_close_finds_the_topic_from_the_working_copy(self):
        desk(self.root, "set", "Close", "house run true")
        desk(self.root, "open", "a")
        self.fill("a")
        put(os.path.join(self.root, "x"), "")  # an unrelated file in the main folder changes nothing
        r = desk(self.work("a"), "close")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Closed line: Desk `a` closed", r.stdout)


class Lock(Topics):
    def lock(self, pid, at):
        d = os.path.join(self.root, ".git", "desk-state")
        os.makedirs(d, exist_ok=True)
        put(os.path.join(d, "open.lock"), f"{pid} {at}")

    def test_a_live_fresh_lock_holds_and_nothing_changes(self):
        self.lock(os.getpid(), int(time.time()))
        r = subprocess.run([sys.executable, DESK, "open", "a"], cwd=self.root, capture_output=True, text=True,
                           env=dict(os.environ, DESK_LOCK_WAIT="1"))
        self.assertEqual(r.returncode, 6)
        self.assertIn("lock", r.stderr)
        self.assertNotIn("desk/a", self.branches())

    def test_control_without_the_lock_the_same_open_succeeds(self):
        self.assertEqual(desk(self.root, "open", "a").returncode, 0)

    def test_a_lock_of_a_dead_process_is_reclaimed(self):
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        self.lock(p.pid, int(time.time()))
        self.assertEqual(desk(self.root, "open", "a").returncode, 0)

    def test_a_lock_older_than_ten_minutes_is_reclaimed_even_when_its_pid_lives(self):
        self.lock(os.getpid(), int(time.time()) - 601)
        self.assertEqual(desk(self.root, "open", "a").returncode, 0)

    def test_parallel_opens_all_succeed(self):
        procs = [subprocess.Popen([sys.executable, DESK, "open", f"t{i}"], cwd=self.root, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) for i in range(5)]
        codes = [p.wait() for p in procs]
        self.assertEqual(codes, [0] * 5, [p.stderr.read() for p in procs])
        self.assertEqual(len([b for b in self.branches() if b.startswith("desk/t")]), 5)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".git", "desk-state", "open.lock")))


class Hooks(Topics):
    def test_an_open_command_runs_only_in_the_form_the_user_confirmed(self):
        self.block_line("- Open: house run echo opened-$DESK_TOPIC")
        r = desk(self.root, "open", "a")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not been confirmed", r.stderr)
        self.assertNotIn("opened-a", r.stdout)
        desk(self.root, "set", "Open", "house run echo opened-$DESK_TOPIC")
        r = desk(self.root, "open", "a")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("opened-a", r.stdout)
        self.assertNotIn("desk/a", self.branches())  # Desks made no second home

    def test_a_house_close_names_what_the_routine_owns_and_warns_without_the_trailer(self):
        self.block_line("- House git: merge, push and rename")
        desk(self.root, "set", "Close", "house run true")
        desk(self.root, "open", "a")
        self.fill("a")
        r = desk(self.work("a"), "close")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("owns merge, push and rename", r.stdout)
        self.assertIn("carries no `Desk-Status: ready` line", r.stdout)
        self.assertIn("next step:", r.stdout)

    def test_get_prints_a_recorded_answer(self):
        self.block_line("- Base: origin/development")
        r = desk(self.root, "get", "Base")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "origin/development"))
        self.assertEqual(desk(self.root, "get", "Nothing").returncode, 1)


class Labels(Topics):
    """A reply label comes from a receipt, never from typing (item 4)."""

    def note(self, text):
        folder = self.fill("a")
        put(os.path.join(folder, "sessions", "2026-01-02-second.md"), text)
        sh(["git", "add", "desks"], self.work("a"))
        commit(self.work("a"), "note")

    def receipt(self, label, closed=None, packet_text="the packet\n"):
        d = os.path.join(self._conf.name, "r")
        os.makedirs(d, exist_ok=True)
        packet = os.path.join(d, "p.md")
        put(packet, packet_text)
        import hashlib
        disp = os.path.join(d, "p-dispositions.md")
        if closed is not None:
            put(disp, "| # | finding | disposition |\n|---|---|---|\n| 1 | a | " + ("adopted" if closed else "TODO") + " |\n")
        rid = "abcdef0123"
        put(os.path.join(d, f"receipt-{rid}.txt"), f"receipt {rid}\npacket {packet}\npacket_sha256 {hashlib.sha256(packet_text.encode()).hexdigest()}\n"
            f"label {label}\nfamilies_answered 3\nfamilies a b c\ndispositions {disp}\n")
        put(os.path.join(self._conf.name, "receipts.tsv"), f"{rid}\t{os.path.join(d, 'receipt-' + rid + '.txt')}\n")
        return rid

    def close(self):
        self.block_line("- Close: house run true")
        desk(self.root, "set", "Close", "house run true")
        return desk(self.work("a"), "close")

    def start(self):
        desk(self.root, "open", "a")

    def test_a_converged_label_without_a_receipt_is_refused(self):
        self.start()
        self.note("# n\n\nReview: [converged] · 3 families\n")
        r = self.close()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("has no receipt", r.stderr)
        self.assertNotIn("Closed line", r.stdout)

    def test_a_receipt_that_does_not_exist_is_refused(self):
        self.start()
        self.note("# n\n\nReview: [converged] · 3 families · receipt 0123456789\n")
        self.assertIn("was not found", self.close().stderr)

    def test_converged_needs_every_disposition_control_it_passes_when_closed(self):
        self.start()
        rid = self.receipt("open", closed=False)
        self.note(f"# n\n\nReview: [converged] · 3 families · receipt {rid}\n")
        r = self.close()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("open", r.stderr)
        self.receipt("open", closed=True)
        r = desk(self.work("a"), "close")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_label_for_a_packet_that_changed_is_refused(self):
        self.start()
        rid = self.receipt("open", closed=True)
        put(os.path.join(self._conf.name, "r", "p.md"), "changed after the review\n")
        self.note(f"# n\n\nReview: [converged] · 3 families · receipt {rid}\n")
        self.assertIn("stale", self.close().stderr)

    def test_same_vendor_and_unreviewed_need_no_receipt(self):
        self.start()
        self.note("# n\n\nReview: [same-vendor]\nReview: [unreviewed]\n")
        self.assertEqual(self.close().returncode, 0)

    def test_quick_no_loop_is_refused_unless_the_profile_lists_it(self):
        self.start()
        self.note("# n\n\nReview: [quick: no loop]\n")
        r = self.close()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not skippable by the session", r.stderr)
        self.block_line("- Quick loop: allowed")
        self.assertEqual(desk(self.work("a"), "close").returncode, 0)


class Lessons(Topics):
    def run_close(self, lesson, extra=""):
        self.block_line("- Close: house run true")
        desk(self.root, "set", "Close", "house run true")
        desk(self.root, "open", "a")
        folder = self.fill("a")
        put(os.path.join(folder, "sessions", "2026-01-02-second.md"), f"# n\n\n## Lessons\n\n{lesson}\n{extra}")
        return desk(self.work("a"), "close")

    def test_a_lesson_with_no_destination_is_refused(self):
        r = self.run_close("- the gate fires twice")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("without a destination", r.stderr)

    def test_each_destination_form_is_accepted(self):
        for ok in ("- one → topic", "- two → issue #12", "- three → dropped: one-off", "- four -> topic"):
            self.assertEqual(self.run_close(ok).returncode, 0, ok)
            sh(["git", "worktree", "remove", "--force", self.work("a")], self.root)
            sh(["git", "branch", "-D", "desk/a"], self.root)

    def test_a_house_file_destination_must_exist(self):
        r = self.run_close("- five → house rules/missing.md")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is not there", r.stderr)

    def test_the_close_note_must_have_the_listed_sections(self):
        self.block_line("- Close sections: Done | Open items")
        r = self.run_close("- x → topic")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no section 'Done'", r.stderr)
        self.assertIn("no section 'Open items'", r.stderr)


class CloseNoteTemplate(Lessons):
    def test_the_template_the_folder_names_sets_the_required_sections(self):
        put(os.path.join(self.root, "tpl", "note.md"), "# {{title}}\n\n## Snapshot\n\n## Loose ends\n")
        commit(self.root, "tpl", "tpl/note.md")
        self.block_line("- Close note: tpl/note.md")
        r = self.run_close("- x → topic")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no section 'Snapshot'", r.stderr)
        self.assertIn("no section 'Loose ends'", r.stderr)

    def test_control_a_note_with_those_sections_closes(self):
        put(os.path.join(self.root, "tpl", "note.md"), "# t\n\n## Snapshot\n\n## Loose ends\n")
        commit(self.root, "tpl", "tpl/note.md")
        self.block_line("- Close note: tpl/note.md")
        self.run_close("- x → topic")  # opens the topic, writes a note without them
        put(os.path.join(self.work("a"), "desks", "a", "sessions", "2026-01-02-second.md"),
            "# n\n\n## Snapshot\n\nok\n\n## Loose ends\n\nnone\n\n## Lessons\n\n- x → topic\n")
        self.assertEqual(desk(self.work("a"), "close").returncode, 0)

    def test_a_template_that_is_not_there_is_named(self):
        self.block_line("- Close note: tpl/missing.md")
        self.assertIn("is not there", self.run_close("- x → topic").stderr)

    def test_listed_sections_win_over_the_template(self):
        put(os.path.join(self.root, "tpl", "note.md"), "## Snapshot\n")
        commit(self.root, "tpl", "tpl/note.md")
        self.block_line("- Close note: tpl/note.md")
        self.block_line("- Close sections: Lessons")
        self.assertEqual(self.run_close("- x → topic").returncode, 0)


class LivingMemoryTemplate(Lessons):
    """The opt-in Living Memory close note, with the personal section opt-in per user."""

    def ship(self, *names):
        for n in names:
            put(os.path.join(self.root, "tpl", n), get(os.path.join(os.path.dirname(HERE), "skills", "desk", "templates", n)))
        commit(self.root, "tpl", "tpl")

    def test_the_shipped_template_requires_its_headings_and_the_source_id(self):
        self.ship("living-memory.md")
        self.block_line("- Close note: tpl/living-memory.md")
        r = self.run_close("- x → topic")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no section 'What this was really about'", r.stderr)
        self.assertNotIn("Personal record", r.stderr)  # opt-in: not required unless the user listed it
        self.assertIn("Source ID / UUID", get(os.path.join(self.root, "tpl", "living-memory.md")))

    def test_listing_the_personal_file_makes_that_section_required(self):
        self.ship("living-memory.md", "living-memory-personal.md")
        self.block_line("- Close note: tpl/living-memory.md; tpl/living-memory-personal.md")
        self.assertIn("no section 'Personal record'", self.run_close("- x → topic").stderr)

    def test_the_template_credits_its_public_source_and_never_copies_transcripts(self):
        t = get(os.path.join(os.path.dirname(HERE), "skills", "desk", "templates", "living-memory.md"))
        self.assertIn("CC BY 4.0", t)
        self.assertIn("never copy the transcript", t)


class StateWhereVersioned(Topics):
    def test_open_refuses_a_desk_root_that_git_ignores(self):
        put(os.path.join(self.root, ".gitignore"), "desks/\n")
        commit(self.root, "ignore", ".gitignore")
        r = desk(self.root, "open", "a")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ignored by git", r.stderr)

    def test_control_a_tracked_desk_root_opens(self):
        self.assertEqual(desk(self.root, "open", "a").returncode, 0)

    def test_note_refuses_an_ignored_inbox(self):
        desk(self.root, "open", "a")
        put(os.path.join(self.work("a"), ".gitignore"), "inbox/\n")
        r = desk(self.work("a"), "note", "a", "b", "something came up")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ignored by git", r.stderr)

    def test_status_reports_state_the_main_folder_holds(self):
        put(os.path.join(self.root, "desks", "old", "README.md"), "# old\n")
        put(os.path.join(self.root, "desks", "old", "notes.md"), "state that no branch holds\n")
        r = desk(self.root, "status")
        self.assertIn("STATE OUTSIDE HISTORY", r.stdout)
        self.assertIn("notes.md", r.stdout)

    def test_migrate_copies_it_into_the_working_copy_and_never_overwrites(self):
        put(os.path.join(self.root, "desks", "a", "notes.md"), "old state\n")
        put(os.path.join(self.root, "desks", "a", "README.md"), "# a\n")
        desk(self.root, "open", "a")
        put(os.path.join(self.work("a"), "desks", "a", "README.md"), "# new\n")
        r = desk(self.root, "migrate", "a")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(get(os.path.join(self.work("a"), "desks", "a", "notes.md")), "old state\n")
        self.assertEqual(get(os.path.join(self.work("a"), "desks", "a", "README.md")), "# new\n")

    def test_pointers_only_seeds_the_readme_and_nothing_else(self):
        self.block_line("- Pointers only: yes")
        desk(self.root, "open", "a")
        self.assertEqual(sorted(os.listdir(os.path.join(self.work("a"), "desks", "a"))), ["README.md"])

    def test_the_session_notes_folder_is_configurable(self):
        self.block_line("- Sessions: notes/{topic}")
        self.block_line("- Close: house run true")
        desk(self.root, "set", "Close", "house run true")
        desk(self.root, "open", "a")
        self.assertEqual(desk(self.work("a"), "close").returncode, 2 - 1)  # no note in notes/a yet: refused
        put(os.path.join(self.work("a"), "notes", "a", "2026-01-01-x.md"), "# x\n")
        self.fill("a")
        os.remove(os.path.join(self.work("a"), "desks", "a", "sessions", "2026-01-01-first.md"))
        self.assertEqual(desk(self.work("a"), "close").returncode, 0)


class Children(Topics):
    def test_a_child_is_cut_from_its_parent_gets_a_brief_and_is_listed(self):
        self.block_line("- Usage reserve: 50")
        desk(self.root, "open", "p")
        put(os.path.join(self.work("p"), "parent.txt"), "p")
        commit(self.work("p"), "parent work", "parent.txt")
        r = desk(self.root, "open", "c", "--parent", "p")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.work("c"), "parent.txt")))  # it started from the parent's branch
        self.assertIn("usage reserve at this level: 50", r.stdout)
        brief = get(os.path.join(self.work("c"), "desks", "c", "brief.md"))
        self.assertIn("Opened by `p` at level 1", brief)
        self.assertIn("The user's words, verbatim", brief)
        head = sh(["git", "rev-parse", "--short=12", "desk/p"], self.root).stdout.strip()
        self.assertIn(f"commit `{head}`", brief)  # the plan is pinned to the parent's head
        out = desk(self.root, "children", "p").stdout
        self.assertIn("c  running  (child of p", out)

    def test_the_depth_cap_defaults_to_three_and_none_lifts_it(self):
        desk(self.root, "open", "t0")
        for i in range(1, 4):
            self.assertEqual(desk(self.root, "open", f"t{i}", "--parent", f"t{i - 1}").returncode, 0)
        r = desk(self.root, "open", "t4", "--parent", "t3")
        self.assertEqual(r.returncode, 7)
        self.assertIn("Depth cap", r.stderr)
        self.block_line("- Depth cap: none")
        self.assertEqual(desk(self.root, "open", "t4", "--parent", "t3").returncode, 0)

    def test_per_level_reserve_repeats_the_last_value(self):
        self.block_line("- Usage reserve: 50, 40")
        desk(self.root, "open", "t0")
        self.assertIn("reserve at this level: 50", desk(self.root, "open", "t1", "--parent", "t0").stdout)
        self.assertIn("reserve at this level: 40", desk(self.root, "open", "t2", "--parent", "t1").stdout)
        self.assertIn("reserve at this level: 40", desk(self.root, "open", "t3", "--parent", "t2").stdout)

    def test_a_child_is_received_into_its_parent_not_the_base(self):
        desk(self.root, "open", "p")
        self.ready("c0")  # a plain ready topic, to show it is not what the child lands in
        desk(self.root, "open", "c", "--parent", "p")
        put(os.path.join(self.work("c"), "child.txt"), "c")
        sh(["git", "add", "child.txt"], self.work("c"))
        self.fill("c")
        commit(self.work("c"), f"ready\n\n{TRAILER}")
        r = desk(self.root, "receive", "c")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("into desk/p", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.work("p"), "child.txt")))
        self.assertNotIn("child.txt", sh(["git", "ls-tree", "-r", "--name-only", "main"], self.root).stdout)


class Receive(Topics):
    def test_receive_lists_then_takes_a_ready_topic_in_and_tidies(self):
        self.ready("a")
        self.assertIn("ready: a", desk(self.root, "receive").stdout)
        r = desk(self.root, "receive", "a")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "a.txt")))  # the target's checked-out folder moved with it
        self.assertNotIn("desk/a", self.branches())
        self.assertFalse(os.path.exists(self.work("a")))
        self.assertEqual(desk(self.root, "receive", "a").returncode, 2)  # now there is nothing left to take

    def test_nothing_ready_is_exit_two(self):
        desk(self.root, "open", "a")
        self.assertEqual(desk(self.root, "receive").returncode, 2)
        self.assertEqual(desk(self.root, "receive", "a").returncode, 2)

    def test_a_failing_check_leaves_everything_untouched(self):
        self.block_line("- Receive checks: false")
        self.ready("a")
        main_before = sh(["git", "rev-parse", "main"], self.root).stdout
        branch_before = sh(["git", "rev-parse", "desk/a"], self.root).stdout
        r = desk(self.root, "receive", "a")
        self.assertEqual(r.returncode, 3)
        self.assertEqual(sh(["git", "rev-parse", "main"], self.root).stdout, main_before)  # the target did not move
        self.assertEqual(sh(["git", "rev-parse", "desk/a"], self.root).stdout, branch_before)  # nor the topic
        self.assertTrue(os.path.isdir(self.work("a")))
        self.assertNotIn("receive-tmp/a", self.branches())  # the scratch copy is gone
        self.assertFalse(os.path.exists(os.path.join(self.root, "a.txt")))
        self.assertIn("blocked: a:", desk(self.root, "digest").stdout)

    def test_control_the_same_topic_passes_when_the_check_passes(self):
        self.block_line("- Receive checks: true")
        self.ready("a")
        self.assertEqual(desk(self.root, "receive", "a").returncode, 0)

    def test_a_conflict_blocks_and_changes_nothing(self):
        self.ready("a", {"same.txt": "from the topic\n"})
        put(os.path.join(self.root, "same.txt"), "from the target\n")
        commit(self.root, "target change", "same.txt")
        before = sh(["git", "rev-parse", "main"], self.root).stdout
        r = desk(self.root, "receive", "a")
        self.assertEqual(r.returncode, 3)
        self.assertEqual(sh(["git", "rev-parse", "main"], self.root).stdout, before)
        self.assertTrue(os.path.isdir(self.work("a")))

    def test_a_target_with_uncommitted_files_blocks(self):
        self.ready("a")
        put(os.path.join(self.root, "CLAUDE.md"), get(os.path.join(self.root, "CLAUDE.md")) + "\nedit\n")
        self.assertEqual(desk(self.root, "receive", "a").returncode, 3)
        self.assertTrue(os.path.isdir(self.work("a")))

    def test_a_house_merge_command_replaces_the_plain_merge_and_must_do_the_job(self):
        self.block_line("- Receive merge: git merge --no-ff -q -m via-house $DESK_SHA")
        self.ready("a")
        self.assertEqual(desk(self.root, "receive", "a").returncode, 0)
        self.assertIn("via-house", sh(["git", "log", "--format=%s", "-3"], self.root).stdout)

    def test_a_house_merge_command_that_does_nothing_is_not_trusted(self):
        self.block_line("- Receive merge: true")
        self.ready("a")
        r = desk(self.root, "receive", "a")
        self.assertEqual(r.returncode, 3)
        self.assertIn("not in the result", r.stdout)

    def test_where_desks_differed_rows_are_appended_in_the_same_step(self):
        self.block_line("- Differed log: desks/DIFFERED.md")
        self.ready("a")
        note = os.path.join(self.work("a"), "desks", "a", "sessions", "2026-01-01-first.md")
        put(note, "# n\n\n## Where Desks differed\n\n| what | the folder | Desks |\n|---|---|---|\n| the gate | privacy | a list of names |\n")
        sh(["git", "add", "desks"], self.work("a"))
        commit(self.work("a"), f"note\n\n{TRAILER}")
        self.assertEqual(desk(self.root, "receive", "a").returncode, 0)
        log = get(os.path.join(self.root, "desks", "DIFFERED.md"))
        self.assertIn("| a | the gate | privacy | a list of names |", log.replace("  ", " "))


class Escalation(Topics):
    def rules(self, text):
        put(os.path.join(self.root, "escalate.tsv"), text)
        commit(self.root, "rules", "escalate.tsv")
        self.block_line("- Escalate: escalate.tsv")

    def test_a_path_rule_escalates_and_nothing_merges(self):
        self.rules("path\tdoctrine/*\tthe rules\n")
        self.ready("a", {"doctrine/rule.md": "new rule\n"})
        before = sh(["git", "rev-parse", "main"], self.root).stdout
        r = desk(self.root, "receive", "a")
        self.assertEqual(r.returncode, 4)
        self.assertIn("doctrine/rule.md matches path rule", r.stdout)
        self.assertEqual(sh(["git", "rev-parse", "main"], self.root).stdout, before)
        self.assertIn("escalations open: a:", desk(self.root, "digest").stdout)

    def test_control_a_file_outside_the_rule_passes(self):
        self.rules("path\tdoctrine/*\tthe rules\n")
        self.ready("a", {"plain.txt": "x\n"})
        self.assertEqual(desk(self.root, "receive", "a").returncode, 0)

    def test_a_reader_who_decides_may_take_it_in_at_that_exact_head(self):
        self.rules("path\tdoctrine/*\tthe rules\n")
        work = self.ready("a", {"doctrine/rule.md": "new rule\n"})
        head = sh(["git", "rev-parse", "--short=12", "HEAD"], work).stdout.strip()
        self.assertEqual(desk(self.root, "receive", "a").returncode, 4)
        self.assertEqual(desk(self.root, "receive", "a", "--escalated-ok", "read the diff", "--head", "000000000000").returncode, 3)
        r = desk(self.root, "receive", "a", "--escalated-ok", "read the diff", "--head", head)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("read the diff", sh(["git", "log", "--format=%s", "-3"], self.root).stdout)
        self.assertNotIn("escalations open: a", desk(self.root, "digest").stdout)

    def test_a_diff_over_the_size_limit_escalates(self):
        self.rules("max-lines\t5\tsize\n")
        self.ready("a", {"big.txt": "line\n" * 40})
        self.assertEqual(desk(self.root, "receive", "a").returncode, 4)

    def test_a_diff_the_close_note_does_not_declare_escalates(self):
        self.rules("undeclared\t*\tclaim vs diff\n")
        work = self.ready("a", {"declared.txt": "x\n", "sneaky.txt": "y\n"})
        note = os.path.join(work, "desks", "a", "sessions", "2026-01-01-first.md")
        put(note, "# n\n\n## Files\n\n- `declared.txt`\n")
        sh(["git", "add", "desks"], work)
        commit(work, f"note\n\n{TRAILER}")
        r = desk(self.root, "receive", "a")
        self.assertEqual(r.returncode, 4)
        self.assertIn("sneaky.txt", r.stdout)

    def test_control_when_the_close_note_declares_everything_it_passes(self):
        self.rules("undeclared\t*\tclaim vs diff\n")
        work = self.ready("a", {"declared.txt": "x\n"})
        put(os.path.join(work, "desks", "a", "sessions", "2026-01-01-first.md"), "# n\n\n## Files\n\n- `declared.txt`\n")
        sh(["git", "add", "desks"], work)
        commit(work, f"note\n\n{TRAILER}")
        self.assertEqual(desk(self.root, "receive", "a").returncode, 0)

    def test_two_anomaly_rows_escalate_none_does_not(self):
        self.rules("anomalies\t2\tanomalies\n")
        work = self.ready("a")
        note = os.path.join(work, "desks", "a", "sessions", "2026-01-01-first.md")
        put(note, "# n\n\n## Anomalies\n\n- one\n- two\n")
        sh(["git", "add", "desks"], work)
        commit(work, f"note\n\n{TRAILER}")
        self.assertEqual(desk(self.root, "receive", "a").returncode, 4)
        put(note, "# n\n\n## Anomalies\n\n- none\n")
        sh(["git", "add", "desks"], work)
        commit(work, f"note again\n\n{TRAILER}")
        self.assertEqual(desk(self.root, "receive", "a").returncode, 0)

    def test_a_rules_file_that_is_missing_fails_closed(self):
        self.block_line("- Escalate: nowhere.tsv")
        self.ready("a")
        r = desk(self.root, "receive", "a")
        self.assertEqual(r.returncode, 4)
        self.assertIn("not there", r.stdout)


class Digest(Topics):
    def test_a_quiet_folder_is_exit_zero(self):
        r = desk(self.root, "digest")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("lane: main folder", r.stdout)
        self.assertIn("ready, not received: none", r.stdout)

    def test_ready_topics_are_listed_with_their_head_and_exit_two(self):
        work = self.ready("a")
        head = sh(["git", "rev-parse", "--short=12", "desk/a"], work).stdout.strip()
        r = desk(self.root, "digest")
        self.assertEqual(r.returncode, 2)
        self.assertIn(f"ready, not received: a {head}", r.stdout)

    def test_the_lane_comes_from_the_branch(self):
        self.block_line("- Maintainer prefix: desk/maint")
        desk(self.root, "open", "m1")
        self.assertIn("lane: desk m1", desk(self.work("m1"), "digest").stdout)
        desk(self.root, "open", "mx")
        # `m1` is not under the maintainer prefix; a branch that is would be
        sh(["git", "checkout", "-q", "-b", "desk/maint"], self.work("mx"))
        self.assertIn("lane: maintainer", desk(self.work("mx"), "digest").stdout)

    def test_a_stale_base_is_named_and_exit_five(self):
        desk(self.root, "open", "a")
        put(os.path.join(self.root, "later.txt"), "x")
        commit(self.root, "later", "later.txt")
        r = desk(self.work("a"), "digest")
        self.assertEqual(r.returncode, 5)
        self.assertIn("STALE", r.stdout)

    def test_freeze_then_compare_matches_and_a_change_is_reported(self):
        self.ready("a")
        f = os.path.join(self._tmp.name, "frozen.json")
        r = desk(self.root, "digest", "--freeze", f, "--next", "receive a")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)  # the digest's own exit code, frozen file written
        self.assertEqual(json.load(open(f))["next"], "receive a")
        self.assertEqual(desk(self.root, "digest", "--compare", f).returncode, 0)
        self.ready("b")
        r = desk(self.root, "digest", "--compare", f)
        self.assertEqual(r.returncode, 1)
        self.assertIn("DIFFERS", r.stdout)

    def test_freeze_is_refused_while_a_child_is_running_and_without_a_next_step(self):
        desk(self.root, "open", "p")
        desk(self.root, "open", "c", "--parent", "p")
        f = os.path.join(self._tmp.name, "frozen.json")
        r = desk(self.root, "digest", "--freeze", f, "--next", "x")
        self.assertEqual(r.returncode, 6)
        self.assertFalse(os.path.exists(f))
        self.assertIn("children are still running", r.stderr)
        # control: with no running child and a next step it is written
        sh(["git", "worktree", "remove", "--force", self.work("c")], self.root)
        sh(["git", "branch", "-D", "desk/c"], self.root)
        self.assertEqual(desk(self.root, "digest", "--freeze", f, "--next", "x").returncode, 0)
        self.assertEqual(desk(self.root, "digest", "--freeze", f).returncode, 6)


class Wording(unittest.TestCase):
    """Items 7 and 8: the contract says the right thing; a small test keeps it from drifting."""

    def skill(self):
        return get(os.path.join(os.path.dirname(HERE), "skills", "desk", "SKILL.md"))

    def test_a_refusal_is_an_answer_and_is_asked_once(self):
        s = " ".join(self.skill().split())
        self.assertIn("A refusal is an answer", s)
        self.assertIn("Ask once", s)
        self.assertIn("never in the project's permission settings", s)

    def test_the_header_declares_its_license_and_what_it_requires(self):
        head = self.skill().split("---")[1]
        self.assertTrue(head.strip().splitlines()[1].startswith("license:"))
        self.assertIn("requires:", head)

    def test_adopt_never_reads_key_files(self):
        adopt = get(os.path.join(os.path.dirname(HERE), "skills", "desk", "reference", "adopt.md"))
        self.assertIn("--check", adopt)
        self.assertNotIn("cat ~/.config/desk/openrouter.key", adopt)

    def test_help_exits_zero(self):
        for name in ("desk.py", "review.py"):
            r = subprocess.run([sys.executable, os.path.join(os.path.dirname(DESK), name), "--help"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, name)

    def test_the_contract_stays_in_one_screenful_of_lines(self):
        self.assertLessEqual(len(self.skill().splitlines()), 300)


if __name__ == "__main__":
    unittest.main()
