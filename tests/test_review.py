"""review.py without the network: the privacy refusal, model choice, what counts as an answer,
labels and receipts. Standard library only.
"""
import importlib.util
import io
import os
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

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
        self._env = {k: os.environ.pop(k, None) for k in ("OPENROUTER_API_KEY", "DESK_REVIEW_KEY", "DESK_REVIEW_MODELS", "DESK_REVIEW_N", "DESK_REVIEW_MIN")}

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

    def test_private_terms_are_case_insensitive_and_comments_ignored(self):
        self.conf("private-terms.txt", "# family\nMontenegro\n")
        self.assertTrue(review.private_hits("the montenegro account"))
        self.assertEqual(review.private_hits("the family account"), [])

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


def refused(code):
    return urllib.error.HTTPError("https://openrouter.ai/api/v1", code, "no", {}, io.BytesIO(b'{"error":"no"}'))


class Proxy(Sandbox):
    """DESK_REVIEW_KEY=proxy: a network proxy attaches the key, the script never sees one."""

    def setUp(self):
        super().setUp()
        os.environ["DESK_REVIEW_KEY"] = "proxy"

    def lane(self, name):
        script = os.path.join(self.dir, name + ".py")
        put(script, "import sys; sys.stdin.read(); print(%r)" % LONG)
        return f'{name} | "{sys.executable}" "{script}"\n'

    def test_no_authorization_header_of_its_own_even_with_a_key_set(self):
        os.environ["OPENROUTER_API_KEY"] = "sk-should-not-be-sent"
        self.conf("openrouter.key", "k")
        self.assertEqual(review.api_key(), "proxy")
        sent = []

        class Answer(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def urlopen(req, timeout=None):
            sent.append(req)
            return Answer(b'{"choices": [{"message": {"content": "fine"}}]}')

        with mock.patch.object(review.urllib.request, "urlopen", urlopen):
            review.ask_openrouter("alpha/big:free", "x", "f", review.api_key())
        self.assertEqual(len(sent), 1)
        self.assertIsNone(sent[0].get_header("Authorization"))

    def fake_key(self, answer):
        calls = []

        def http(url, payload=None, key=None, timeout=100):
            calls.append((url, key))
            if isinstance(answer, Exception):
                raise answer
            return answer

        review.http = http
        return calls

    def test_check_working_names_label_and_limit(self):
        calls = self.fake_key({"data": {"label": "desk-cloud", "limit": 10, "usage": 0}})
        code, out, _ = self.run_main("--check")
        self.assertEqual(code, 0)
        self.assertIn('review key:      via proxy, working (label "desk-cloud", limit 10)', out)
        self.assertIn("cross-vendor", out)
        self.assertEqual(calls, [("https://openrouter.ai/api/v1/key", "proxy")])

    def test_check_working_without_details(self):
        self.fake_key({"data": {}})
        code, out, _ = self.run_main("--check")
        self.assertEqual(code, 0)
        self.assertIn("review key:      via proxy, working\n", out)

    def test_check_not_attached_counts_as_no_key(self):
        for status in (401, 403):
            self.fake_key(refused(status))
            code, out, _ = self.run_main("--check")
            self.assertEqual(code, 3)
            self.assertIn(f"review key:      via proxy, NOT attached (HTTP {status})", out)
            self.assertIn("same-vendor", out)

    def test_check_not_attached_with_another_lane_still_exits_0(self):
        self.conf("reviewers.txt", self.lane("mine"))
        self.fake_key(refused(401))
        code, out, _ = self.run_main("--check")
        self.assertEqual(code, 0)
        self.assertIn("NOT attached (HTTP 401)", out)

    def test_check_with_no_answer_at_all_is_not_working(self):
        self.fake_key(urllib.error.URLError("no route"))
        code, out, _ = self.run_main("--check")
        self.assertEqual(code, 3)
        self.assertIn("via proxy, not reached", out)

    def chat(self, error):
        calls = []

        def http(url, payload=None, key=None, timeout=100):
            if payload is None:
                return CATALOGUE
            calls.append(payload["model"])
            raise error

        review.http = http
        return calls

    def test_a_refusal_stops_the_lane_and_says_why(self):
        for status in (401, 403):
            os.environ["DESK_REVIEW_N"] = "1"
            calls = self.chat(refused(status))
            code, out, _ = self.run_main(self.packet())
            self.assertEqual(code, 4)
            self.assertEqual(len(calls), 1)  # no retry, no top-up
            self.assertIn("not-attached", out)
            self.assertIn("Review: [unreviewed] · key not attached in this environment · receipt", out)

    def test_a_refusal_means_never_converged(self):
        self.conf("reviewers.txt", self.lane("one") + self.lane("two"))
        self.chat(refused(401))
        code, out, _ = self.run_main(self.packet())
        self.assertEqual(code, 0)
        self.assertNotIn("[converged]", out)
        self.assertIn("Review: [thin] · 2 vendors · key not attached in this environment · receipt", out)
        rid = out.split("receipt ")[-1].split()[0]
        self.assertIn("review_key key not attached", self.run_main("--verify", rid, self.dir)[1])

    def test_rate_limits_and_server_errors_keep_their_handling(self):
        for status, expected in ((429, "rate-limited"), (502, "failed")):
            calls = self.chat(refused(status))
            got, _ = review.ask_openrouter("alpha/big:free", "x", "f", review.api_key())
            self.assertEqual(got, expected)
            self.assertEqual(len(calls), 2)  # retried once, as before

    def test_without_the_flag_a_refusal_is_an_ordinary_failure(self):
        del os.environ["DESK_REVIEW_KEY"]
        self.chat(refused(401))
        self.assertEqual(review.ask_openrouter("alpha/big:free", "x", "f", "k")[0], "failed")


if __name__ == "__main__":
    unittest.main()
