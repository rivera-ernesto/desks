#!/usr/bin/env python3
"""Send one review packet to several AI models from other vendors and print a label.

    python3 review.py <packet.md> ["what to look for"]  [--background]
    python3 review.py --verify <receipt>  [folder to search]
    python3 review.py --status <packet.md>      (the tail of a background run)
    python3 review.py --check                   (is a review key set up? which lanes?)

It asks free models only, one per family, through OpenRouter, in parallel. It
writes each answer next to the packet, in <packet>-reviews/, with a ledger and
a receipt. Standard library only: nothing to install.

Setup lives outside any project, so a key is never committed by accident:
    ~/.config/desk/openrouter.key   the key, one line (or env OPENROUTER_API_KEY)
    ~/.config/desk/private-terms.txt  words that must never leave this machine
    ~/.config/desk/reviewers.txt    extra lanes: name | command reading stdin
    ~/.config/desk/apple-shortcut   name of a macOS Shortcut (private lane)

A folder with its own rules says so in the Desk block (`desk.py set`):
    Gate: <command>          run as `<command> <file> public|private`; exit 0 and a first line that does
                             not start with REFUSE lets that tier go, anything else refuses (fails closed).
                             When there is a gate, the built-in scan and the private-terms list stand down.
    Private lane: <command>  run as `<command> <packet>`, answer on stdout; exit 3 means "packet too large"
    Reviews: <name>          the answers folder, `{stem}` is the packet's name (default `{stem}-reviews`)
    Dispositions: <name>     the file that closes a review (default `{stem}-dispositions.md`)

Environment: DESK_REVIEW_N families to ask at once (6) - DESK_REVIEW_MIN answers
wanted (3) - DESK_REVIEW_MODELS comma list instead of the live catalogue -
DESK_REVIEW_WATCHDOG seconds before a background run is stopped (1500).

Exit codes: 0 enough families answered (the label is open until every finding has a disposition)
            1 packet refused by the gate or the built-in scan - 2 usage - 3 no key and no other lane
            4 nobody answered - 6 fewer families answered than wanted, or only the private lane
            7 a background run was stopped by its watchdog
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


def api_key():
    return os.environ.get("OPENROUTER_API_KEY", "").strip() or conf("openrouter.key")


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
    headers = {"Content-Type": "application/json", "X-Title": "Desk review"}
    if key:
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
        vendor = i.split("/")[0]
        ctx = m.get("context_length") or 0
        # the largest context per vendor is a rough stand-in for its stronger model
        if vendor not in best or ctx > best[vendor][1]:
            best[vendor] = (i, ctx)
    ids = sorted(v[0] for v in best.values())
    if not ids:
        return []
    k = datetime.date.today().toordinal() % len(ids)  # rotate, so no vendor always goes first
    ids = ids[k:] + ids[:k]
    calls, ok = past_rates(folder)

    def band(i):
        v = i.split("/")[0]
        n = calls.get(v, 0)
        if n < 5:
            return 1  # unknown
        return 0 if ok.get(v, 0) * 2 >= n else 2  # proven first, weak last, never dropped

    return sorted(ids, key=band)


def ask_openrouter(model, packet_text, focus, key):
    if not model.endswith(":free"):
        return "refused", f"'{model}' is not a free model; this script only asks free models"
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
            r = http(API + "/chat/completions", body, key)
            if "error" in r:
                last = json.dumps(r["error"])[:400]
            else:
                msg = r["choices"][0]["message"]
                text = (msg.get("content") or "").strip()
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


def dispositions_closed(path):
    """True when the file has finding rows and every row ends in a real disposition."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    rows = table_rows(text)
    if not rows:
        return False
    return all(r and r[-1] and r[-1].lower() not in ("todo", "tbd", "?", "open", "pending") and "{{" not in r[-1] for r in rows)


def index_file():
    return os.path.join(CONF, "receipts.tsv")


