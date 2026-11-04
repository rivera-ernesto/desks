#!/usr/bin/env python3
"""Send one review packet to several AI models from other vendors and print a label.

    python3 review.py <packet.md> ["what to look for"]  [--background]
    python3 review.py --verify <receipt>  [folder to search]
    python3 review.py --status <packet.md>      (the tail of a background run)
    python3 review.py --check                   (is a review key set up? which lanes? sends nothing)
    python3 review.py --test                    (asks each provider whether its key works;
                                                 sends no packet and spends nothing)

It asks one model per family, in parallel: free models through OpenRouter, and
any free-tier provider the user has set up a key for. It writes each answer
next to the packet, in <packet>-reviews/, with a ledger and a receipt.
Standard library only: nothing to install.

Setup lives outside any project, so a key is never committed by accident:
    ~/.config/desk/openrouter.key   the key, one line (or env OPENROUTER_API_KEY)
    ~/.config/desk/private-terms.txt  words that must never leave this machine
    ~/.config/desk/reviewers.txt    extra lanes: name | command reading stdin
    ~/.config/desk/<provider>.key   a free-tier key for groq, gemini, mistral,
                                    cerebras or github (GitHub Models)
    ~/.config/desk/providers.txt    any OpenAI-compatible endpoint, one per line:
                                    name | base url | model [| key file]
                                    (a localhost one, e.g. Ollama, also reviews
                                    packets that must not leave the machine)
    ~/.config/desk/apple-shortcut   name of a macOS Shortcut (private lane)

A folder with its own rules says so in the Desk block (`desk.py set`):
    Gate: <command>          run as `<command> <file> public|private`; exit 0 and a first line of exactly `OK`
                             (or `PASS`) lets that tier go, anything else refuses (fails closed).
                             When there is a gate, the built-in scan and the private-terms list stand down.
    Private lane: <command>  run as `<command> <packet>`, answer on stdout; exit 3 means "packet too large"
    Reviews: <name>          the answers folder, `{stem}` is the packet's name (default `{stem}-reviews`)
    Dispositions: <name>     the file that closes a review (default `{stem}-dispositions.md`)

Environment: DESK_REVIEW_N families to ask at once (6) - DESK_REVIEW_MIN answers
wanted (3) - DESK_REVIEW_MODELS comma list instead of the live catalogue -
DESK_REVIEW_WATCHDOG seconds before a background run is stopped (1500).

Exit codes: 0 enough families answered (the label is open until every finding has a disposition)
            1 packet refused by the gate or the built-in scan - 2 usage - 3 no key and no other lane
            4 nobody answered - 5 not sent: the folder reviews its own way, or its Desk block cannot be read
            6 fewer families answered than wanted, or only the private lane
            7 a background run was stopped by its watchdog
            (--verify: 0 the receipt checks out, its label now is printed - 1 no receipt, a stale packet, or a receipt that does not sit in its packet's review folder)

`--alongside` is self-declared: any caller can pass it, so it only says "this run was started as the second
opinion of the folder's own routine". It is a courtesy flag, not proof, and nothing here depends on it for safety.
"""
import concurrent.futures as cf
import datetime
import importlib.util
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://openrouter.ai/api/v1"
CONF = os.environ.get("DESK_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".config", "desk")  # as desk.py (#62)
SYSTEM = (
    "You are an independent reviewer from a different model vendor than the author. "
    "The author is Claude (Anthropic). Your value is that you think differently: say what "
    "the author would likely miss or agree with too easily. Be concrete and adversarial "
    "about the reasoning, not the prose. If the proposal is sound, say which single claim "
    "carries the most risk and why. Answer in under 500 words."
)
# Models that answer nothing useful to a review prompt.
SKIP = ("guard", "safety", "moderation", "embed", "anthropic/", "thinkingmachines/")
# ...and, in a direct provider's list, models that are not for chat.
SKIP_DIRECT = SKIP + ("tts", "whisper", "transcri", "audio", "image", "imagen", "veo", "realtime",
                      "live", "aqa", "ocr", "rerank", "-search", "orpheus", "playai")

# Direct providers with a free tier, set up by putting a key in ~/.config/desk/<name>.key.
# Each speaks the OpenAI chat format. The patterns choose its model from the live list:
# the first pattern that matches a family not already asked, the newest match. They are
# patterns and not fixed ids because the lists change every few weeks. A line in
# providers.txt with the same name pins the model instead.
PROVIDERS = {
    "groq": {"base": "https://api.groq.com/openai/v1",
             "prefer": [r"gpt-oss-120b", r"kimi-k\d", r"qwen3?-.*32b|qwen3", r"llama-4-maverick", r"llama-3\.3-70b", r"llama"]},
    "gemini": {"base": "https://generativelanguage.googleapis.com/v1beta/openai",
               "prefer": [r"^gemini-[\d.]+-pro$", r"^gemini-[\d.]+-flash$", r"^gemini-[\d.]+-pro", r"^gemini-[\d.]+-flash(?!-lite)", r"^gemini"]},
    "mistral": {"base": "https://api.mistral.ai/v1",
                "prefer": [r"^mistral-large-latest$", r"^mistral-medium-latest$", r"^magistral-medium-latest$", r"^mistral-small-latest$"]},
    "cerebras": {"base": "https://api.cerebras.ai/v1",
                 "prefer": [r"gpt-oss-120b", r"qwen-3.*235b", r"glm", r"llama.*70b", r"qwen", r"llama"]},
    "github": {"base": "https://models.github.ai/inference", "models": "https://models.github.ai/catalog/models",
               "prefer": [r"^openai/gpt-\d", r"^deepseek/", r"^meta/llama", r"^mistral-ai/", r"^xai/", r"^microsoft/", r"^cohere/"]},
}

# Who made a model, whoever hosts it: one answer per maker is what makes a review cross-vendor.
VENDOR_ALIASES = {"meta-llama": "meta", "deepseek-ai": "deepseek", "xai": "x-ai", "zai-org": "z-ai",
                  "mistral-ai": "mistralai", "mistral": "mistralai", "alibaba": "qwen"}
VENDOR_WORDS = [
    (r"llama", "meta"), (r"gemma|gemini", "google"), (r"qwen|qwq", "qwen"),
    (r"mistral|mixtral|magistral|codestral|ministral|devstral|pixtral", "mistralai"),
    (r"gpt|^o\d", "openai"), (r"deepseek", "deepseek"), (r"kimi", "moonshotai"), (r"glm", "z-ai"),
    (r"nemotron", "nvidia"), (r"command|aya", "cohere"), (r"phi-?\d", "microsoft"), (r"grok", "x-ai"),
    (r"claude", "anthropic"), (r"granite", "ibm"),
]
MIN_CHARS = 200  # a one-word or empty answer does not count as a review

# Things that should not leave the machine whatever the topic is.
BUILTIN_PRIVATE = [
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "an email address"),
    (r"(?<![\w.])\+?\d[\d\s().-]{8,}\d(?![\w.])", "a phone-like number"),
    (r"\b(sk|pk|ghp|gho|xox[bp])[-_][A-Za-z0-9_-]{16,}", "something that looks like a key"),
]
# Dates and times are not phone numbers (#24): 2026-10-15, 2026-10-15T09:30, 2026-10-14..16.
# They are blanked before the scan, so a real number next to a date is still found.
DATES = re.compile(r"(?<![\w.])\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?(?:\.\.\d{2})?(?![\w])")


