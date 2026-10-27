#!/usr/bin/env python3
"""The review providers, in one place, and the dashboard that shows and edits them.

    python3 providers.py                     the dashboard as text: what is set up, whether it
                                             answers, which review lanes this machine has, what
                                             is missing and the exact step to add it
    python3 providers.py --no-ping           the same without calling anyone
    python3 providers.py html <file>         the same dashboard as one static page
    python3 providers.py serve [--port N]    the dashboard as a local page that also edits
                                             where each key comes from (this machine only)
    python3 providers.py set <name> --url <base_url> --model <model> --key <source> [--lane vendor|private]
    python3 providers.py set openrouter --key <source>
    python3 providers.py remove <name>
    python3 providers.py export [--env-file <path outside any repository>]
                                             the keys this machine has, by name and origin, and
                                             the steps to load them into a cloud environment

A provider is OpenRouter (free models only) or any endpoint that speaks the OpenAI chat API:
a model someone shares with a key, a model on your own machine, or a gateway in front of
Apple Intelligence. It is declared by name, base_url, model and where its key comes from:

    env:VAR      an environment variable (a shell, or a cloud environment's variables)
    file:NAME    a file in the Desk config folder, readable by you only (this machine)
    proxy        the network adds the key: a cloud environment's network secret
    none         no key (a server on your own machine that asks for none)

The declarations live in <config>/providers.json, written by this script only. A cloud
environment declares endpoints with variables instead: DESK_ENDPOINT_<NAME>_URL, _MODEL,
_KEY (the key itself, or `proxy`) and optionally _LANE. Keys are never written to that file,
to a repository, to answer files or to anything this script prints.

Standard library only.
"""
import html as htmlmod
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

