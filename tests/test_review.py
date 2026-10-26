"""review.py without the network: the privacy refusal, model choice, what counts as an answer,
labels and receipts. Standard library only.
"""
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "desk", "scripts", "review.py")
spec = importlib.util.spec_from_file_location("review", PATH)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def put(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


LONG = "This is a substantive objection to the proposal. " * 8
CATALOGUE = {"data": [
    {"id": "alpha/big:free", "context_length": 100}, {"id": "alpha/small:free", "context_length": 10},
    {"id": "beta/one:free", "context_length": 50}, {"id": "gamma/paid", "context_length": 999},
    {"id": "anthropic/claude:free", "context_length": 999}, {"id": "delta/llama-guard:free", "context_length": 9},
    {"id": "epsilon/e:free", "context_length": 5}, {"id": "zeta/z:free", "context_length": 5},
]}


class Sandbox(unittest.TestCase):
    """Every test gets an empty config folder and no key, whatever the machine has."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self._conf, self._http, self._sleep = review.CONF, review.http, review.time.sleep
        review.CONF = os.path.join(self.dir, "conf")
        os.makedirs(review.CONF)
        review.time.sleep = lambda s: None
        self._env = {k: os.environ.pop(k, None) for k in ("OPENROUTER_API_KEY", "DESK_REVIEW_MODELS", "DESK_REVIEW_N", "DESK_REVIEW_MIN")}

    def tearDown(self):
        review.CONF, review.http, review.time.sleep = self._conf, self._http, self._sleep
        for k, v in self._env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        self._tmp.cleanup()

    def conf(self, name, text):
        put(os.path.join(review.CONF, name), text)

    def packet(self, text="A question about pricing a used bicycle in a mid-size town.\n"):
        p = os.path.join(self.dir, "reviews", "2026-01-01-price.md")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        put(p, text)
        return p

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = review.main(["review.py", *args])
        return code, out.getvalue(), err.getvalue()

    def fake(self, answers):
        """answers: vendor -> text, or an Exception to raise."""
        calls = []

        def http(url, payload=None, key=None, timeout=100):
            if payload is None:
                return CATALOGUE
            calls.append(payload["model"])
            a = answers.get(payload["model"].split("/")[0], RuntimeError("down"))
            if isinstance(a, Exception):
                raise a
            return {"choices": [{"message": {"content": a}}]}

        review.http = http
        return calls


class Privacy(Sandbox):
    def test_refuses_email_phone_and_keys(self):
        for bad in ("write to someone@example.com", "call +1 (555) 010-9999 now", "key sk-abcdefghijklmnopqrstuvwx"):
            self.assertTrue(review.private_hits(bad), bad)

    def test_ordinary_text_and_prices_pass(self):
        self.assertEqual(review.private_hits("Ask 95, accept 80. Sold ones went for 70 to 100 in 2026."), [])

    def test_dates_are_not_phone_numbers(self):
        for ok in ("seen on 2026-10-15 and 2026-10-09", "at 2026-10-15T09:30 and 2026-10-15 09:30:12",
                   "from 2026-10-14..16"):
            self.assertEqual(review.private_hits(ok), [], ok)
        for bad in ("on 2026-10-15 call 555 010 9999", "2026-10-15 +1 (555) 010-9999"):
            self.assertTrue(review.private_hits(bad), bad)

    def test_private_terms_match_whole_words_only(self):
        self.conf("private-terms.txt", "Mara\nLa Paz Street\n")
        self.assertTrue(review.private_hits("ask Mara first"))
        self.assertTrue(review.private_hits("near la paz street"))
        self.assertEqual(review.private_hits("a maracuya juice, Amara's shop"), [])
        self.conf("private-terms.txt", "Inés\n")
        self.assertTrue(review.private_hits("INÉS arrives at 5"))
        self.assertEqual(review.private_hits("Inésita arrives at 5"), [])

    def test_private_terms_are_case_insensitive_and_comments_ignored(self):
        self.conf("private-terms.txt", "# family\nMontenegro\n")
        self.assertTrue(review.private_hits("the montenegro account"))
        self.assertEqual(review.private_hits("the family account"), [])

    def test_a_folder_that_reviews_its_own_way_is_not_sent_unless_its_routine_asks(self):
        old = os.getcwd()
        os.chdir(self.dir)  # not a git folder: the Desk block is read from here
        try:
            put(os.path.join(self.dir, "CLAUDE.md"), "<!-- desk:start -->\n- Review: house follow how.md\n<!-- desk:end -->\n")
            code, _, err = self.run_main(self.packet())
            self.assertEqual(code, 5)
            self.assertIn("reviews its own way: how.md", err)
            code, _, err = self.run_main(self.packet(), "--alongside")
            self.assertEqual(code, 3)  # it went on: no key here, so it stops at the key, not at the house line
        finally:
            os.chdir(old)

    def test_when_the_desk_block_cannot_be_read_nothing_is_sent(self):
        old = review.importlib.util.spec_from_file_location
        review.importlib.util.spec_from_file_location = lambda *a, **k: (_ for _ in ()).throw(OSError("gone"))
        try:
            code, _, err = self.run_main(self.packet())
        finally:
            review.importlib.util.spec_from_file_location = old
        self.assertEqual(code, 5)
        self.assertIn("could not read this folder's Desk block", err)

    def test_a_refused_packet_is_never_sent(self):
        self.conf("openrouter.key", "k")
        calls = self.fake({"alpha": LONG})
        code, _, err = self.run_main(self.packet("mail a@b.co about it"))
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])
        self.assertIn("NOT SENT", err)


class Choosing(Sandbox):
    def test_one_free_model_per_vendor_never_the_authors_vendor_or_classifiers(self):
        self.fake({})
        ids = review.pick_models(self.dir)
        self.assertEqual(sorted(ids), ["alpha/big:free", "beta/one:free", "epsilon/e:free", "zeta/z:free"])

    def test_a_paid_model_is_refused_before_any_call(self):
        calls = self.fake({})
        status, _ = review.ask_openrouter("gamma/paid", "x", "f", "k")
        self.assertEqual(status, "refused")
        self.assertEqual(calls, [])

    def test_vendors_that_failed_before_go_last_but_stay(self):
        folder = os.path.join(self.dir, "reviews", "old-reviews")
        os.makedirs(folder)
        rows = ["date\tpacket\tmodel\tvendor\tstatus\tseconds"] + ["d\tp\tm\talpha\tfailed\t1"] * 5
        put(os.path.join(folder, "ledger.tsv"), "\n".join(rows) + "\n")
        self.fake({})
        ids = review.pick_models(os.path.join(self.dir, "reviews", "new-reviews"))
        self.assertEqual(ids[-1], "alpha/big:free")
        self.assertEqual(len(ids), 4)


class Answers(Sandbox):
    def test_what_counts_as_an_answer(self):
        self.assertTrue(review.substantive(LONG))
        self.assertFalse(review.substantive("Here"))
        self.assertFalse(review.substantive("<|tool_call_start|>[search(query='" + "x" * 400 + "')]<|tool_call_end|>"))

    def test_a_timeout_is_not_retried_but_another_failure_is(self):
        calls = self.fake({"alpha": TimeoutError("timed out")})
        self.assertEqual(review.ask_openrouter("alpha/big:free", "x", "f", "k")[0], "failed")
        self.assertEqual(len(calls), 1)
        calls = self.fake({"beta": RuntimeError("502")})
        review.ask_openrouter("beta/one:free", "x", "f", "k")
        self.assertEqual(len(calls), 2)

    def test_the_daily_cap_is_named_and_stops_the_top_up(self):
        self.conf("openrouter.key", "k")
        os.environ["DESK_REVIEW_N"] = "1"
        calls = self.fake({v: RuntimeError("free-models-per-day limit") for v in ("alpha", "beta", "epsilon", "zeta")})
        code, out, _ = self.run_main(self.packet())
        self.assertEqual(code, 4)
        self.assertIn("ACCOUNT CAP", out)
        self.assertLessEqual(len(calls), 2)


class Labels(Sandbox):
    def go(self, answers, n="6"):
        self.conf("openrouter.key", "k")
        os.environ["DESK_REVIEW_N"] = n
        self.fake(answers)
        return self.run_main(self.packet())

    def test_no_key_and_no_lane_says_same_vendor(self):
        code, _, err = self.run_main(self.packet())
        self.assertEqual(code, 3)
        self.assertIn("[same-vendor]", err)

    def test_several_vendors_converged_with_a_verifiable_receipt(self):
        code, out, _ = self.go({"alpha": LONG, "beta": LONG, "epsilon": LONG})
        self.assertEqual(code, 0)
        self.assertIn("Review: [converged] · 3 families · receipt ", out)
        self.assertIn("2026-01-01-price-dispositions.md", out)
        rid = out.split("receipt ")[1].split()[0]
        code, shown, _ = self.run_main("--verify", rid, self.dir)
        self.assertEqual(code, 0)
        self.assertIn("families_answered 3", shown)
        self.assertEqual(self.run_main("--verify", "0000000000", self.dir)[0], 1)

    def test_verify_says_converged_only_once_the_dispositions_exist(self):
        code, out, _ = self.go({"alpha": LONG, "beta": LONG, "epsilon": LONG})
        rid = out.split("receipt ")[1].split()[0]
        shown = self.run_main("--verify", rid, self.dir)[1]
        self.assertIn("dispositions missing", shown)
        self.assertIn("label now: open", shown)
        put(os.path.join(self.dir, "reviews", "2026-01-01-price-dispositions.md"), "| # | finding | disposition |\n|---|---|---|\n| 1 | too long | adopted |\n")
        shown = self.run_main("--verify", rid, self.dir)[1]
        self.assertIn("dispositions present", shown)
        self.assertIn("label now: converged", shown)

    def test_reading_old_ledgers_leaves_no_file_open(self):
        import gc, warnings
        d = os.path.join(self.dir, "reviews", "old-reviews")
        os.makedirs(d)
        put(os.path.join(d, "ledger.tsv"), "date\tpacket\tmodel\tvendor\tstatus\tseconds\n")
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter("always")
            review.past_rates(os.path.join(self.dir, "reviews", "x-reviews"))
            gc.collect()
        self.assertFalse([w for w in seen if issubclass(w.category, ResourceWarning)])

    def test_one_vendor_is_thin(self):
        code, out, _ = self.go({"alpha": LONG})
        self.assertEqual(code, 6)  # fewer families than wanted is not a clean run
        self.assertIn("Review: [thin] · 1 family", out)

    def test_nobody_is_unreviewed(self):
        code, out, _ = self.go({})
        self.assertEqual(code, 4)
        self.assertIn("[unreviewed]", out)

    def test_an_empty_answer_does_not_count_as_a_vendor(self):
        _, out, _ = self.go({"alpha": LONG, "beta": "ok"})
        self.assertIn("[thin]", out)

    def test_top_up_reaches_vendors_beyond_the_first_batch(self):
        _, out, _ = self.go({"epsilon": LONG, "zeta": LONG, "beta": LONG}, n="1")
        self.assertIn("Topped up with:", out)
        self.assertIn("[converged]", out)

    def test_your_own_lane_counts_as_a_vendor(self):
        script = os.path.join(self.dir, "lane.py")
        put(script, "import sys; sys.stdin.read(); print(%r)" % LONG)
        self.conf("reviewers.txt", f'mine | "{sys.executable}" "{script}"\n')
        code, out, _ = self.run_main(self.packet())
        self.assertEqual(code, 6)
        self.assertIn("[thin] · 1 family", out)

    def test_usage_errors(self):
        self.assertEqual(self.run_main("--help")[0], 0)  # asking for help is not an error
        self.assertEqual(self.run_main()[0], 2)
        code, _, err = self.run_main(os.path.join(self.dir, "nope.md"))
        self.assertEqual(code, 2)
        self.assertIn("packet not found", err)


REASONING_ONLY = [
    "<think>" + "The proposal says X and I should consider Y at length. " * 12 + "</think>",
    "<think>" + "Still thinking about the proposal and what to answer. " * 12,   # never closed
    "Let me think about it step by step and weigh the claims. " * 12 + "</think>",   # closed, never opened
    "[no content field; showing reasoning trace]\n" + "The user wants a review of the packet. " * 12,
    "<think>" + "Reasoning about the packet at length. " * 12 + "</think>\n\nOk.",
    "<|tool_call_start|>[search(query='" + "x" * 400 + "')]<|tool_call_end|>",
    "   \n  ",
]


class Substantive(Sandbox):
    """What counts as a family's answer: fixtures shaped like the empty and trace-only answers free models return."""

    def test_empty_and_reasoning_only_answers_do_not_count(self):
        for t in REASONING_ONLY:
            self.assertFalse(review.substantive(t), t[:60])

    def test_an_answer_after_the_reasoning_counts(self):
        self.assertTrue(review.substantive("<think>short plan</think>\n" + LONG))
        self.assertTrue(review.substantive(LONG))

    def test_exactly_at_the_threshold(self):
        self.assertFalse(review.substantive("x" * (review.MIN_CHARS - 1)))
        self.assertTrue(review.substantive("x" * review.MIN_CHARS))

    def test_a_reasoning_field_with_no_content_is_thin_not_answered(self):
        review.http = lambda url, payload=None, key=None, timeout=100: {"choices": [{"message": {"content": "", "reasoning": "Thinking " * 80}}]}
        status, body = review.ask_openrouter("alpha/big:free", "x", "f", "k")
        self.assertEqual(status, "thin-answer")
        self.assertTrue(body.startswith(review.TRACE_MARK))


class HouseHooks(Sandbox):
    """`Gate:` and `Private lane:` in the Desk block (item 3). Each test is run from a folder that has one."""

    def folder(self, *lines, gate=None, lane=None):
        self.old = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, self.old)
        put(os.path.join(self.dir, "CLAUDE.md"), "<!-- desk:start -->\n" + "\n".join(lines) + "\n<!-- desk:end -->\n")

    def script(self, name, body):
        p = os.path.join(self.dir, name)
        put(p, body)
        return f'"{sys.executable}" "{p}"'

    def test_a_gate_that_passes_lets_the_packet_go_and_the_built_in_scan_stands_down(self):
        gate = self.script("gate.py", "print('ok')")
        self.folder(f"- Gate: {gate}")
        self.conf("openrouter.key", "k")
        os.environ["DESK_REVIEW_N"] = "3"
        calls = self.fake({"alpha": LONG, "beta": LONG, "epsilon": LONG})
        code, out, _ = self.run_main(self.packet("write to someone@example.com about the bicycle\n"))
        self.assertEqual(code, 0)  # the folder's gate is the one authority: no second marker list
        self.assertGreaterEqual(len(calls), 3)

    def test_negative_control_a_nonzero_gate_stops_everything(self):
        gate = self.script("gate.py", "import sys; sys.exit(1)")
        self.folder(f"- Gate: {gate}")
        self.conf("openrouter.key", "k")
        calls = self.fake({"alpha": LONG})
        code, _, err = self.run_main(self.packet())
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])
        self.assertIn("NOT SENT", err)

    def test_refuse_on_the_first_line_refuses_even_with_exit_zero(self):
        gate = self.script("gate.py", "print('REFUSE: a name'); import sys; sys.exit(0)")
        self.folder(f"- Gate: {gate}")
        self.conf("openrouter.key", "k")
        calls = self.fake({"alpha": LONG})
        self.assertEqual(self.run_main(self.packet())[0], 1)
        self.assertEqual(calls, [])

    def test_a_gate_that_exits_zero_and_says_nothing_refuses(self):
        gate = self.script("gate.py", "import sys; sys.exit(0)")
        self.folder(f"- Gate: {gate}")
        self.conf("openrouter.key", "k")
        calls = self.fake({"alpha": LONG})
        self.assertEqual(self.run_main(self.packet())[0], 1)
        self.assertEqual(calls, [])

    def test_a_gate_that_cannot_run_refuses(self):
        self.folder("- Gate: /nonexistent/gate-command")
        self.conf("openrouter.key", "k")
        calls = self.fake({"alpha": LONG})
        self.assertEqual(self.run_main(self.packet())[0], 1)
        self.assertEqual(calls, [])

    def test_the_gate_gets_the_tier_and_a_file_that_includes_the_focus(self):
        seen = os.path.join(self.dir, "seen.txt")
        gate = self.script("gate.py", f"import sys; open({seen!r}, 'a').write(sys.argv[2] + ':' + open(sys.argv[1]).read().splitlines()[-1] + chr(10))")
        lane = self.script("lane.py", "print('x')")
        self.folder(f"- Gate: {gate}", f"- Private lane: {lane}")
        self.conf("openrouter.key", "k")
        self.fake({"alpha": LONG})
        self.run_main(self.packet(), "my focus line")
        lines = open(seen).read().splitlines()
        self.assertEqual(lines, ["public:my focus line", "private:my focus line"])

    def test_public_refused_private_answers_is_partial_and_exits_nonzero(self):
        gate = self.script("gate.py", "import sys; print('ok'); sys.exit(0 if sys.argv[2] == 'private' else 1)")
        lane = self.script("lane.py", f"print({LONG!r})")
        self.folder(f"- Gate: {gate}", f"- Private lane: {lane}")
        self.conf("openrouter.key", "k")
        calls = self.fake({"alpha": LONG})
        code, out, _ = self.run_main(self.packet())
        self.assertEqual(calls, [])  # nothing went to the outside vendors
        self.assertEqual(code, 6)  # a partial refusal is not a clean exit
        self.assertIn("private lane only", out)

    def test_a_private_lane_too_large_is_named(self):
        lane = self.script("lane.py", "import sys; sys.exit(3)")
        self.folder(f"- Private lane: {lane}")
        status, why = review.ask_private_command(f'"{sys.executable}" -c "import sys; sys.exit(3)"', self.packet(), "f", self.dir)
        self.assertEqual(status, "too-large")
        self.assertIn("KB", why)

    def test_the_folder_names_the_reviews_folder_and_the_dispositions_file(self):
        self.folder("- Reviews: {stem}_Reviews", "- Dispositions: {stem}_Dispositions.md")
        self.conf("openrouter.key", "k")
        os.environ["DESK_REVIEW_N"] = "3"
        self.fake({"alpha": LONG, "beta": LONG, "epsilon": LONG})
        packet = self.packet()
        code, out, _ = self.run_main(packet)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isdir(packet[:-3] + "_Reviews"))
        self.assertIn("2026-01-01-price_Dispositions.md", out)