def conf(name):
    p = os.path.join(CONF, name)
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


# In a cloud session the environment can add the key on the way out (a network secret), so the
# session never holds it. Then there is no key here, and this stands in for it: no header is sent.
PROXY = "(added by the environment)"
_probed = {}


def cloud():
    """A Claude Code cloud session (CLAUDE_CODE_REMOTE=true). DESK_CLOUD=1 or 0 overrides, as in desk.py."""
    forced = os.environ.get("DESK_CLOUD", "").strip()
    if forced in ("0", "1"):
        return forced == "1"
    return os.environ.get("CLAUDE_CODE_REMOTE", "").strip().lower() == "true"


def api_key(probe=False):
    """The OpenRouter key: OPENROUTER_API_KEY, then openrouter.key. In a cloud session with neither, and
    only when `probe` allows the network, ask OpenRouter once, with no key, whether the environment adds one."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip() or conf("openrouter.key")
    if key or not (probe and cloud()):
        return key
    if "ok" not in _probed:
        try:
            _probed["ok"] = bool(http(API + "/key", timeout=15).get("data"))
        except Exception:
            _probed["ok"] = False
    return PROXY if _probed["ok"] else ""


def vendor_of(model, fallback=""):
    """The maker of a model id, as one name: meta-llama/llama-4 and llama-3.3-70b are both meta."""
    m = model.lower()
    if m.startswith("models/"):
        m = m[len("models/"):]
    if "/" in m:
        prefix = m.split("/")[0]
        return VENDOR_ALIASES.get(prefix, prefix)
    for pat, vendor in VENDOR_WORDS:
        if re.search(pat, m):
            return vendor
    return fallback or m.split(":")[0].split("-")[0]


def is_local(url):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host in ("localhost", "::1") or host.startswith("127.")


def direct_lanes():
    """Providers asked directly: the presets with a key file, and every providers.txt line."""
    lanes, pinned = [], {}
    for line in conf("providers.txt").splitlines():
        if line.strip().startswith("#") or "|" not in line:
            continue
        parts = [x.strip() for x in line.split("|")]
        name, base, model = (parts + ["", "", ""])[:3]
        keyfile = parts[3] if len(parts) > 3 and parts[3] else name + ".key"
        if not name:
            continue
        if name in PROVIDERS and not base:
            pinned[name] = model  # a preset with its model pinned
            continue
        if base and model:
            lanes.append({"name": name, "base": base.rstrip("/"), "model": model, "key": conf(keyfile),
                          "local": is_local(base)})
    for name, prov in PROVIDERS.items():
        key = conf(name + ".key")
        if key and name not in {l["name"] for l in lanes}:
            lanes.append({"name": name, "base": prov["base"], "model": pinned.get(name), "key": key,
                          "prefer": prov["prefer"], "models": prov.get("models"), "local": False})
    return lanes


def model_ids(data):
    items = data if isinstance(data, list) else (data or {}).get("data", [])
    ids = []
    for m in items:
        i = (m.get("id") or m.get("name") or "") if isinstance(m, dict) else str(m)
        if i.startswith("models/"):
            i = i[len("models/"):]
        if i:
            ids.append(i)
    return ids


def newest(ids):
    return max(ids, key=lambda i: ([int(n) for n in re.findall(r"\d+", i)], -len(i)))


def choose(lane, ids, taken):
    """The model this lane asks: the first preferred pattern that brings a family not yet asked."""
    ids = [i for i in ids if not any(x in i.lower() for x in SKIP_DIRECT)]
    for pat in lane["prefer"]:
        found = [i for i in ids if re.search(pat, i, re.I) and vendor_of(i, lane["name"]) not in taken | {"anthropic"}]
        if found:
            return newest(found)
    return None


def explain(e):
    if isinstance(e, urllib.error.HTTPError):
        if e.code in (401, 403):
            return f"the key was refused (HTTP {e.code})"
        return f"HTTP {e.code}"
    return f"could not reach it ({type(e).__name__}: {e})"[:200]


def resolve_lanes(lanes):
    """Give every direct lane its model and family, one lane per family. Lanes that cannot answer
    are returned apart, with the reason, so the user hears about a bad key instead of a silent gap."""
    def listing(lane):
        if lane.get("model"):
            return None
        try:
            return model_ids(http(lane.get("models") or lane["base"] + "/models", key=lane["key"], timeout=20))
        except Exception as e:
            return e

    with cf.ThreadPoolExecutor(max_workers=max(len(lanes), 1)) as ex:
        lists = list(ex.map(listing, lanes))
    ready, broken, taken = [], [], set()
    for lane, ids in zip(lanes, lists):
        if isinstance(ids, Exception):
            broken.append((lane["name"], explain(ids)))
            continue
        model = lane.get("model") or choose(lane, ids, taken)
        if not model:
            broken.append((lane["name"], "no model in its list matches; pin one in providers.txt"))
            continue
        vendor = vendor_of(model, lane["name"])
        if vendor == "anthropic" or vendor in taken:
            broken.append((lane["name"], f"{model} is by {vendor}, already asked or the author's family"))
            continue
        taken.add(vendor)
        ready.append(dict(lane, model=model, vendor=vendor))
    return ready, broken


def private_hits(text):
    """Why this packet must not be sent, or [] when it may go."""
    hits = []
    for line in conf("private-terms.txt").splitlines():
        term = line.strip()
        # A whole word or phrase, not part of a longer word (#51): "Mara" is not in "maracuya".
        if term and not term.startswith("#") and re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I):
            hits.append(f'your private term "{term}"')
    undated = DATES.sub(" ", text)
    for pattern, what in BUILTIN_PRIVATE:
        if re.search(pattern, undated):
            hits.append(what)
    return hits


def http(url, payload=None, key=None, timeout=100):
    headers = {"Content-Type": "application/json", "X-Title": "Desk review", "User-Agent": "desk-review"}
    if url.startswith(API):
        headers["HTTP-Referer"] = "https://github.com/rivera-ernesto/desks"
    if key and key != PROXY:
        headers["Authorization"] = "Bearer " + key
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def past_rates(folder):
    """vendor -> (calls, answered) across every ledger near this packet."""
    calls, ok = {}, {}
    root = os.path.dirname(folder) or "."
    for d, _, files in os.walk(root):
        if "ledger.tsv" in files:
            try:
                with open(os.path.join(d, "ledger.tsv"), encoding="utf-8") as fh:  # closed, not left to the collector (#49)
                    rows = fh.read().splitlines()
            except OSError:
                continue
            for r in rows[1:]:
                c = r.split("\t")
                if len(c) >= 5 and c[3] != "apple":
                    calls[c[3]] = calls.get(c[3], 0) + 1
                    ok[c[3]] = ok.get(c[3], 0) + (c[4] == "answered")
    return calls, ok


def pick_models(folder):
    """One free model per vendor, vendors that answered before first."""
    fixed = os.environ.get("DESK_REVIEW_MODELS", "").strip()
    if fixed:
        return [m.strip() for m in fixed.split(",") if m.strip()]
    data = http(API + "/models", timeout=30).get("data", [])
    best = {}
    for m in data:
        i = m.get("id", "")
        if not i.endswith(":free") or any(s in i for s in SKIP):
            continue
        vendor = vendor_of(i)
        # the largest context, then the most parameters, is a rough stand-in for a vendor's stronger model
        size = (m.get("context_length") or 0, max([int(n) for n in re.findall(r"(\d+)b(?![a-z])", i.lower())] or [0]))
        if vendor not in best or size > best[vendor][1]:
            best[vendor] = (i, size)
    ids = sorted(v[0] for v in best.values())
    if not ids:
        return []
    k = datetime.date.today().toordinal() % len(ids)  # rotate, so no vendor always goes first
    ids = ids[k:] + ids[:k]
    calls, ok = past_rates(folder)

    def band(i):
        v = vendor_of(i)
        n = calls.get(v, 0)
        if n < 5:
            return 1  # unknown
        return 0 if ok.get(v, 0) * 2 >= n else 2  # proven first, weak last, never dropped

    return sorted(ids, key=band)


def ask_openrouter(model, packet_text, focus, key):
    if not model.endswith(":free"):
        return "refused", f"'{model}' is not a free model; this script only asks free models"
    return ask_chat(API, model, packet_text, focus, key)


def ask_direct(lane, packet_text, focus):
    return ask_chat(lane["base"], lane["model"], packet_text, focus, lane["key"],
                    patience=600 if lane["local"] else 100)


def ask_chat(base, model, packet_text, focus, key, patience=100):
    """One review from any endpoint that speaks the OpenAI chat format."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"FOCUS: {focus}\n\n---\n\n{packet_text}"},
        ],
        "max_tokens": 6000,
        "temperature": 0.3,
    }
    last = ""
    for attempt in (1, 2):  # one retry: free endpoints fail under load for a minute or two
        try:
            r = http(base + "/chat/completions", body, key, timeout=patience)
            err = r.get("error") or ((r.get("choices") or [{}])[0] or {}).get("error")
            if err:  # OpenRouter can answer 200 with the upstream provider's error inside the choice
                last = json.dumps(err)[:400]
                if isinstance(err, dict) and err.get("code") == 429:
                    last = "429 " + last
            else:
                msg = r["choices"][0]["message"]
                content = msg.get("content") or ""
                if isinstance(content, list):  # some endpoints answer in parts
                    content = "".join(x.get("text", "") for x in content if isinstance(x, dict))
                text = content.strip()
                if not text and (msg.get("reasoning") or msg.get("reasoning_content")):
                    text = TRACE_MARK + "\n" + str(msg.get("reasoning") or msg.get("reasoning_content"))
                return ("answered" if substantive(text) else "thin-answer"), text
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: " + e.read().decode("utf-8", "replace")[:400]
        except Exception as e:  # network, timeout, malformed answer
            last = f"{type(e).__name__}: {e}"
            if "timed out" in last.lower():
                return "failed", last  # a model that slow will not be quick the second time
        if "free-models-per-day" in last:
            return "account-cap", last
        if "HTTP 401" in last or "HTTP 403" in last:
            return "key-refused", last  # a refused key is refused the second time too
        if attempt == 1:
            time.sleep(20)
    return ("rate-limited" if "429" in last else "failed"), last


