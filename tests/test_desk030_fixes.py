"""Fixes from the 0.3.0 code review. Each guard has a control: the same step without the guard's
condition succeeds. Standard library only.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_desk import Base, desk, get, sh, DESK, READY_RUN  # noqa: E402
import test_desk030 as t30  # noqa: E402
from test_desk030 import put, commit, TRAILER, HERE  # noqa: E402

SKILL = os.path.join(os.path.dirname(HERE), "skills", "desk")
SID = "11111111-2222-3333-4444-555555555555"


class WrongBranch(t30.Topics):
    """A follow-opened folder whose session sits on main must not have main pushed or merged as the topic."""

    def setup_folder(self, branch):
        put(os.path.join(self.root, "open.md"), "open it\n")
        commit(self.root, "opener", "open.md")
        desk(self.root, "set", "Open", "house follow open.md")
        if branch != "main":
            sh(["git", "checkout", "-q", "-b", branch], self.root)
        folder = os.path.join(self.root, "desks", "a")
        put(os.path.join(folder, "README.md"), "# a\n\nstate\n")
        put(os.path.join(folder, "sessions", "2026-01-01-first.md"), "# note\n")
        commit(self.root, "topic", "desks")

    def test_a_close_from_the_wrong_branch_pushes_and_merges_nothing(self):
        self.setup_folder("main")
        before = sh(["git", "rev-parse", "HEAD"], self.root).stdout
        r = desk(self.root, "close", "a", "--merge")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not the branch of topic a", r.stderr)
        self.assertEqual(sh(["git", "rev-parse", "HEAD"], self.root).stdout, before)  # no trailer commit on main

    def test_control_the_topics_own_branch_closes(self):
        self.setup_folder("desk/a")
        r = desk(self.root, "close", "a", "--merge")
        self.assertNotIn("not the branch of topic", r.stderr)


class EscalationFailsClosed(t30.Escalation):
    def run_a(self, rules, note="# n\n\n## Anomalies\n\n- none\n"):
        self.rules(rules)
        work = self.ready("a")
        put(os.path.join(work, "desks", "a", "sessions", "2026-01-01-first.md"), note)
        sh(["git", "add", "desks"], work)
        commit(work, f"note\n\n{TRAILER}")
        return desk(self.root, "receive", "a")

    def test_an_unknown_rule_kind_escalates(self):
        r = self.run_a("claim-vs-diff\t*\ttypo\n")
        self.assertEqual(r.returncode, 4)
        self.assertIn("`claim-vs-diff`", r.stdout)

    def test_a_bad_number_escalates(self):
        self.assertEqual(self.run_a("max-lines\tmany\tsize\n").returncode, 4)

    def test_a_bad_anomaly_number_escalates(self):
        self.assertEqual(self.run_a("anomalies\ttwo\tn\n").returncode, 4)

    def test_a_rules_file_with_only_comments_escalates(self):
        self.assertEqual(self.run_a("# nothing here\n").returncode, 4)

    def test_none_is_matched_as_a_whole_word_only(self):
        note = "# n\n\n## Anomalies\n\n- nonexistent file was read\n"
        self.assertEqual(self.run_a("anomalies\t1\tn\n", note).returncode, 4)

    def test_control_a_known_rule_with_a_number_and_a_none_row_passes(self):
        self.assertEqual(self.run_a("anomalies\t1\tn\nmax-lines\t500\tsize\n").returncode, 0)


class EscalateExcept(t30.Topics):
    """#82: a folder whose close writes its own notes and packs on every close must not escalate every topic."""

    rules = t30.Escalation.rules
    JOURNAL = "path\t*Journal*\tjournal notes\texcept=desks/a/closes/*\n"

    def test_a_match_only_inside_the_topics_own_close_folder_is_received(self):
        self.rules(self.JOURNAL)
        self.ready("a", {"desks/a/closes/Journal-2026-01-01.md": "closed\n"})
        r = desk(self.root, "receive", "a")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_control_the_same_file_outside_that_folder_escalates(self):
        self.rules(self.JOURNAL)
        self.ready("a", {"journal/Journal-2026-01-01.md": "closed\n"})
        r = desk(self.root, "receive", "a")
        self.assertEqual(r.returncode, 4)
        self.assertIn("journal/Journal-2026-01-01.md matches path rule `*Journal*`", r.stdout)

    def test_lines_inside_the_topics_own_folders_do_not_count_toward_max_lines(self):
        self.rules("max-lines\t20\tsize\n")
        self.ready("a", {"desks/a/closes/pack.md": "line\n" * 200})
        r = desk(self.root, "receive", "a")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_control_the_same_lines_outside_them_escalate(self):
        self.rules("max-lines\t20\tsize\n")
        self.ready("a", {"pack.md": "line\n" * 200})
        r = desk(self.root, "receive", "a")
        self.assertEqual(r.returncode, 4)
        self.assertIn("over the limit of 20", r.stdout)

    def test_max_lines_takes_an_except_glob(self):
        self.rules("max-lines\t20\tsize\texcept=vendor/*\n")
        self.ready("a", {"vendor/lib.txt": "line\n" * 200})
        r = desk(self.root, "receive", "a")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_a_malformed_except_escalates(self):
        for rule, says in (("path\t*Journal*\twhy\texcept=\n", "no glob"),
                           ("path\t*Journal*\twhy\texcept closes/*\n", "not `except=<glob>`"),
                           ("path\t*Journal*\twhy\tunless=closes/*\n", "does not know: `unless=closes/*`"),
                           ("undeclared\t*\twhy\texcept=closes/*\n", "only path, doctrine and max-lines")):
            with self.subTest(rule=rule):
                self.rules(rule)
                if "desk/a" not in self.branches():
                    self.ready("a", {"plain.txt": "x\n"})  # nothing here matches any rule's glob
                r = desk(self.root, "receive", "a")
                self.assertEqual(r.returncode, 4, r.stdout)
                self.assertIn(says, r.stdout)
                self.assertIn("the answer is escalate, not skip", r.stdout)