OPENROUTER = "https://openrouter.ai/api/v1"
PROXY = "proxy"
CONF = os.environ.get("DESK_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".config", "desk")
HIDDEN = "[key hidden]"
SOURCE = re.compile(r"^(env:[A-Za-z_][A-Za-z0-9_]*|file:[A-Za-z0-9._-]+|proxy|none)$")
NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
# Reviewers must come from another family than the author (Claude).
SAME_FAMILY = re.compile(r"anthropic|claude", re.I)


def cloud():
    """True in a Claude Code cloud session. DESK_CLOUD=1 or 0 overrides, for tests and odd setups."""
    forced = os.environ.get("DESK_CLOUD", "").strip()
    if forced in ("0", "1"):
        return forced == "1"
    return os.environ.get("CLAUDE_CODE_REMOTE", "").strip().lower() == "true"


def read(conf, name):
    try:
        with open(os.path.join(conf, name), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def load(conf=None):
    """The declarations file, or an empty one. A file that cannot be read is an error, not empty."""
    path = os.path.join(conf or CONF, "providers.json")
    if not os.path.exists(path):
        return {"openrouter": {}, "endpoints": {}}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("openrouter", {})
    data.setdefault("endpoints", {})
    return data


def save(data, conf=None):
    conf = conf or CONF
    for name, e in list(data.get("endpoints", {}).items()) + [("openrouter", data.get("openrouter", {}))]:
        src = e.get("key", "")
        if src and not SOURCE.match(src):
            raise ValueError(f"{name}: a key source is env:VAR, file:NAME, proxy or none. "
                             "The key itself never goes in this file.")
    os.makedirs(conf, exist_ok=True)
    path = os.path.join(conf, "providers.json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    os.replace(path + ".tmp", path)


class Provider:
    """One place a review can be sent. `secret()` is the only way to the key, and nothing prints it."""

    def __init__(self, name, kind, base_url, model, source, lane="vendor", origin="", conf=None, value=None):
        self.name, self.kind, self.base_url, self.model = name, kind, base_url.rstrip("/"), model
        self.source, self.lane, self.origin, self.conf = source, lane, origin, conf or CONF
        self._value = value  # set only for keys that came in an environment variable of a cloud declaration

    def __repr__(self):  # never the key
        return f"Provider({self.name}, {self.kind}, {self.base_url}, {self.model}, key from {self.source})"

    def secret(self):
        if self._value is not None:
            return self._value
        if self.source.startswith("env:"):
            return os.environ.get(self.source[4:], "").strip()
        if self.source.startswith("file:"):
            return read(self.conf, self.source[5:])
        return ""

    def has_key(self):
        return self.source in (PROXY, "none") or bool(self.secret())

    def headers(self):
        h = {"Content-Type": "application/json", "X-Title": "Desk review"}
        k = self.secret()
        if k and self.source != PROXY:
            h["Authorization"] = "Bearer " + k
        return h

    def problem(self):
        """Why nothing may be sent to this provider, or ''."""
        u = urllib.parse.urlparse(self.base_url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return f"base_url is not an http(s) address: {self.base_url}"
        if u.scheme == "http" and self.secret() and not local_host(u.hostname):
            return "a key would travel unencrypted (http) to another machine; use https"
        if self.kind == "endpoint" and self.lane == "vendor" and SAME_FAMILY.search(self.model + self.base_url):
            return "a Claude model cannot review Claude's answers; this lane needs another family"
        return ""


def local_host(host):
    if host in ("localhost",) or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def openrouter(conf=None):
    """OpenRouter, from the first place that has its key, or None."""
    conf = conf or CONF
    declared = load(conf).get("openrouter", {}).get("key", "")
    if os.environ.get("DESK_REVIEW_KEY", "").strip() == PROXY:
        src, origin = PROXY, "network secret (DESK_REVIEW_KEY=proxy)"
    elif declared:
        src, origin = declared, "dashboard"
    elif os.environ.get("OPENROUTER_API_KEY", "").strip():
        src, origin = "env:OPENROUTER_API_KEY", "environment variable"
    elif read(conf, "openrouter.key"):
        src, origin = "file:openrouter.key", "key file"
    else:
        return None
    return Provider("openrouter", "openrouter", OPENROUTER, ":free models only", src, origin=origin, conf=conf)


def endpoints(conf=None):
    """Every declared OpenAI-compatible endpoint: the cloud environment's variables win over the file."""
    conf = conf or CONF
    out = {}
    for name, e in sorted(load(conf).get("endpoints", {}).items()):
        out[name] = Provider(name, "endpoint", e.get("base_url", ""), e.get("model", ""), e.get("key", "none"),
                             e.get("lane", "vendor"), "dashboard", conf)
    for var in sorted(os.environ):
        m = re.match(r"^DESK_ENDPOINT_([A-Z0-9_]+)_URL$", var)
        if not m:
            continue
        up = m.group(1)
        name = up.lower().replace("_", "-")
        key = os.environ.get(f"DESK_ENDPOINT_{up}_KEY", "").strip()
        src = PROXY if key == PROXY else (f"env:DESK_ENDPOINT_{up}_KEY" if key else "none")
        out[name] = Provider(name, "endpoint", os.environ[var].strip(), os.environ.get(f"DESK_ENDPOINT_{up}_MODEL", "").strip(),
                             src, os.environ.get(f"DESK_ENDPOINT_{up}_LANE", "vendor").strip().lower() or "vendor",
                             "environment variables", conf)
    return list(out.values())


def all_secrets(conf=None):
    """Every key this process could send, so that `redact` can hide each one wherever it appears."""
    ps = endpoints(conf) + [p for p in [openrouter(conf)] if p]
    vals = {p.secret() for p in ps}
    vals.add(os.environ.get("OPENROUTER_API_KEY", "").strip())
    vals.add(read(conf or CONF, "openrouter.key"))
    return sorted((v for v in vals if len(v) >= 8), key=len, reverse=True)


def redact(text, conf=None):
    """The text with every known key replaced, and anything that looks like a bearer token too."""
    text = str(text)
    for v in all_secrets(conf):
        text = text.replace(v, HIDDEN)
    return re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}", r"\1" + HIDDEN, text)


def call(p, path, payload=None, timeout=15):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(p.base_url + path, data=data, headers=p.headers())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "{}")


def ping(p):
    """(state, detail). A cheap call that spends no tokens where the API allows it.

    ok · refused (the key or its absence was turned down) · unreachable · error · blocked
    """
    why = p.problem()
    if why:
        return "blocked", why
    try:
        if p.kind == "openrouter":
            d = call(p, "/key").get("data") or {}
            bits = [f'label "{d["label"]}"'] if d.get("label") else []
            if "limit" in d:
                bits.append("limit " + ("none" if d["limit"] is None else str(d["limit"])))
            return "ok", ", ".join(bits) or "key accepted"
        try:
            ids = [m.get("id", "") for m in call(p, "/models").get("data", [])]
            return "ok", ("model listed" if p.model in ids else f"answers; model {p.model} not in its list")
        except urllib.error.HTTPError as e:
            if e.code not in (404, 405):
                raise
            call(p, "/chat/completions", {"model": p.model, "max_tokens": 1,
                                          "messages": [{"role": "user", "content": "ping"}]}, timeout=30)
            return "ok", "answers (one-token ping)"
    except urllib.error.HTTPError as e:
        said = (e.headers.get("X-Proxy-Error") or "") if getattr(e, "headers", None) else ""
        state = "refused" if e.code in (401, 403) else "error"
        return state, redact(f"HTTP {e.code}" + (f"; proxy says: {said}" if said else ""), p.conf)
    except Exception as e:  # DNS, refused, timeout, not JSON
        return "unreachable", redact(f"{type(e).__name__}: {e}", p.conf)[:200]


def command_lanes(conf):
    lanes = []
    for line in read(conf, "reviewers.txt").splitlines():
        if "|" in line and not line.strip().startswith("#"):
            name, cmd = line.split("|", 1)
            if name.strip() and cmd.strip():
                lanes.append((name.strip(), cmd.strip()))
    return lanes


def private_terms(conf):
    """(terms, where they came from). DESK_PRIVATE_TERMS is for a cloud session, where no file survives."""
    env = os.environ.get("DESK_PRIVATE_TERMS", "")
    if env.strip():
        return [t.strip() for t in re.split(r"[;\n]", env) if t.strip() and not t.strip().startswith("#")], "DESK_PRIVATE_TERMS"
    text = read(conf, "private-terms.txt")
    return [t.strip() for t in text.splitlines() if t.strip() and not t.strip().startswith("#")], ("private-terms.txt" if text else "")


# ---------------------------------------------------------------- the dashboard

def steps_openrouter(is_cloud):
    if is_cloud:
        return ["Create a free key at openrouter.ai (Keys).",
                "In the cloud environment's settings (environment menu, then Edit), add a network secret "
                "for the host openrouter.ai holding that key, and the variable DESK_REVIEW_KEY=proxy. "
                "Where there are no network secrets, add the variable OPENROUTER_API_KEY=<the key> instead.",
                "Allow openrouter.ai in the environment's network access if it is limited.",
                "Start a new session; run this dashboard again."]
    return ["Create a free key at openrouter.ai (Keys).",
            "Run `python3 providers.py serve`, open the page it prints, and paste the key in the OpenRouter row. "
            "It is written to the Desk config folder, readable by you only, and never shown again."]


def steps_endpoint(is_cloud):
    if is_cloud:
        return ["In the cloud environment's settings add the variables DESK_ENDPOINT_<NAME>_URL (the base_url, "
                "ending in /v1), DESK_ENDPOINT_<NAME>_MODEL and DESK_ENDPOINT_<NAME>_KEY (the key, or `proxy` "
                "when a network secret for that host carries it). Add DESK_ENDPOINT_<NAME>_LANE=private only for "
                "a machine you control. Allow its host in network access. Start a new session."]
    return ["Run `python3 providers.py serve` and add it in the Endpoints form: name, base_url, model, where its key comes from."]


def gather(conf=None, do_ping=True):
    """Everything the dashboard shows, as data. No key values anywhere in it."""
    conf = conf or CONF
    is_cloud = cloud()
    rows, missing = [], []
    try:
        load(conf)
        conf_error = ""
    except (OSError, ValueError) as e:
        conf_error = f"{os.path.join(conf, 'providers.json')} cannot be read ({e}); fix or move it aside"
    orp = openrouter(conf) if not conf_error else None
    if orp:
        state, detail = ping(orp) if do_ping else ("not checked", "")
        if not orp.has_key():
            state, detail = "no key", f"{orp.source} is empty"
        rows.append({"name": "openrouter", "kind": "OpenRouter, free models", "where": OPENROUTER,
                     "key": orp.source, "origin": orp.origin, "lane": "vendors", "state": state, "detail": detail})
        if state in ("refused", "no key"):
            missing.append(("OpenRouter key does not work here", ["The key is missing, wrong or revoked: create a new one."]
                            + steps_openrouter(is_cloud)[1:]))
    else:
        missing.append(("Cross-vendor review: no OpenRouter key", steps_openrouter(is_cloud)))
    for p in endpoints(conf) if not conf_error else []:
        state, detail = ping(p) if do_ping else ("not checked", p.problem())
        if not p.has_key():
            state, detail = "no key", f"{p.source} is empty"
        rows.append({"name": p.name, "kind": "OpenAI-compatible endpoint", "where": p.base_url + "  ·  " + p.model,
                     "key": p.source, "origin": p.origin, "lane": "private lane" if p.lane == "private" else "vendor",
                     "state": state, "detail": detail})
        if state not in ("ok", "not checked"):
            missing.append((f"Endpoint {p.name}: {state}", [detail] + steps_endpoint(is_cloud)))
    if not any(r["kind"].startswith("OpenAI") for r in rows):
        missing.append(("Optional: an endpoint (someone's shared model, your own, or an Apple Intelligence gateway)",
                        steps_endpoint(is_cloud)))
    lanes = []
    ok = [r for r in rows if r["state"] in ("ok", "not checked")]
    lanes.append(("Free models from other vendors (OpenRouter)",
                  "on" if any(r["name"] == "openrouter" for r in ok) else "off: no working key"))
    for r in rows:
        if r["kind"].startswith("OpenAI"):
            lanes.append((f"Endpoint {r['name']} ({r['lane']})", "on" if r in ok else f"off: {r['state']}"))
    for name, cmd in command_lanes(conf):
        exe = (cmd.split() or [""])[0]
        lanes.append((f"Your command lane {name}", "on" if shutil.which(exe) else f"off: `{exe}` is not installed here"))
    shortcut = read(conf, "apple-shortcut")
    if is_cloud:
        lanes.append(("Apple Intelligence through a macOS Shortcut", "off in the cloud: macOS only; use a gateway endpoint"))
    elif shortcut:
        lanes.append((f'Apple Intelligence, Shortcut "{shortcut}"', "on" if shutil.which("shortcuts") else "off: not a Mac"))
    lanes.append(("Same-vendor pass (a desk-reader subagent)", "on: always; labelled [same-vendor]"))
    terms, terms_from = private_terms(conf)
    if not terms:
        missing.append(("Private terms: names are not checked before a packet leaves",
                        ["In the cloud environment's settings add DESK_PRIVATE_TERMS, terms separated by `;`."] if is_cloud else
                        [f"Write the names and words that must never leave, one per line, to {os.path.join(conf, 'private-terms.txt')}."]))
    if conf_error:
        missing.insert(0, ("The providers file is broken", [conf_error]))
    return {"environment": "cloud" if is_cloud else "local", "config": conf, "providers": rows, "lanes": lanes,
            "private_terms": f"{len(terms)} from {terms_from}" if terms else "none", "missing": missing}


def text(d):
    out = [f"Desk providers · environment: {d['environment']} · keys are never shown", ""]
    out.append("Providers")
    if not d["providers"]:
        out.append("  none set up")
    for r in d["providers"]:
        out.append(f"  {r['name']:<12} {r['state']:<12} {r['kind']}")
        out.append(f"  {'':<12} {'':<12} {r['where']}")
        out.append(f"  {'':<12} {'':<12} key from {r['key']} ({r['origin']})" + (f" · {r['detail']}" if r['detail'] else ""))
    out += ["", "Review lanes here"]
    out += [f"  {name}: {state}" for name, state in d["lanes"]]
    out += ["", f"Private terms: {d['private_terms']}", "", "Missing"]
    if not d["missing"]:
        out.append("  nothing")
    for title, steps in d["missing"]:
        out.append(f"  - {title}")
        out += [f"      {i}. {s}" for i, s in enumerate(steps, 1)]
    return "\n".join(out) + "\n"


CSS = """:root{--bg:#fbfaf7;--fg:#1d1d1b;--mute:#6b6a65;--line:#e3e1da;--ok:#1f7a4d;--bad:#a3341f}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--mute:#9a988f;--line:#33322f;--ok:#5fc08d;--bad:#ec8a73}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0 auto;max-width:860px;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}p.m{color:var(--mute);margin:0}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);padding:6px 8px 6px 0;text-align:left;vertical-align:top}
th{color:var(--mute);font-weight:500}.ok{color:var(--ok)}.bad{color:var(--bad)}code{font-size:13px}
input,select,button{font:inherit;padding:4px 6px}form{margin:6px 0}li{margin:4px 0}.wrap{overflow-x:auto}"""


def page(d, forms=""):
    e = htmlmod.escape

    def state(s):
        return f'<span class="{"ok" if s in ("ok", "not checked") or s.startswith("on") else "bad"}">{e(s)}</span>'
    rows = "".join(f"<tr><td><b>{e(r['name'])}</b><br>{e(r['kind'])}</td><td><code>{e(r['where'])}</code></td>"
                   f"<td><code>{e(r['key'])}</code><br>{e(r['origin'])}</td><td>{state(r['state'])}<br>{e(r['detail'])}</td></tr>"
                   for r in d["providers"]) or '<tr><td colspan="4">none set up</td></tr>'
    lanes = "".join(f"<tr><td>{e(n)}</td><td>{state(s)}</td></tr>" for n, s in d["lanes"])
    miss = "".join(f"<li><b>{e(t)}</b><ol>" + "".join(f"<li>{e(s)}</li>" for s in st) + "</ol></li>" for t, st in d["missing"]) or "<li>nothing</li>"
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>Desk providers</title><style>{CSS}</style></head><body><h1>Desk providers</h1>"
            f"<p class=m>Environment: {e(d['environment'])} · config folder {e(d['config'])} · key values are never shown</p>"
            f'<h2>Providers</h2><div class="wrap"><table><tr><th>Name</th><th>Where</th><th>Key from</th><th>State</th></tr>{rows}</table></div>'
            f"{forms}<h2>Review lanes here</h2><table>{lanes}</table><h2>Private terms</h2><p>{e(d['private_terms'])}</p>"
            f"<h2>Missing, and the exact step</h2><ul>{miss}</ul></body></html>")


def edit_forms(d, token):
    e = htmlmod.escape
    sel = '<select name="source">' + "".join(f"<option>{s}</option>" for s in ("env:", "file:", "proxy", "none")) + "</select>"
    return (f'<h2>Edit</h2><p class=m>Saved to {e(os.path.join(d["config"], "providers.json"))}; a pasted key goes to its own file, readable by you only.</p>'
            f'<form method=post action="/{token}/openrouter">OpenRouter key from {sel} <input name="arg" placeholder="VAR or file name">'
            f' or paste the key <input type=password name="paste" autocomplete=off> <button>Save</button></form>'
            f'<form method=post action="/{token}/endpoint"><input name="name" placeholder="name" required size=10> '
            f'<input name="base_url" placeholder="https://host/v1" required> <input name="model" placeholder="model" required size=14> '
            f'key from {sel} <input name="arg" placeholder="VAR or file name" size=12> or paste <input type=password name="paste" autocomplete=off size=12> '
            f'<select name="lane"><option>vendor</option><option>private</option></select> <button>Save</button></form>'
            f'<form method=post action="/{token}/remove"><input name="name" placeholder="name" size=10> <button>Remove endpoint</button></form>')


def store_key(name, value, conf):
    """Write a pasted key to <conf>/<name>.key, mode 600. Never into a repository."""
    if inside_repo(conf):
        raise ValueError(f"{conf} is inside a git repository; a key is never written there. Set DESK_CONFIG_DIR elsewhere.")
    os.makedirs(conf, exist_ok=True)
    path = os.path.join(conf, f"{name}.key")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(value.strip() + "\n")
    os.chmod(path, 0o600)
    return f"file:{name}.key"


def inside_repo(path):
    d = os.path.abspath(path)
    while not os.path.isdir(d):
        d = os.path.dirname(d)
    p = subprocess.run(["git", "-C", d, "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
    return p.returncode == 0 and p.stdout.strip() == "true"


def apply(form, kind, conf):
    """One edit from the local page or the command line. Returns what changed, in words."""
    data = load(conf)
    src = form.get("source", "")
    if src in ("env:", "file:"):
        src += form.get("arg", "").strip()
    pasted = form.get("paste", "").strip()
    if kind == "remove":
        name = form.get("name", "").strip()
        if data["endpoints"].pop(name, None) is None:
            raise ValueError(f"no endpoint named {name} in the dashboard's file")
        save(data, conf)
        return f"removed {name}"
    name = "openrouter" if kind == "openrouter" else form.get("name", "").strip().lower()
    if not NAME.match(name) or (kind == "endpoint" and name == "openrouter"):
        raise ValueError("a name is lowercase letters, digits and dashes, starting with a letter")
    if pasted:
        src = store_key(name, pasted, conf)
    if src and not SOURCE.match(src):
        raise ValueError("a key source is env:VAR, file:NAME, proxy or none")
    if kind == "openrouter":
        data["openrouter"] = {"key": src} if src else {}
    else:
        lane = form.get("lane", "vendor")
        if lane not in ("vendor", "private"):
            raise ValueError("lane is vendor or private")
        p = Provider(name, "endpoint", form.get("base_url", "").strip(), form.get("model", "").strip(), src or "none", lane, conf=conf)
        if not p.model or p.problem():
            raise ValueError(p.problem() or "a model is needed")
        data["endpoints"][name] = {"base_url": p.base_url, "model": p.model, "key": p.source, "lane": lane}
    save(data, conf)
    return f"saved {name} (key from {src or 'none'})"


def make_server(conf, port=0):
    """(server, url): the dashboard as a page on this machine only, edit forms behind a one-time path."""
    import http.server
    token = secrets.token_urlsafe(16)

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):  # nothing about requests reaches the terminal
            pass

        def send(self, body, code=200):
            b = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path.rstrip("/") != "/" + token:
                return self.send("not here", 404)
            d = gather(conf)
            self.send(page(d, edit_forms(d, token)))

        def do_POST(self):
            parts = self.path.strip("/").split("/")
            if len(parts) != 2 or parts[0] != token or parts[1] not in ("openrouter", "endpoint", "remove"):
                return self.send("not here", 404)
            n = int(self.headers.get("Content-Length") or 0)
            form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode()).items()}
            try:
                said = apply(form, parts[1], conf)
            except (ValueError, OSError) as e:
                said = f"not saved: {e}"
            d = gather(conf)
            self.send(page(d, f"<p><b>{htmlmod.escape(redact(said, conf))}</b></p>" + edit_forms(d, token)))

    srv = http.server.HTTPServer(("127.0.0.1", port), H)
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/{token}"