THINK = r"(?:think|thinking|reasoning|reflection)"
TRACE_MARK = "[no content field; showing reasoning trace]"


def answer_text(text):
    """What a model said as an answer: tool-call spans, reasoning blocks and a bare trace removed."""
    t = re.sub(r"<\|tool_call_start\|>.*?<\|tool_call_end\|>", "", text or "", flags=re.S)
    t = re.sub(r"<(tool_call|function_call|tool_use)>.*?</\1>", "", t, flags=re.S)
    if t.lstrip().startswith(TRACE_MARK):
        return ""
    t = re.sub(rf"<({THINK})>.*?</\1>", "", t, flags=re.S | re.I)
    if re.search(rf"<{THINK}>", t, re.I):  # opened and never closed: all that follows is reasoning
        t = re.sub(rf"<{THINK}>.*\Z", "", t, flags=re.S | re.I)
    elif re.search(rf"</{THINK}>", t, re.I):  # closed with no opening: what came before is reasoning
        t = re.sub(rf"\A.*?</{THINK}>", "", t, flags=re.S | re.I)
    return t.strip()


def substantive(text):
    """An answer counts as a family's only when, after the removals above, it is at least MIN_CHARS of text."""
    return len(re.sub(r"\s", "", answer_text(text))) >= MIN_CHARS


