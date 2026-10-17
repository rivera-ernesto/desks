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
            self.assertIn("reviews its own way: follow how.md", err)
            code, _, err = self.run_main(self.packet(), "--alongside")
            self.assertEqual(code, 3)  # it went on: no key here, so it stops at the key, not at the house line
        finally:
            os.chdir(old)

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
        self.assertIn("Review: [converged] · 3 vendors · receipt ", out)
        self.assertIn("2026-01-01-price-dispositions.md", out)
        rid = out.split("receipt ")[1].split()[0]
        code, shown, _ = self.run_main("--verify", rid, self.dir)
        self.assertEqual(code, 0)
        self.assertIn("vendors_answered 3", shown)
        self.assertEqual(self.run_main("--verify", "0000000000", self.dir)[0], 1)

    def test_verify_says_converged_only_once_the_dispositions_exist(self):
        code, out, _ = self.go({"alpha": LONG, "beta": LONG})
        rid = out.split("receipt ")[1].split()[0]
        shown = self.run_main("--verify", rid, self.dir)[1]
        self.assertIn("dispositions missing", shown)
        self.assertIn("label now: open", shown)
        put(os.path.join(self.dir, "reviews", "2026-01-01-price-dispositions.md"), "| 1 | adopted |\n")
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
        self.assertEqual(code, 0)
        self.assertIn("Review: [thin] · 1 vendor", out)

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
        self.assertEqual(code, 0)
        self.assertIn("[thin] · 1 vendor", out)

    def test_usage_errors(self):
        self.assertEqual(self.run_main("--help")[0], 2)
        code, _, err = self.run_main(os.path.join(self.dir, "nope.md"))
        self.assertEqual(code, 2)
        self.assertIn("packet not found", err)


if __name__ == "__main__":
    unittest.main()