class Receipts(Sandbox):
    def converge(self):
        self.conf("openrouter.key", "k")
        os.environ["DESK_REVIEW_N"] = "3"
        self.fake({"alpha": LONG, "beta": LONG, "epsilon": LONG})
        packet = self.packet()
        _, out, _ = self.run_main(packet)
        return packet, out.split("receipt ")[1].split()[0]

    def test_verify_works_from_any_folder(self):
        _, rid = self.converge()
        elsewhere = tempfile.mkdtemp()
        old = os.getcwd()
        os.chdir(elsewhere)
        try:
            code, shown, _ = self.run_main("--verify", rid)  # no folder argument, a different cwd
        finally:
            os.chdir(old)
        self.assertEqual(code, 0)
        self.assertIn("label now: open", shown)

    def test_closed_only_when_every_row_has_a_disposition(self):
        packet, rid = self.converge()
        d = packet[:-3] + "-dispositions.md"
        put(d, "| # | finding | disposition |\n|---|---|---|\n| 1 | a | adopted |\n| 2 | b | TODO |\n")
        self.assertEqual(review.receipt_state(rid, [self.dir])["now"], "open")
        put(d, "| # | finding | disposition |\n|---|---|---|\n| 1 | a | adopted |\n| 2 | b | rejected: out of scope |\n")
        self.assertEqual(review.receipt_state(rid, [self.dir])["now"], "converged")
        put(d, "# no rows at all\n")
        self.assertEqual(review.receipt_state(rid, [self.dir])["now"], "open")

    def test_two_tables_in_one_file_are_both_checked(self):
        packet, rid = self.converge()
        put(packet[:-3] + "-dispositions.md", "| # | f | disposition |\n|---|---|---|\n| 1 | a | adopted |\n\nRound 2\n\n| # | f | disposition |\n|---|---|---|\n| 2 | b |  |\n")
        self.assertEqual(review.receipt_state(rid, [self.dir])["now"], "open")

    def test_a_changed_packet_is_not_covered_by_the_receipt(self):
        packet, rid = self.converge()
        put(packet[:-3] + "-dispositions.md", "| # | f | disposition |\n|---|---|---|\n| 1 | a | adopted |\n")
        self.assertEqual(review.receipt_state(rid, [self.dir])["now"], "converged")
        put(packet, "A different question entirely.\n")
        self.assertEqual(review.receipt_state(rid, [self.dir])["now"], "stale")


class Background(Sandbox):
    def test_a_background_run_returns_at_once_and_a_watchdog_stops_a_hung_one(self):
        lane = os.path.join(self.dir, "slow.py")
        put(lane, "import time; time.sleep(60)")
        self.conf("reviewers.txt", f'slow | "{sys.executable}" "{lane}"\n')
        packet = self.packet()
        env = dict(os.environ, DESK_CONFIG_DIR=review.CONF, DESK_REVIEW_WATCHDOG="2")
        t0 = review.time.time()
        r = review.subprocess.run([sys.executable, PATH, packet, "--background"], capture_output=True, text=True, env=env, cwd=self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(review.time.time() - t0, 5)  # it did not wait for the review
        log = os.path.join(self.dir, "reviews", "2026-01-01-price-reviews", "run.log")
        for _ in range(60):
            if os.path.isfile(log) and "WATCHDOG" in open(log).read():
                break
            self._sleep(0.25)
        self.assertIn("WATCHDOG", open(log).read())
        self.assertIn("WATCHDOG", self.run_main("--status", packet)[1])


if __name__ == "__main__":
    unittest.main()