def ask_command(command, packet_text, focus):
    """A reviewer the user already pays for: any command that reads a prompt on stdin."""
    prompt = f"{SYSTEM}\n\nFOCUS: {focus}\n\n---\n\n{packet_text}"
    try:
        p = subprocess.run(command, shell=True, input=prompt, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return "failed", "no answer within 300 s"
    text = (p.stdout or "").strip()
    if p.returncode != 0 or not text:
        return "failed", (p.stderr or "empty answer")[:400]
    return ("answered" if substantive(text) else "thin-answer"), text


def ask_apple(shortcut, packet_text, focus):
    """Apple's Private Cloud Compute through a macOS Shortcut.

    A successful run is not trusted by itself: the Shortcut can silently fall
    back to the small on-device model, which reads only the first few pages.
    So the prompt carries two random codes, one at the start and one after the
    input has been padded past that model's reach, and the answer must repeat
    both. Both present means this call read everything on the larger model.
    """
    if not shutil.which("shortcuts"):
        return "failed", "the 'shortcuts' command is not available (macOS only)"
    a, b = secrets.token_hex(6), secrets.token_hex(6)
    prompt = (
        f"Your reply MUST begin with this exact line: CANARY-A: {a}\n"
        "At the very end of the input there is a second code labelled CANARY-B. Your reply "
        "MUST contain it on its own line, as the last line.\n\n"
        f"{SYSTEM}\n\nFOCUS: {focus}\n\n---\n\n{packet_text}\n\n"
        "=== END OF MATERIAL. Below, the same material repeats only to test reading length; "
        "do not review the repeats. ===\n"
    )
    i = 1
    while len(prompt.encode()) < 24576:  # repeats, not filler: identical filler made the model error out
        prompt += f"\n--- repeat {i} ---\n{packet_text}"
        i += 1
    prompt += f"\nCANARY-B: {b}\n"
    with tempfile.TemporaryDirectory() as td:
        # named files with extensions: Shortcuts reads the input's type from its extension
        src, out = os.path.join(td, "prompt.txt"), os.path.join(td, "answer.txt")
        open(src, "w", encoding="utf-8").write(prompt)
        try:
            subprocess.run(
                ["shortcuts", "run", shortcut, "--input-path", src, "--output-path", out,
                 "--output-type", "public.plain-text"],
                capture_output=True, timeout=180,
            )
        except subprocess.TimeoutExpired:
            return "failed", "the Shortcut did not answer within 180 s"
        try:
            text = open(out, encoding="utf-8").read()
        except OSError:
            return "failed", "the Shortcut returned nothing"
    if f"CANARY-A: {a}" not in text or f"CANARY-B: {b}" not in text:
        return "canary-missing", "the answer did not repeat both codes, so it may come from the small on-device model; not counted"
    text = "\n".join(l for l in text.splitlines() if "CANARY-" not in l).strip()
    return ("answered" if substantive(text) else "thin-answer"), text


def command_lanes():
    lanes = []
    for line in conf("reviewers.txt").splitlines():
        if "|" in line and not line.strip().startswith("#"):
            name, cmd = line.split("|", 1)
            if name.strip() and cmd.strip():
                lanes.append((name.strip(), cmd.strip()))
    return lanes


def desk_module():
    try:
        spec = importlib.util.spec_from_file_location("desk", os.path.join(os.path.dirname(os.path.abspath(__file__)), "desk.py"))
        desk = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(desk)
        return desk
    except (Exception, SystemExit):
        return None


def folder_settings():
    """(settings of the folder this runs in, the working copy to run its hooks in), or ({}, cwd)."""
    desk = desk_module()
    if desk is None:
        return {}, os.getcwd()
    try:
        root, _ = desk.main_root()
        return desk.settings(root), desk.house_work()
    except (Exception, SystemExit):
        return {}, os.getcwd()


def pattern(cfg, key, default, stem):
    return (cfg.get(key, "").strip() or default).replace("{stem}", stem)


def table_rows(text):
    """The body rows of every markdown table in `text`: [list of cells]. A header is the row above a separator."""
    lines, rows = text.splitlines(), []
    sep = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
    for n, l in enumerate(lines):
        if not l.strip().startswith("|") or sep.match(l):
            continue
        if n + 1 < len(lines) and sep.match(lines[n + 1]) and "-" in lines[n + 1]:
            continue  # the header row
        rows.append([c.strip() for c in l.strip().strip("|").split("|")])
    return rows


# A finding is closed by a recognised status word, then anything: `Accepted, fixed in abc123`, `Rejected: out of scope`.
# The words SKILL.md and reference/review.md tell the agent to write, plus older ones still in use (#96).
DISPOSITION_WORDS = ("adopted", "accepted", "rejected", "partly", "left", "noted")
DISPOSITION = re.compile(r"(" + "|".join(DISPOSITION_WORDS) + r")\b", re.I)


def open_rows(path):
    """The rows of a dispositions file that do not end in a real disposition; None when it has no rows."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    rows = table_rows(text)
    if not rows:
        return None
    return [r for r in rows if not (r and DISPOSITION.match(r[-1].lstrip("*_` ")) and "{{" not in r[-1])]


def dispositions_closed(path):
    """True when the file has finding rows and every row ends in a real disposition."""
    return open_rows(path) == []


def index_file():
    return os.path.join(CONF, "receipts.tsv")


def find_receipt(rid, roots=()):
    """The receipt file named by the index kept in the config folder (so it works from any folder). There is
    no search of the tree: a file someone wrote into the project is not a receipt. `roots` is accepted and ignored."""
    if not re.fullmatch(r"[0-9a-f]{10}", rid or ""):
        return None
    try:
        with open(index_file(), encoding="utf-8") as fh:
            index = fh.read().splitlines()
    except OSError:
        return None
    for line in reversed(index):
        r, _, path = line.partition("\t")
        if r == rid and os.path.isfile(path):
            return path
    return None


def packet_hash(path):
    """The hash recorded in a receipt: of the packet's text as it was read (utf-8)."""
    with open(path, encoding="utf-8") as fh:
        return hashlib.sha256(fh.read().encode()).hexdigest()


def receipt_state(rid, roots=(".",)):
    """What a receipt proves now: its label at run time, its label today, and why. None when it does not exist."""
    path = find_receipt(rid, roots)
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    f = dict(l.split(" ", 1) for l in text.splitlines() if " " in l)
    label, packet = f.get("label", ""), f.get("packet", "")
    disp = f.get("dispositions", "")
    now, why = label, ""
    here = os.path.dirname(os.path.realpath(path))
    pdir = os.path.dirname(os.path.realpath(packet)) if packet else ""
    if f.get("receipt") != rid or not pdir or here == pdir or os.path.commonpath([pdir, here]) != pdir:
        now, why = "unverified", "the receipt does not sit in the review folder of its own packet"
    elif not os.path.isfile(packet):
        now, why = "stale", "the packet is missing, so nothing says what this receipt covered"
    elif f.get("packet_sha256") != packet_hash(packet):
        now, why = "stale", "the packet changed after the review ran, so this receipt does not cover it"
    elif label == "open":
        if disp and dispositions_closed(disp):
            now = "converged"
        else:
            now, why = "open", f"give every finding a disposition in {disp or 'the dispositions file'}"
            bad = open_rows(disp) if disp else None
            if bad:  # #96: say which row and which words count, so nobody has to guess
                why += (f": {len(bad)} row(s) do not end in one of {', '.join(DISPOSITION_WORDS)}, "
                        f"first: | {' | '.join(bad[0])[:120]} |")
    return {"path": path, "text": text, "fields": f, "label": label, "now": now, "why": why, "dispositions": disp}


def verify(receipt, root):
    st = receipt_state(receipt, [root, os.getcwd()])
    if not st:
        print(f"NO RECEIPT {receipt}: the label it backs is unverified", file=sys.stderr)
        return 1
    print(st["text"], end="" if st["text"].endswith("\n") else "\n")
    if st["fields"].get("label") == "open":
        has = os.path.isfile(st["dispositions"])
        print(f"dispositions {'present' if has else 'missing'}: {st['dispositions']}")
    print(f"label now: {st['now']}" + (f" ({st['why']})" if st["why"] else ""))
    return 1 if st["now"] in ("stale", "unverified") else 0


def key_status(key):
    """What OpenRouter says about the key, without spending anything. Never prints the key."""
    try:
        d = http(API + "/key", key=key, timeout=15).get("data") or {}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, f"set, but OpenRouter refused it (HTTP {e.code}): make a new key, `desk setup`"
        return None, f"set (not checked: HTTP {e.code})"
    except Exception as e:
        return None, f"set (not checked: {explain(e)})"
    how = "added by the environment" if key == PROXY else "set"
    if d.get("is_free_tier"):
        return True, f"{how} and working · no credit bought: 50 free requests a day (about eight reviews)"
    return True, f"{how} and working · credit bought once: 1000 free requests a day"


def check(live=False):
    """What is set up. Offline unless `live`: then each provider is asked whether its key works."""
    key, lanes, apple = api_key(probe=live), command_lanes(), conf("apple-shortcut")
    direct = direct_lanes()
    ok_key, ready = True, direct
    if not key and cloud() and not live:
        print("review key:      none here; in a cloud session the environment may add it (`--test` asks)")
    elif not key:
        print("review key:      not set  ->  run `desk setup`")
    elif live:
        ok_key, said = key_status(key)
        print("review key:      " + said)
    else:
        print("review key:      set  (`--test` asks OpenRouter whether it works)")
    if live and direct:
        ready, broken = resolve_lanes(direct)
        print("providers:       " + (", ".join(f"{l['name']} ({l['model']}{', on this machine' if l['local'] else ''})"
                                               for l in ready) or "none working"))
        for name, why in broken:
            print(f"  not working:   {name}: {why}")
    else:
        print("providers:       " + (", ".join(l["name"] + (" (on this machine)" if l["local"] else "") for l in direct) or "none"))
    print("your own lanes:  " + (", ".join(n for n, _ in lanes) or "none"))
    print("private lane:    " + (f'Shortcut "{apple}"' if apple else "none"))
    print("private terms:   " + (f"{len(conf('private-terms.txt').splitlines())} lines" if conf("private-terms.txt") else "none"))
    cross = (key and ok_key is not False) or lanes or ready
    print("mode:            " + ("cross-vendor" if cross else "same-vendor"))
    return 0 if (key or lanes or apple or direct) else 3


def house_review():
    """The folder's own review procedure, when its Desk block says `Review: house follow|run <x>` (#28)."""
    desk = desk_module()
    if desk is None:
        return None  # cannot tell: the caller fails closed, never as if there were no house review
    try:
        root, _ = desk.main_root()
        mode, arg = desk.open_mode(desk.settings(root), "review")
    except (Exception, SystemExit):
        return None
    return arg if mode in ("follow", "run") else ""


def run_gate(cmd, text, tier, cwd):
    """(True, '') when the folder's gate lets this text out for this tier. Anything but a clean pass refuses."""
    with tempfile.TemporaryDirectory() as td:
        f = os.path.join(td, "screen.md")
        open(f, "w", encoding="utf-8").write(text)
        try:
            p = subprocess.run(f"{cmd} {shlex.quote(f)} {tier}", shell=True, cwd=cwd, capture_output=True, text=True,
                               timeout=120, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, f"the gate could not run ({type(e).__name__})"
    out = (p.stdout or "").strip()
    first = out.splitlines()[0].strip() if out else ""
    if p.returncode != 0 or first not in ("OK", "PASS"):  # only an explicit pass passes: silence, noise and errors refuse
        why = first or (p.stderr or "").strip().splitlines()[-1:] or [f"exit {p.returncode}"]
        return False, why if isinstance(why, str) else why[0]
    return True, ""


def ask_private_command(cmd, packet, focus, cwd):
    """The folder's private lane: `<command> <packet>`, the answer on stdout, exit 3 for a packet too large."""
    size = os.path.getsize(packet)
    try:
        p = subprocess.run(f"{cmd} {shlex.quote(packet)}", shell=True, cwd=cwd, capture_output=True, text=True, timeout=400,
                           stdin=subprocess.DEVNULL, env=dict(os.environ, DESK_FOCUS=focus))
    except subprocess.TimeoutExpired:
        return "failed", "no answer within 400 s"
    text = (p.stdout or "").strip()
    if p.returncode == 3:
        return "too-large", f"the lane refused the packet as too large ({size // 1024} KB); shorten it or split it"
    if "canary missing" in ((p.stdout or "") + (p.stderr or "")):
        return "canary-missing", "the lane's answer did not repeat both codes, so it may come from a small on-device model; not counted"
    if p.returncode != 0 or not text:
        return "failed", ((p.stderr or "empty answer")[:300] + (f" (the packet is {size // 1024} KB; some lanes fail above 15 KB)" if size > 15000 else ""))
    return ("answered" if substantive(text) else "thin-answer"), text


def watchdog(seconds, log_dir):
    def stop():
        msg = f"WATCHDOG: the review did not finish within {seconds} s and was stopped. The reply is [unreviewed]."
        try:
            open(os.path.join(log_dir, "run.log"), "a", encoding="utf-8").write(msg + "\n")
        except OSError:
            pass
        print(msg, file=sys.stderr, flush=True)
        os._exit(7)
    t = threading.Timer(seconds, stop)
    t.daemon = True
    t.start()


def status(packet):
    cfg, _ = folder_settings()
    stem = os.path.splitext(os.path.basename(packet))[0]
    out = os.path.join(os.path.dirname(packet) or ".", pattern(cfg, "reviews", "{stem}-reviews", stem))
    log = os.path.join(out, "run.log")
    if not os.path.isfile(log):
        print(f"no background run for {packet} (looked for {log})", file=sys.stderr)
        return 1
    text = open(log, encoding="utf-8").read().splitlines()
    print("\n".join(text[-25:]))
    return 0


def main(argv):
    alongside = "--alongside" in argv  # started by the folder's own review routine, as its second opinion
    argv = [a for a in argv if a != "--alongside"]
    if len(argv) >= 2 and argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if len(argv) >= 2 and argv[1] in ("--check", "--test"):
        return check(live=argv[1] == "--test")
    if len(argv) >= 3 and argv[1] == "--verify":
        return verify(argv[2], argv[3] if len(argv) > 3 else ".")
    if len(argv) >= 3 and argv[1] == "--status":
        return status(argv[2])
    background = "--background" in argv
    argv = [a for a in argv if a != "--background"]
    wd = 0
    if "--watchdog" in argv:
        i = argv.index("--watchdog")
        wd = int(argv[i + 1])
        del argv[i:i + 2]
    if len(argv) >= 2 and not argv[1].startswith("-") and not os.path.isfile(argv[1]):
        print(f"packet not found: {os.path.abspath(argv[1])}\n(run from the folder the session was opened on, or give the full path)", file=sys.stderr)
        return 2
    if len(argv) < 2 or argv[1].startswith("-"):
        print(__doc__.split("Setup lives")[0].strip(), file=sys.stderr)
        return 2
    house = house_review()
    if house is None and not alongside:
        print("NOT SENT: could not read this folder's Desk block to check for `Review: house`. "
              "Check that desk.py sits next to this script.", file=sys.stderr)
        return 5
    if house and not alongside:
        print(f"NOT SENT: this folder reviews its own way: {house}. This script runs only as the second "
              "opinion that routine starts (`--alongside`).", file=sys.stderr)
        return 5
    packet = argv[1]
    focus = argv[2] if len(argv) > 2 else "Adversarial review: what would the author miss or agree with too easily?"
    text = open(packet, encoding="utf-8").read()
    stem = os.path.splitext(os.path.basename(packet))[0]
    cfg, cwd = folder_settings()
    out = os.path.join(os.path.dirname(packet) or ".", pattern(cfg, "reviews", "{stem}-reviews", stem))
    dispositions = os.path.abspath(os.path.join(os.path.dirname(packet) or ".", pattern(cfg, "dispositions", "{stem}-dispositions.md", stem)))
    if background:
        os.makedirs(out, exist_ok=True)
        log = os.path.join(out, "run.log")
        secs = int(os.environ.get("DESK_REVIEW_WATCHDOG", "1500"))
        cmd = [sys.executable, os.path.abspath(__file__), *([a for a in argv[1:]]), "--watchdog", str(secs)]
        with open(log, "w", encoding="utf-8") as lf:
            subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True, cwd=os.getcwd())
        print(f"Started in the background (stopped by a watchdog after {secs} s). Log: {log}\n"
              f"Read it with: python3 {os.path.abspath(__file__)} --status {packet}")
        return 0
    if wd:
        os.makedirs(out, exist_ok=True)
        watchdog(wd, out)

    key, lanes, apple = api_key(probe=True), command_lanes(), conf("apple-shortcut")
    direct = direct_lanes()
    gate, plane = cfg.get("gate", "").strip(), cfg.get("private lane", "").strip()
    screened = text + "\n" + focus
    if gate:  # the folder's gate is the one authority: no second marker list here
        public_ok, why_pub = run_gate(gate, screened, "public", cwd)
        private_ok, why_priv = (run_gate(gate, screened, "private", cwd) if plane else (False, "no private lane is set up"))
        hits = [] if public_ok else [f"the folder's gate refused it ({why_pub})"]
    else:
        hits = private_hits(screened)
        public_ok, private_ok, why_priv = not hits, True, ""
    if hits:
        # a model on this machine sends nothing anywhere: it may take what the private tier may take
        direct = [l for l in direct if l["local"]] if (private_ok if gate else True) else []
    private_job = bool((plane and private_ok) or (apple and (not gate or private_ok)) or (hits and direct))  # what would really run below
    if hits:
        print("NOT SENT to outside vendors. The packet contains: " + "; ".join(sorted(set(hits))), file=sys.stderr)
        if not private_job:
            print(("The private lane will not take it either: " + why_priv + ". " if gate and why_priv else "") +
                  "Remove it and run again, or review with a subagent and label the reply [same-vendor].", file=sys.stderr)
            return 1
        print("Asking only the lanes that keep it on this machine.", file=sys.stderr)
    if public_ok and not gate and not conf("private-terms.txt"):
        print("note: no private-terms list, so names are not checked. Ask the user for them (reference/setup.md, Private terms).", file=sys.stderr)
    if not (key or lanes or apple or plane or direct):
        print("No review key and no other lane. Label the reply [same-vendor] after a subagent pass, or run `desk setup`.", file=sys.stderr)
        return 3

    os.makedirs(out, exist_ok=True)
    ledger = os.path.join(out, "ledger.tsv")
    if not os.path.exists(ledger):
        open(ledger, "w", encoding="utf-8").write("date\tpacket\tmodel\tfamily\tstatus\tseconds\n")
    today = datetime.date.today().isoformat()
    results = []  # (family, model, status, seconds)

    def record(family, model, fn, file=None):
        t0 = time.time()
        status, body = fn()
        secs = int(time.time() - t0)
        with open(os.path.join(out, (file or family) + ".txt"), "w", encoding="utf-8") as f:
            f.write(f"packet: {packet}\nmodel:  {model}\nstatus: {status}\n\n{body}\n")
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(f"{today}\t{stem}\t{model}\t{family}\t{status}\t{secs}\n")
        results.append((family, model, status, secs))
        return status

    n = int(os.environ.get("DESK_REVIEW_N", "6"))
    want = int(os.environ.get("DESK_REVIEW_MIN", "3"))
    ready, broken = resolve_lanes(direct) if direct else ([], [])
    for name, why in broken:
        print(f"Not asking {name}: {why}", file=sys.stderr)
    asked = {l["vendor"] for l in ready}
    models = []
    if public_ok and key:
        try:
            # families a direct provider already covers go last: asked again only if that lane fails
            models = sorted(pick_models(out), key=lambda m: vendor_of(m) in asked)
        except Exception as e:
            print(f"Could not read the model list ({e}).", file=sys.stderr)
    jobs = []
    if public_ok:
        jobs += [(name, "your lane: " + name, (lambda c=cmd: ask_command(c, text, focus))) for name, cmd in lanes]
    jobs += [(l["vendor"], f"{l['name']}: {l['model']}", (lambda l=l: ask_direct(l, text, focus)),
              f"{l['vendor']}-{l['name']}") for l in ready]
    first = [m for m in models if vendor_of(m) not in asked][:max(n - len(jobs), 0)]
    jobs += [(vendor_of(m), m, (lambda m=m: ask_openrouter(m, text, focus, key))) for m in first]
    if plane and private_ok:
        jobs.append(("apple", f"private lane: {plane}", lambda: ask_private_command(plane, packet, focus, cwd)))
    elif apple and (not gate or private_ok):
        jobs.append(("apple", f'Shortcut "{apple}"', lambda: ask_apple(apple, text, focus)))
    if jobs:
        print(f"Asking {len(jobs)} reviewers (a few minutes, no cost)...", flush=True)
    with cf.ThreadPoolExecutor(max_workers=max(len(jobs), 1)) as ex:
        list(ex.map(lambda j: record(*j), jobs))

    def answered():
        return sorted({v for v, _, s, _ in results if s == "answered" and v != "apple"})

    # Top up: free models fail often. A family that failed is replaced from the live free list: keep
    # asking other families, one at a time, until enough have answered or the list runs out.
    topped = []
    capped = any(s == "account-cap" for _, _, s, _ in results)
    dead_key = lambda: any(s == "key-refused" and m.endswith(":free") for _, m, s, _ in results)
    for m in models:
        if len(answered()) >= want or capped or dead_key():
            break
        v = vendor_of(m)
        if m in first or v in answered():
            continue
        if record(v, m, lambda m=m: ask_openrouter(m, text, focus, key), v if v not in asked else v + "-openrouter") == "account-cap":
            capped = True
        topped.append(v)

    print()
    for v, m, s, secs in results:
        print(f"  {m:<48} {s} ({secs}s)")
    print(f"\nAnswers: {out}")
    if topped:
        print("Topped up with: " + " ".join(topped))
    refused = sorted({m.split(": ")[0] if ": " in m else "openrouter" for _, m, s, _ in results if s == "key-refused"})
    if refused:
        print("KEY REFUSED by: " + ", ".join(refused) + ". Run `review.py --test` and make a new key there.")
    if capped:
        print("ACCOUNT CAP: OpenRouter refused on the daily limit for free models. Another model will not help.\n"
              "  It is 50 requests a day, or 1000 a day once the account has bought 10 USD of credit\n"
              "  (the credit is not spent by free models). Otherwise wait for the daily reset.")
    families = answered()
    private_ok_answer = any(v == "apple" and s == "answered" for v, _, s, _ in results)
    sha = hashlib.sha256(text.encode()).hexdigest()
    rid = hashlib.sha256(f"{sha}{time.time()}{len(families)}".encode()).hexdigest()[:10]
    if families:
        label = "open" if len(families) >= want else "thin"
    else:
        label = "private-lane-only" if private_ok_answer else "unreviewed"
    receipt = os.path.abspath(os.path.join(out, f"receipt-{rid}.txt"))
    with open(receipt, "w", encoding="utf-8") as f:
        f.write(f"receipt {rid}\ndate {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\npacket {os.path.abspath(packet)}\n"
                f"packet_sha256 {sha}\nlabel {label}\nfamilies_answered {len(families)}\n"
                f"families {' '.join(families)}\ndispositions {dispositions}\n"
                f"private_lane {'answered' if private_ok_answer else 'no'}\n")
    try:
        os.makedirs(CONF, exist_ok=True)
        with open(index_file(), "a", encoding="utf-8") as f:
            f.write(f"{rid}\t{receipt}\n")
    except OSError:
        pass  # the index is a convenience; the receipt next to the answers is the record
    plus = " + private lane" if private_ok_answer and families else ""
    print()
    if label == "unreviewed":
        print(f"Label line: Review: [unreviewed] · receipt {rid}   (nobody answered)")
        return 4
    if label == "private-lane-only":
        print(f"Label line: Review: [thin] · private lane only · receipt {rid}")
        return 6
    if label == "thin":
        print(f"Label line: Review: [thin] · {len(families)} {'family' if len(families) == 1 else 'families'}{plus} · receipt {rid}")
        return 6
    print(f"Label line: Review: [converged] · {len(families)} families{plus} · receipt {rid}\n"
          f"  Earn it first: give every finding a disposition in {os.path.basename(dispositions)}, next to the packet.\n"
          f"  Until every row has one the review is still open (`review.py --verify {rid}` says which).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
