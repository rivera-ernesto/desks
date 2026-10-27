"""providers.py, the dashboard, and the promise that no key is ever written to the repository,
to an answer file, to the dashboard or to anything printed. Standard library only; the only
network is a fake server on this machine.
"""
import contextlib
import importlib.util
import io
import os
import re
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
import unittest.mock
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "skills", "desk", "scripts")
sys.path.insert(0, HERE)
sys.path.insert(0, SCRIPTS)
import providers  # noqa: E402
import review  # noqa: E402
from fake_openai import Fake  # noqa: E402

def slurp(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# Invented values that look like real keys. Any of them showing up where it must not is the failure.
OR_KEY = "sk-or-v1-" + "0123456789abcdef" * 4
EP_KEY = "ep-sentinel-key-" + "9" * 24
PASTED = "pasted-sentinel-" + "7" * 24
SENTINELS = (OR_KEY, EP_KEY, PASTED)


class Clean(unittest.TestCase):
    """An empty config folder and no Desk variables, whatever the machine has."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self._tmp.name)
        self.conf = os.path.join(self.dir, "conf")
        os.makedirs(self.conf)
        self._saved = {k: os.environ.pop(k) for k in list(os.environ)
                       if k.startswith("DESK_") or k in ("OPENROUTER_API_KEY", "CLAUDE_CODE_REMOTE")}
        os.environ["DESK_CLOUD"] = "0"
        self._pc, self._rc = providers.CONF, review.CONF
        providers.CONF = review.CONF = self.conf
        self.fakes = []

    def tearDown(self):
        for f in self.fakes:
            f.close()
        providers.CONF, review.CONF = self._pc, self._rc
        for k in [k for k in os.environ if k.startswith("DESK_") or k in ("OPENROUTER_API_KEY", "CLAUDE_CODE_REMOTE")]:
            del os.environ[k]
        os.environ.update(self._saved)
        self._tmp.cleanup()

    def fake(self, **kw):
        f = Fake(**kw)
        self.fakes.append(f)
        return f

    def endpoint_env(self, name, fake, key="", lane=""):
        up = name.upper()
        os.environ[f"DESK_ENDPOINT_{up}_URL"] = fake.url
        os.environ[f"DESK_ENDPOINT_{up}_MODEL"] = fake.model
        if key:
            os.environ[f"DESK_ENDPOINT_{up}_KEY"] = key
        if lane:
            os.environ[f"DESK_ENDPOINT_{up}_LANE"] = lane

    def run_main(self, mod, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = mod.main(argv)
        return rc, out.getvalue() + err.getvalue()

    def assertNoKey(self, text, where):
        for s in SENTINELS:
            self.assertNotIn(s, text, f"a key value appeared in {where}")

    def tree_text(self, top):
        chunks = []
        for d, _, files in os.walk(top):
            for f in files:
                with open(os.path.join(d, f), encoding="utf-8", errors="replace") as fh:
                    chunks.append(fh.read())
        return "\n".join(chunks)


class Declarations(Clean):
    def test_an_endpoint_declared_by_environment_variables(self):
        f = self.fake(key=EP_KEY)
        self.endpoint_env("shared_llama", f, EP_KEY)
        [p] = providers.endpoints()
        self.assertEqual((p.name, p.base_url, p.model, p.source, p.lane),
                         ("shared-llama", f.url, f.model, "env:DESK_ENDPOINT_SHARED_LLAMA_KEY", "vendor"))
        self.assertEqual(p.secret(), EP_KEY)
        self.assertNotIn(EP_KEY, repr(p))

    def test_a_key_of_proxy_means_the_network_adds_it(self):
        f = self.fake()
        self.endpoint_env("gw", f, "proxy", "private")
        [p] = providers.endpoints()
        self.assertEqual((p.source, p.lane), ("proxy", "private"))
        self.assertNotIn("Authorization", p.headers())

    def test_the_dashboard_file_holds_where_a_key_comes_from_never_the_key(self):
        os.environ["MY_EP_KEY"] = EP_KEY
        rc, out = self.run_main(providers, ["p", "set", "mine", "--url", "https://models.example.invalid/v1",
                                            "--model", "other/m", "--key", "env:MY_EP_KEY"])
        self.assertEqual(rc, 0, out)
        text = slurp(os.path.join(self.conf, "providers.json"))
        self.assertIn('"env:MY_EP_KEY"', text)
        self.assertNoKey(text, "providers.json")
        [p] = providers.endpoints()
        self.assertEqual(p.secret(), EP_KEY)

    def test_a_key_typed_where_its_source_goes_is_refused(self):
        rc, out = self.run_main(providers, ["p", "set", "mine", "--url", "https://x.example.invalid/v1",
                                            "--model", "m", "--key", EP_KEY])
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(os.path.join(self.conf, "providers.json")))
        with self.assertRaises(ValueError):
            providers.save({"openrouter": {"key": OR_KEY}, "endpoints": {}}, self.conf)

    def test_environment_variables_win_over_the_file_for_the_same_name(self):
        providers.save({"openrouter": {}, "endpoints": {"gw": {"base_url": "https://a.example.invalid/v1", "model": "m",
                                                                "key": "none", "lane": "vendor"}}}, self.conf)
        os.environ["DESK_ENDPOINT_GW_URL"] = "https://b.example.invalid/v1"
        [p] = providers.endpoints()
        self.assertEqual(p.base_url, "https://b.example.invalid/v1")

    def test_openrouter_sources_in_order(self):
        self.assertIsNone(providers.openrouter())
        with open(os.path.join(self.conf, "openrouter.key"), "w") as f:
            f.write(OR_KEY)
        self.assertEqual(providers.openrouter().source, "file:openrouter.key")
        os.environ["OPENROUTER_API_KEY"] = OR_KEY
        self.assertEqual(providers.openrouter().source, "env:OPENROUTER_API_KEY")
        os.environ["DESK_REVIEW_KEY"] = "proxy"
        self.assertEqual(providers.openrouter().source, "proxy")
        self.assertEqual(review.api_key(), "proxy")

    def test_what_may_not_be_sent(self):
        os.environ["K"] = EP_KEY
        remote_http = providers.Provider("a", "endpoint", "http://models.example.invalid/v1", "m", "env:K")
        self.assertIn("unencrypted", remote_http.problem())
        self.assertEqual(providers.Provider("b", "endpoint", "http://127.0.0.1:9/v1", "m", "env:K").problem(), "")
        same = providers.Provider("c", "endpoint", "https://x.example.invalid/v1", "anthropic/claude-x", "none")
        self.assertIn("another family", same.problem())


class Ping(Clean):
    def test_states(self):
        good = self.fake(key=EP_KEY)
        os.environ["K"] = EP_KEY
        self.assertEqual(providers.ping(providers.Provider("g", "endpoint", good.url, good.model, "env:K"))[0], "ok")
        os.environ["K"] = "wrong-key-but-long-enough"
        state, detail = providers.ping(providers.Provider("g", "endpoint", good.url, good.model, "env:K"))
        self.assertEqual(state, "refused")
        self.assertNotIn("wrong-key-but-long-enough", detail)
        state, _ = providers.ping(providers.Provider("u", "endpoint", "http://127.0.0.1:9/v1", "m", "none"))
        self.assertEqual(state, "unreachable")


class NoKeyAnywhere(Clean):
    """The test the task asks for: keys come from the environment or a key file and go nowhere else."""

    def setUp(self):
        super().setUp()
        os.environ["OPENROUTER_API_KEY"] = OR_KEY
        self.ep = self.fake(key=EP_KEY, echo_auth=True)
        self.endpoint_env("other", self.ep, EP_KEY)

    def test_the_dashboard_in_text_and_html_never_shows_a_key(self):
        real = providers.call

        def call(p, path, payload=None, timeout=15):  # OpenRouter refuses, quoting the header it got
            if p.kind == "openrouter":
                raise urllib.error.URLError("refused; you sent " + p.headers().get("Authorization", ""))
            return real(p, path, payload, timeout)
        with unittest.mock.patch.object(providers, "call", call):
            rc, out = self.run_main(providers, ["p"])
            self.assertEqual(rc, 0)
            self.assertNoKey(out, "the text dashboard")
            self.assertIn("[key hidden]", out)
            self.assertRegex(out, r"other\s+ok")
            page = os.path.join(self.dir, "d.html")
            rc, out = self.run_main(providers, ["p", "html", page])
            self.assertNoKey(slurp(page) + out, "the html dashboard")

    def test_an_error_that_quotes_the_key_is_redacted(self):
        self.assertEqual(providers.redact(f"HTTP 401: bad key Bearer {EP_KEY}"), "HTTP 401: bad key Bearer [key hidden]")
        self.assertNotIn(OR_KEY, providers.redact(f"x {OR_KEY} y"))

    def test_a_review_writes_no_key_in_answers_ledger_receipt_or_output(self):
        packet = os.path.join(self.dir, "desks", "t", "reviews", "2026-01-01-q.md")
        os.makedirs(os.path.dirname(packet))
        with open(packet, "w") as f:
            f.write("Should a small shop price a used item at the median of recent sales?\n")
        os.environ["DESK_REVIEW_MODELS"] = "none/x:free"  # no catalogue call
        with unittest.mock.patch.object(review, "ask_openrouter", return_value=("failed", "HTTP 500 with Bearer " + OR_KEY)), \
                unittest.mock.patch.object(review, "house_review", return_value=""):
            rc, out = self.run_main(review, ["review.py", packet])
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.ep.seen_auth[-1], "Bearer " + EP_KEY, "the endpoint got its key")
        self.assertNoKey(out, "review output")
        self.assertNoKey(self.tree_text(os.path.join(self.dir, "desks")), "the review's files")

    def test_export_shows_names_and_origins_and_writes_values_only_where_asked(self):
        rc, out = self.run_main(providers, ["p", "export"])
        self.assertEqual(rc, 0)
        self.assertNoKey(out, "export's output")
        self.assertIn("OPENROUTER_API_KEY", out)
        self.assertIn("DESK_ENDPOINT_OTHER_KEY", out)
        target = os.path.join(self.dir, "outside", "cloud.env")
        os.makedirs(os.path.dirname(target))
        rc, out = self.run_main(providers, ["p", "export", "--env-file", target])
        self.assertEqual(rc, 0, out)
        self.assertNoKey(out, "export's output")
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)
        self.assertIn(OR_KEY, slurp(target))

    def test_export_never_writes_into_a_repository(self):
        repo = os.path.join(self.dir, "repo")
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q", repo], check=True)
        rc, out = self.run_main(providers, ["p", "export", "--env-file", os.path.join(repo, "cloud.env")])
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(os.path.join(repo, "cloud.env")))


class LocalPage(Clean):
    def test_the_local_page_edits_sources_and_stores_a_pasted_key_privately(self):
        import http.client
        srv, url = providers.make_server(self.conf)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            host, port, token = re.match(r"http://([\d.]+):(\d+)/(\S+)", url).groups()
            self.assertEqual(host, "127.0.0.1")

            def ask(method, path, body=None):
                c = http.client.HTTPConnection(host, int(port), timeout=10)
                c.request(method, path, body, {"Content-Type": "application/x-www-form-urlencoded"})
                r = c.getresponse()
                page = r.read().decode()
                c.close()
                return r.status, page
            self.assertEqual(ask("GET", "/")[0], 404)
            self.assertEqual(ask("POST", "/wrong/openrouter", "paste=x")[0], 404)
            status, page = ask("POST", f"/{token}/openrouter", "source=env%3A&arg=&paste=" + PASTED)
            status2, page2 = ask("GET", f"/{token}")
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual((status, status2), (200, 200))
        self.assertIn("saved openrouter", page)
        self.assertNoKey(page + page2, "the local page")
        key_file = os.path.join(self.conf, "openrouter.key")
        self.assertEqual(slurp(key_file).strip(), PASTED)
        self.assertEqual(stat.S_IMODE(os.stat(key_file).st_mode), 0o600)
        self.assertNoKey(slurp(os.path.join(self.conf, "providers.json")), "providers.json")
        self.assertEqual(providers.openrouter().source, "file:openrouter.key")

    def test_a_pasted_key_is_never_written_inside_a_repository(self):
        repo = os.path.join(self.dir, "repo")
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q", repo], check=True)
        with self.assertRaises(ValueError):
            providers.apply({"paste": PASTED}, "openrouter", os.path.join(repo, "conf"))
        self.assertFalse(os.path.exists(os.path.join(repo, "conf", "openrouter.key")))


class Lanes(Clean):
    def test_a_private_endpoint_must_repeat_both_codes(self):
        good, bad = self.fake(canaries=True), self.fake(canaries=False)
        os.environ["DESK_REVIEW_KEY"] = ""
        for name, f, want in (("good", good, "answered"), ("bad", bad, "canary-missing")):
            p = providers.Provider(name, "endpoint", f.url, f.model, "none", "private")
            self.assertEqual(review.ask_endpoint(p, "A packet.\n", "focus")[0], want)

    def test_a_packet_refused_for_outside_vendors_still_goes_to_a_private_endpoint(self):
        gw = self.fake(canaries=True)
        self.endpoint_env("gw", gw, "", "private")
        packet = os.path.join(self.dir, "p.md")
        with open(packet, "w") as f:
            f.write("Write to someone@example.com about the price.\n")
        with unittest.mock.patch.object(review, "house_review", return_value=""):
            rc, out = self.run_main(review, ["review.py", packet])
        self.assertEqual(rc, 0, out)
        self.assertIn("private lane only", out)
        self.assertEqual(len(gw.seen_auth), 1)

    def test_two_endpoints_from_other_families_are_two_vendors(self):
        for n in ("aa", "bb"):
            self.endpoint_env(n, self.fake(model=f"{n}/m"))
        packet = os.path.join(self.dir, "p.md")
        with open(packet, "w") as f:
            f.write("Is a weekly market stall worth it for a hobby seller?\n")
        with unittest.mock.patch.object(review, "house_review", return_value=""):
            rc, out = self.run_main(review, ["review.py", packet])
        self.assertEqual(rc, 0, out)
        self.assertIn("[converged] · 2 vendors", out)

    def test_in_the_cloud_the_shortcut_lane_is_off_and_says_so(self):
        os.environ["DESK_CLOUD"] = "1"
        with open(os.path.join(self.conf, "apple-shortcut"), "w") as f:
            f.write("Desk Review")
        d = providers.gather(do_ping=False)
        self.assertIn(("Apple Intelligence through a macOS Shortcut",
                       "off in the cloud: macOS only; use a gateway endpoint"), d["lanes"])
        self.assertEqual(d["environment"], "cloud")
        self.assertTrue(any("cloud environment's settings" in " ".join(s) for _, s in d["missing"]))

    def test_private_terms_from_the_environment(self):
        os.environ["DESK_PRIVATE_TERMS"] = "Mara; Calle Ocho"
        self.assertTrue(review.private_hits("ask Mara"))
        self.assertTrue(review.private_hits("on calle ocho"))
        self.assertFalse(review.private_hits("maracuya"))


class Repository(unittest.TestCase):
    """Nothing that looks like a real key is tracked in this repository."""

    PATTERNS = [r"sk-or-v1-[0-9a-f]{64}", r"sk-(?:proj-)?[A-Za-z0-9]{40,}", r"gh[pousr]_[A-Za-z0-9]{36}",
                r"AKIA[0-9A-Z]{16}", r"xox[baprs]-[A-Za-z0-9-]{20,}", r"AIza[0-9A-Za-z_-]{35}"]

    def test_no_tracked_file_holds_a_key(self):
        files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True)
        if files.returncode != 0:
            self.skipTest("not a git checkout")
        hits = []
        for rel in filter(None, files.stdout.split("\0")):
            if rel.endswith((".png", ".jpg", ".ico", ".woff2")):
                continue  # (the sentinels above are built from parts, so they match nothing here)
            try:
                with open(os.path.join(ROOT, rel), encoding="utf-8", errors="ignore") as fh:
                    text = fh.read()
            except OSError:
                continue
            hits += [f"{rel}: {m.group(0)[:8]}…" for p in self.PATTERNS for m in re.finditer(p, text)]
        self.assertEqual(hits, [])

    def test_key_files_and_env_files_are_ignored(self):
        ignored = slurp(os.path.join(ROOT, ".gitignore"))
        for pattern in ("*.key", ".env", "providers.json"):
            self.assertIn(pattern, ignored)


class Dashboard(unittest.TestCase):
    def test_the_dashboard_command_runs_the_one_generator(self):
        for path in ("commands/dashboard.md", ".claude/commands/dashboard.md"):
            text = slurp(os.path.join(ROOT, path))
            self.assertIn("scripts/providers.py", text, path)
        self.assertIn("`desk dashboard`", slurp(os.path.join(ROOT, "skills", "desk", "SKILL.md")))

if __name__ == "__main__":
    unittest.main()