def serve(conf, port):
    if cloud():
        print("In a cloud session nobody can open a page on this machine, and keys are set in the cloud "
              "environment's settings. Showing the dashboard instead.\n")
        print(text(gather(conf)), end="")
        return 0
    srv, url = make_server(conf, port)
    print(f"Desk providers dashboard: {url}\n(this machine only; stop it with Ctrl-C)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


# ---------------------------------------------------------------- export to a cloud environment

KNOWN_ENV = ("OPENROUTER_API_KEY",)


def export(conf, env_file=""):
    """The keys this machine has: names and origins only. With env_file, also a file to paste from."""
    found = []  # (variable for the cloud, origin, value, host)
    orp = openrouter(conf)
    if orp and orp.source != PROXY and orp.secret():
        found.append(("OPENROUTER_API_KEY", f"{orp.origin} ({orp.source})", orp.secret(), "openrouter.ai"))
    for p in endpoints(conf):
        if p.source not in (PROXY, "none") and p.secret():
            up = p.name.upper().replace("-", "_")
            found += [(f"DESK_ENDPOINT_{up}_KEY", f"{p.origin} ({p.source})", p.secret(), urllib.parse.urlparse(p.base_url).hostname or "")]
    plain = []
    for p in endpoints(conf):
        up = p.name.upper().replace("-", "_")
        plain += [(f"DESK_ENDPOINT_{up}_URL", p.base_url), (f"DESK_ENDPOINT_{up}_MODEL", p.model)]
        if p.lane != "vendor":
            plain.append((f"DESK_ENDPOINT_{up}_LANE", p.lane))
    terms, _ = private_terms(conf)
    print("Keys on this machine (names and origins only):")
    for var, origin, _, host in found:
        print(f"  {var:<34} from {origin} · for {host}")
    if not found:
        print("  none found")
    print("\nTo load them into a cloud environment (no tool can do it for you: it is your account's setting):")
    print("  1. Open the cloud environment's settings: the environment menu in a cloud session's title bar, then Edit.")
    print("  2. Each key: where the settings offer network secrets, add one for its host with the key as the value, and")
    print("     set the variable to `proxy` (OpenRouter: DESK_REVIEW_KEY=proxy) so the session never sees the key.")
    print("     Otherwise add it as an environment variable with the name shown above.")
    if plain or terms:
        print("  3. Add these variables too (no secrets in them):")
        for k, v in plain:
            print(f"       {k}={v}")
        if terms:
            print(f"       DESK_PRIVATE_TERMS=<your {len(terms)} private terms, separated by ;>")
    print("  4. Start a new cloud session and run `python3 providers.py` there: each provider should say ok.")
    if env_file:
        path = os.path.abspath(env_file)
        if inside_repo(os.path.dirname(path)):
            print(f"\nNOT WRITTEN: {path} is inside a git repository. Keys never go there.", file=sys.stderr)
            return 1
        if os.path.exists(path):
            print(f"\nNOT WRITTEN: {path} exists; choose a new name.", file=sys.stderr)
            return 1
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("# Paste into the cloud environment's settings, then delete this file.\n")
            for var, _, val, _ in found:
                f.write(f"{var}={val}\n")
            for k, v in plain:
                f.write(f"{k}={v}\n")
            if terms:
                f.write("DESK_PRIVATE_TERMS=" + ";".join(terms) + "\n")
        print(f"\nWritten, readable by you only: {path}\nIt holds the values. Paste it into the settings, then delete it.")
    return 0


def main(argv):
    a = argv[1:]
    conf = CONF
    if a[:1] in (["-h"], ["--help"], ["help"]):
        print(__doc__)
        return 0
    if not a or a[0] == "--no-ping":
        print(text(gather(conf, do_ping=not a)), end="")
        return 0
    if a[0] == "html" and len(a) == 2:
        d = gather(conf)
        with open(a[1], "w", encoding="utf-8") as f:
            f.write(page(d))
        print(f"dashboard written: {os.path.abspath(a[1])}")
        print(text(d), end="")
        return 0
    if a[0] == "serve":
        port = int(a[a.index("--port") + 1]) if "--port" in a else 0
        return serve(conf, port)
    if a[0] == "export":
        return export(conf, a[a.index("--env-file") + 1] if "--env-file" in a and a.index("--env-file") + 1 < len(a) else "")
    if a[0] in ("set", "remove") and len(a) >= 2:
        opts = {}
        for flag in ("--url", "--model", "--key", "--lane"):
            if flag in a and a.index(flag) + 1 < len(a):
                opts[flag[2:]] = a[a.index(flag) + 1]
        src = opts.get("key", "")
        form = {"name": a[1], "base_url": opts.get("url", ""), "model": opts.get("model", ""),
                "lane": opts.get("lane", "vendor"), "source": src}
        kind = "remove" if a[0] == "remove" else ("openrouter" if a[1] == "openrouter" else "endpoint")
        try:
            print(apply(form, kind, conf))
        except ValueError as e:
            print(f"not saved: {e}", file=sys.stderr)
            return 2
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