def find_receipt(rid, roots):
    """The receipt file, from the index kept in the config folder (so it works from any folder), else a search of `roots`."""
    try:
        with open(index_file(), encoding="utf-8") as fh:
            index = fh.read().splitlines()
        for line in index:
            r, _, path = line.partition("\t")
            if r == rid and os.path.isfile(path):
                return path
    except OSError:
        pass
    for root in roots:
        for d, dirs, files in os.walk(root or "."):
            dirs[:] = [x for x in dirs if x not in (".git", "node_modules")]
            if f"receipt-{rid}.txt" in files:
                return os.path.join(d, f"receipt-{rid}.txt")
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
    if packet and os.path.isfile(packet) and f.get("packet_sha256") != packet_hash(packet):
        now, why = "stale", "the packet changed after the review ran, so this receipt does not cover it"
    elif label == "open":
        if disp and dispositions_closed(disp):
            now = "converged"
        else:
            now, why = "open", f"give every finding a disposition in {disp or 'the dispositions file'}"
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
    return 0


def check():
    key, lanes, apple = api_key(), command_lanes(), conf("apple-shortcut")
    print("review key:      " + ("set" if key else "not set  ->  run `desk setup`"))
    print("your own lanes:  " + (", ".join(n for n, _ in lanes) or "none"))
    print("private lane:    " + (f'Shortcut "{apple}"' if apple else "none"))
    print("private terms:   " + (f"{len(conf('private-terms.txt').splitlines())} lines" if conf("private-terms.txt") else "none"))
    print("mode:            " + ("cross-vendor" if (key or lanes) else "same-vendor"))
    return 0 if (key or lanes or apple) else 3


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
    first = out.splitlines()[0] if out else ""
    if p.returncode != 0 or first.upper().startswith("REFUSE"):
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
    if len(argv) >= 2 and argv[1] == "--check":
        return check()
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

    key, lanes, apple = api_key(), command_lanes(), conf("apple-shortcut")
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
        print("NOT SENT to outside vendors. The packet contains: " + "; ".join(sorted(set(hits))), file=sys.stderr)
        if not (apple or (plane and private_ok)):
            print(("The private lane refused it too: " + why_priv + ". " if gate and plane else "") +
                  "Remove it and run again, or review with a subagent and label the reply [same-vendor].", file=sys.stderr)
            return 1
        print("Asking the private lane only.", file=sys.stderr)
    if public_ok and not gate and not conf("private-terms.txt"):
        print("note: no private-terms list, so names are not checked. Ask the user for them (reference/setup.md, Private terms).", file=sys.stderr)
    if not (key or lanes or apple or plane):
        print("No review key and no other lane. Label the reply [same-vendor] after a subagent pass, or run `desk setup`.", file=sys.stderr)
        return 3

    os.makedirs(out, exist_ok=True)
    ledger = os.path.join(out, "ledger.tsv")
    if not os.path.exists(ledger):
        open(ledger, "w", encoding="utf-8").write("date\tpacket\tmodel\tfamily\tstatus\tseconds\n")
    today = datetime.date.today().isoformat()
    results = []  # (family, model, status, seconds)

    def record(family, model, fn):
        t0 = time.time()
        status, body = fn()
        secs = int(time.time() - t0)
        with open(os.path.join(out, family + ".txt"), "w", encoding="utf-8") as f:
            f.write(f"packet: {packet}\nmodel:  {model}\nstatus: {status}\n\n{body}\n")
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(f"{today}\t{stem}\t{model}\t{family}\t{status}\t{secs}\n")
        results.append((family, model, status, secs))
        return status

    n = int(os.environ.get("DESK_REVIEW_N", "6"))
    want = int(os.environ.get("DESK_REVIEW_MIN", "3"))
    models = []
    if public_ok and key:
        try:
            models = pick_models(out)
        except Exception as e:
            print(f"Could not read the model list ({e}).", file=sys.stderr)
    jobs = []
    if public_ok:
        jobs += [(name, "your lane: " + name, (lambda c=cmd: ask_command(c, text, focus))) for name, cmd in lanes]
        jobs += [(m.split("/")[0], m, (lambda m=m: ask_openrouter(m, text, focus, key))) for m in models[:n]]
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
    for m in models[n:]:
        if len(answered()) >= want or capped:
            break
        if record(m.split("/")[0], m, lambda m=m: ask_openrouter(m, text, focus, key)) == "account-cap":
            capped = True
        topped.append(m.split("/")[0])

    print()
    for v, m, s, secs in results:
        print(f"  {m:<48} {s} ({secs}s)")
    print(f"\nAnswers: {out}")
    if topped:
        print("Topped up with: " + " ".join(topped))
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