class LockFile(t30.Topics):
    def lock(self, text, age=0):
        d = os.path.join(self.root, ".git", "desk-state")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "open.lock")
        put(p, text)
        if age:
            os.utime(p, (time.time() - age, time.time() - age))

    def open_a(self):
        return subprocess.run([sys.executable, DESK, "open", "a"], cwd=self.root, capture_output=True, text=True,
                              env=dict(os.environ, DESK_LOCK_WAIT="1"))

    def test_an_empty_fresh_lock_is_live(self):
        self.lock("")  # a writer an instant from finishing
        r = self.open_a()
        self.assertEqual(r.returncode, 6, r.stderr)
        self.assertNotIn("desk/a", self.branches())

    def test_an_unreadable_fresh_lock_is_live(self):
        self.lock("garbage")
        self.assertEqual(self.open_a().returncode, 6)

    def test_control_an_empty_lock_older_than_the_ttl_is_reclaimed(self):
        self.lock("", age=601)
        self.assertEqual(self.open_a().returncode, 0)

    def test_a_lock_is_created_with_its_content(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("deskmod", DESK)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        lk = mod.Lock(self.root)
        with lk:
            self.assertEqual(get(lk.path), lk.mine)
        self.assertFalse(os.path.exists(lk.path))
        self.assertEqual([n for n in os.listdir(os.path.dirname(lk.path)) if n.startswith("open.lock")], [])


class CloseChecks(t30.Topics):
    def test_an_orphaned_child_closes_with_a_clear_error_not_a_traceback(self):
        desk(self.root, "open", "p")
        desk(self.root, "open", "c", "--parent", "p")
        self.fill("c")
        brief = os.path.join(self.work("c"), "desks", "c", "brief.md")
        put(brief, re.sub(r"\{\{[^}]*\}\}", "x", get(brief)))
        sh(["git", "add", "desks"], self.work("c"))
        commit(self.work("c"), "brief")
        sh(["git", "worktree", "remove", "--force", self.work("p")], self.root)
        sh(["git", "branch", "-D", "desk/p"], self.root)
        r = desk(self.root, "close", "c", "--merge")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("parent topic's branch is gone", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_the_base_is_checked_before_the_ready_trailer_is_committed(self):
        desk(self.root, "open", "a")
        self.fill("a")
        sh(["git", "checkout", "-q", "-b", "elsewhere"], self.root)
        r = desk(self.root, "close", "a", "--merge")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Nothing was changed", r.stderr)
        self.assertNotIn(TRAILER, sh(["git", "log", "-1", "--format=%B", "desk/a"], self.root).stdout)

    def test_control_on_the_base_the_same_close_merges(self):
        desk(self.root, "open", "a")
        self.fill("a")
        self.assertEqual(desk(self.root, "close", "a", "--merge").returncode, 0)


class ReceiptsAreStrict(t30.Labels):
    def test_a_receipt_written_into_the_tree_is_not_a_receipt(self):
        self.start()
        rid = "0123456789"
        put(os.path.join(self.work("a"), "forged", f"receipt-{rid}.txt"), f"receipt {rid}\npacket /x\nlabel converged\n")
        self.note(f"# n\n\nReview: [converged] · 3 families · receipt {rid}\n")
        self.assertIn("was not found", self.close().stderr)

    def test_a_deleted_packet_is_stale_not_skipped(self):
        self.start()
        rid = self.receipt("open", closed=True)
        os.unlink(os.path.join(self._conf.name, "r", "p.md"))
        self.note(f"# n\n\nReview: [converged] · 3 families · receipt {rid}\n")
        self.assertIn("packet is missing", self.close().stderr)

    def test_a_receipt_outside_its_packets_review_folder_is_refused(self):
        self.start()
        rid = self.receipt("open", closed=True)
        src = os.path.join(self._conf.name, "r", "p-reviews", f"receipt-{rid}.txt")
        dst = os.path.join(self._conf.name, "elsewhere", f"receipt-{rid}.txt")
        os.makedirs(os.path.dirname(dst))
        shutil.move(src, dst)
        put(os.path.join(self._conf.name, "receipts.tsv"), f"{rid}\t{dst}\n")
        self.note(f"# n\n\nReview: [converged] · 3 families · receipt {rid}\n")
        self.assertIn("review folder of its own packet", self.close().stderr)

    def test_a_disposition_needs_a_status_word(self):
        self.start()
        rid = self.receipt("open", closed=True)
        disp = os.path.join(self._conf.name, "r", "p-dispositions.md")
        put(disp, "| # | finding | disposition |\n|---|---|---|\n| 1 | a | x |\n")
        self.note(f"# n\n\nReview: [converged] · 3 families · receipt {rid}\n")
        self.assertNotEqual(self.close().returncode, 0)
        for word in ("Accepted, fixed", "rejected: out of scope", "Partly", "left to the user", "noted"):
            put(disp, f"| # | finding | disposition |\n|---|---|---|\n| 1 | a | {word} |\n")
            self.assertEqual(desk(self.work("a"), "close").returncode, 0, word)


class Wording(unittest.TestCase):
    def test_open_label_is_defined_in_the_skill_and_the_changelog(self):
        skill = get(os.path.join(SKILL, "SKILL.md"))
        self.assertRegex(skill, r"`\[open\]`\s+(a review|the review)")
        log = get(os.path.join(os.path.dirname(HERE), "CHANGELOG.md"))
        self.assertIn("`[open]` is a review", log)

    def test_the_spanish_command_aliases_are_gone(self):
        self.assertNotIn("cierra", get(os.path.join(SKILL, "SKILL.md")).lower())
        code = get(DESK)
        kinds = code[code.index("KINDS = {"):code.index("READ_FIRST")]
        self.assertNotRegex(kinds, r"cierra|cierre")

    def test_every_command_has_its_exit_codes_in_the_docs(self):
        ref = get(os.path.join(SKILL, "reference", "exit-codes.md"))
        for cmd in ("open", "close", "receive", "digest", "review.py", "remove"):
            self.assertIn(f"`{cmd}", ref, cmd)
        self.assertIn("self-declared", ref)

    def test_the_purpose_comes_first_in_the_readme(self):
        readme = get(os.path.join(os.path.dirname(HERE), "README.md"))
        self.assertIn("The user is the source and the purpose of Desks.", readme)
        self.assertLess(readme.index("The user is the source and the purpose of Desks."), readme.index("## "))

    def test_records_are_plain_markdown_owned_by_the_user(self):
        text = get(os.path.join(os.path.dirname(HERE), "INSTALL.md")) + get(os.path.join(SKILL, "reference", "setup.md"))
        self.assertIn("plain Markdown", text)
        self.assertIn("uninstalling", text.lower())
        self.assertIn("Transcripts:", text)


class DepthCap(t30.Topics):
    def test_a_cap_of_five_allows_five_levels_and_stops_the_sixth(self):
        self.block_line("- Depth cap: 5")
        desk(self.root, "open", "t0")
        for i in range(1, 6):
            self.assertEqual(desk(self.root, "open", f"t{i}", "--parent", f"t{i - 1}").returncode, 0, i)
        r = desk(self.root, "open", "t6", "--parent", "t5")
        self.assertEqual(r.returncode, 7)
        self.assertIn("Depth cap: 5", r.stderr)


class TranscriptArchive(t30.Topics):
    def setUp(self):
        super().setUp()
        self._src = tempfile.TemporaryDirectory()
        self._arch = tempfile.TemporaryDirectory()
        self.arch = os.path.join(os.path.realpath(self._arch.name), "sessions")
        self._old = os.environ.get("DESK_TRANSCRIPTS_SRC")
        os.environ["DESK_TRANSCRIPTS_SRC"] = self._src.name
        self.body = '{"type":"user","text":"hello"}\n'
        put(os.path.join(self._src.name, "-some-project", f"{SID}.jsonl"), self.body)
        put(os.path.join(self._src.name, "-other-project", "99999999-aaaa-bbbb-cccc-dddddddddddd.jsonl"), "other\n")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("DESK_TRANSCRIPTS_SRC", None)
        else:
            os.environ["DESK_TRANSCRIPTS_SRC"] = self._old
        self._src.cleanup()
        self._arch.cleanup()
        super().tearDown()

    def prepare(self, source_line=f"Source ID / UUID: {SID}\n", setting=True):
        if setting:
            desk(self.root, "set", "Transcripts", self.arch)
        desk(self.root, "open", "a")
        folder = self.fill("a")
        note = os.path.join(folder, "sessions", "2026-01-02-second.md")
        put(note, "# n\n\n" + source_line)
        sh(["git", "add", "desks"], self.work("a"))
        commit(self.work("a"), "note")
        return note

    def test_close_archives_the_transcript_and_records_its_hash_next_to_the_source_id(self):
        note = self.prepare()
        r = desk(self.root, "close", "a", "--merge")
        self.assertEqual(r.returncode, 0, r.stderr)
        dest = os.path.join(self.arch, f"{SID}.jsonl")
        self.assertEqual(get(dest), self.body)
        digest = hashlib.sha256(self.body.encode()).hexdigest()
        merged = get(os.path.join(self.root, "desks", "a", "sessions", "2026-01-02-second.md"))
        self.assertIn(f"Source ID / UUID: {SID}\nTranscript sha256: {digest}", merged)
        self.assertEqual(sh(["git", "status", "--porcelain"], self.root).stdout, "")

    def test_under_a_house_close_the_note_is_saved_so_the_routine_finds_a_clean_tree(self):
        self.prepare()
        desk(self.root, "set", "Close", 'house run test -z "$(git status --porcelain)" && ' + READY_RUN)
        r = desk(self.work("a"), "close")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.arch, f"{SID}.jsonl")))
        note = get(os.path.join(self.work("a"), "desks", "a", "sessions", "2026-01-02-second.md"))
        self.assertIn("Transcript sha256: ", note)
        self.assertEqual(sh(["git", "status", "--porcelain"], self.work("a")).stdout, "")

    def test_it_is_off_unless_the_setting_names_a_folder(self):
        self.prepare(setting=False)
        self.assertEqual(desk(self.root, "close", "a", "--merge").returncode, 0)
        self.assertFalse(os.path.exists(self.arch))

    def test_a_folder_inside_a_git_working_tree_is_refused(self):
        self.arch = os.path.join(self.root, "archive")
        self.prepare()
        r = desk(self.root, "close", "a", "--merge")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("inside a git working tree", r.stderr)
        self.assertFalse(os.path.exists(self.arch))

    def test_a_symlink_that_leads_into_a_repository_is_refused(self):
        real = os.path.join(self.root, "real-archive")
        os.makedirs(real)
        link = os.path.join(os.path.realpath(self._arch.name), "link")
        os.symlink(real, link)
        self.arch = os.path.join(link, "sessions")
        self.prepare()
        r = desk(self.root, "close", "a", "--merge")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("inside a git working tree", r.stderr)
        self.assertEqual(os.listdir(real), [])

    def test_a_git_that_cannot_answer_counts_as_inside(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("deskmod2", DESK)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        d = os.path.realpath(self._arch.name)
        mod.run = lambda *a, **k: (128, "", "fatal: detected dubious ownership in repository")
        self.assertTrue(mod.inside_work_tree(d))
        mod.run = lambda *a, **k: (128, "", "fatal: not a git repository (or any of the parent directories): .git")
        self.assertFalse(mod.inside_work_tree(d))  # control: the plain "not a repository" answer is outside

    def test_a_folder_inside_the_skill_itself_is_refused(self):
        self.arch = os.path.join(os.path.dirname(os.path.dirname(DESK)), "archive")
        self.prepare()
        r = desk(self.root, "close", "a", "--merge")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("inside the Desks skill folder", r.stderr)
        self.assertFalse(os.path.exists(self.arch))

    def test_without_a_source_id_the_newest_transcript_of_the_project_is_taken(self):
        proj = os.path.join(self._src.name, re.sub(r"[^A-Za-z0-9]", "-", self.work("a")))
        put(os.path.join(proj, "aaaaaaaa-0000-0000-0000-000000000001.jsonl"), "old\n")
        os.utime(os.path.join(proj, "aaaaaaaa-0000-0000-0000-000000000001.jsonl"), (1, 1))
        put(os.path.join(proj, "aaaaaaaa-0000-0000-0000-000000000002.jsonl"), "newest\n")
        note = self.prepare(source_line="no id here\n")
        r = desk(self.root, "close", "a", "--merge")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(get(os.path.join(self.arch, "aaaaaaaa-0000-0000-0000-000000000002.jsonl")), "newest\n")
        merged = get(os.path.join(self.root, "desks", "a", "sessions", "2026-01-02-second.md"))
        self.assertIn("Source ID / UUID: aaaaaaaa-0000-0000-0000-000000000002\nTranscript sha256: ", merged)

    def test_a_named_id_that_is_not_found_is_never_replaced_by_another_transcript(self):
        self.prepare(source_line="Source ID / UUID: 00000000-0000-0000-0000-000000000000\n")
        r = desk(self.root, "close", "a", "--merge")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no transcript for session 00000000", r.stderr)
        self.assertFalse(os.path.exists(self.arch))


class RemoveKeepsRecords(unittest.TestCase):
    def test_an_archive_inside_what_would_be_removed_stops_the_removal(self):
        with tempfile.TemporaryDirectory() as t:
            dest = os.path.realpath(t)
            shutil.copytree(SKILL, os.path.join(dest, ".claude", "skills", "desk"), ignore=shutil.ignore_patterns("__pycache__"))
            arch = os.path.join(dest, ".claude", "skills", "desk", "mine")
            put(os.path.join(arch, "x.jsonl"), "transcript\n")
            put(os.path.join(dest, "CLAUDE.md"), f"<!-- desk:start -->\n- Transcripts: {arch}\n<!-- desk:end -->\n")
            script = os.path.join(dest, ".claude", "skills", "desk", "scripts", "desk.py")
            r = sh([sys.executable, script, "remove", "--yes"], dest)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("Nothing was removed", r.stderr)
            self.assertTrue(os.path.isfile(os.path.join(arch, "x.jsonl")))


    def test_remove_takes_out_desks_and_never_the_records_or_the_archive(self):
        with tempfile.TemporaryDirectory() as t:
            dest = os.path.realpath(t)
            shutil.copytree(SKILL, os.path.join(dest, ".claude", "skills", "desk"), ignore=shutil.ignore_patterns("__pycache__"))
            for n in ("desk-reader.md", "desk-runner.md", "other-agent.md"):
                put(os.path.join(dest, ".claude", "agents", n), "agent\n")
            arch = os.path.join(dest, "archive")
            put(os.path.join(arch, f"{SID}.jsonl"), "transcript\n")
            rec = os.path.join(dest, "desks", "a", "sessions", "2026-01-01-first.md")
            put(rec, "# the record\n")
            put(os.path.join(dest, "CLAUDE.md"), "# Mine\n\nMy rule.\n\n<!-- desk:start -->\n- Desk root: `desks/`\n"
                f"- Transcripts: {arch}\n<!-- desk:end -->\n")
            script = os.path.join(dest, ".claude", "skills", "desk", "scripts", "desk.py")
            r = sh([sys.executable, script, "remove"], dest)  # a list, not a removal
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Nothing was removed", r.stdout)
            self.assertTrue(os.path.isfile(script))
            r = sh([sys.executable, script, "remove", "--yes"], dest)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse(os.path.exists(os.path.join(dest, ".claude", "skills", "desk")))
            self.assertFalse(os.path.exists(os.path.join(dest, ".claude", "agents", "desk-reader.md")))
            self.assertTrue(os.path.exists(os.path.join(dest, ".claude", "agents", "other-agent.md")))
            self.assertEqual(get(rec), "# the record\n")
            self.assertEqual(get(os.path.join(arch, f"{SID}.jsonl")), "transcript\n")
            text = get(os.path.join(dest, "CLAUDE.md"))
            self.assertIn("My rule.", text)
            self.assertNotIn("desk:start", text)


if __name__ == "__main__":
    unittest.main()
