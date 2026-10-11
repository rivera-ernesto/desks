#!/usr/bin/env python3
"""Send one review packet to several AI models from other vendors and print a label.

    python3 review.py <packet.md> ["what to look for"]
    python3 review.py --verify <receipt>  [folder to search, default: .]
    python3 review.py --check             (is a review key set up? which lanes?)

It asks free models only, one per vendor, through OpenRouter, in parallel. It
writes each answer next to the packet, in <packet>-reviews/, with a ledger and
a receipt. Standard library only: nothing to install.

Setup lives outside any project, so a key is never committed by accident:
    ~/.config/desk/openrouter.key   the key, one line (or env OPENROUTER_API_KEY)
    ~/.config/desk/private-terms.txt  words that must never leave this machine
    ~/.config/desk/reviewers.txt    extra lanes: name | command reading stdin
    ~/.config/desk/apple-shortcut   name of a macOS Shortcut (private lane)

Environment: DESK_REVIEW_N vendors to ask at once (6) · DESK_REVIEW_MIN answers
wanted (3) · DESK_REVIEW_MODELS comma list instead of the live catalogue.

Exit codes: 0 at least one vendor answered · 1 packet refused · 2 usage
            3 no key and no other lane · 4 nobody answered
"""
import concurrent.futures as cf
import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

API = "https://openrouter.ai/api/v1"
CONF = os.path.join(os.path.expanduser("~"), ".config", "desk")
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
    low = text.lower()
    for line in conf("private-terms.txt").splitlines():
        term = line.strip()
        if term and not term.startswith("#") and term.lower() in low:
            hits.append(f'your private term "{term}"')
    for pattern, what in BUILTIN_PRIVATE:
        if re.search(pattern, text):
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
                rows = open(os.path.join(d, "ledger.tsv"), encoding="utf-8").read().splitlines()
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
                text = (r["choices"][0]["message"].get("content") or "").strip()
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


def substantive(text):
    t = re.sub(r"<\|tool_call_start\|>.*?<\|tool_call_end\|>", "", text, flags=re.S)
    t = re.sub(r"<(tool_call|function_call|tool_use)>.*?</\1>", "", t, flags=re.S)
    return len(re.sub(r"\s", "", t)) >= MIN_CHARS


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


def verify(receipt, root):
    for d, _, files in os.walk(root):
        if f"receipt-{receipt}.txt" in files:
            print(open(os.path.join(d, f"receipt-{receipt}.txt"), encoding="utf-8").read())
            return 0
    print(f"NO RECEIPT {receipt}: the label it backs is unverified", file=sys.stderr)
    return 1


def check():
    key, lanes, apple = api_key(), command_lanes(), conf("apple-shortcut")
    print("review key:      " + ("set" if key else "not set  ->  run `desk setup`"))
    print("your own lanes:  " + (", ".join(n for n, _ in lanes) or "none"))
    print("private lane:    " + (f'Shortcut "{apple}"' if apple else "none"))
    print("private terms:   " + (f"{len(conf('private-terms.txt').splitlines())} lines" if conf("private-terms.txt") else "none"))
    print("mode:            " + ("cross-vendor" if (key or lanes) else "same-vendor"))
    return 0 if (key or lanes or apple) else 3


def main(argv):
    if len(argv) >= 2 and argv[1] == "--check":
        return check()
    if len(argv) >= 3 and argv[1] == "--verify":
        return verify(argv[2], argv[3] if len(argv) > 3 else ".")
    if len(argv) >= 2 and not argv[1].startswith("-") and not os.path.isfile(argv[1]):
        print(f"packet not found: {os.path.abspath(argv[1])}\n(run from the folder the session was opened on, or give the full path)", file=sys.stderr)
        return 2
    if len(argv) < 2 or argv[1].startswith("-"):
        print(__doc__.split("Setup lives")[0].strip(), file=sys.stderr)
        return 2
    packet = argv[1]
    focus = argv[2] if len(argv) > 2 else "Adversarial review: what would the author miss or agree with too easily?"
    text = open(packet, encoding="utf-8").read()
    stem = os.path.splitext(os.path.basename(packet))[0]
    out = os.path.join(os.path.dirname(packet) or ".", stem + "-reviews")

    key, lanes, apple = api_key(), command_lanes(), conf("apple-shortcut")
    hits = private_hits(text + "\n" + focus)
    public_ok = not hits
    if hits:
        print("NOT SENT to outside vendors. The packet contains: " + "; ".join(sorted(set(hits))), file=sys.stderr)
        if not apple:
            print("Remove it and run again, or review with a subagent and label the reply [same-vendor].", file=sys.stderr)
            return 1
        print("Asking the private lane only.", file=sys.stderr)
    if not (key or lanes or apple):
        print("No review key and no other lane. Label the reply [same-vendor] after a subagent pass, or run `desk setup`.", file=sys.stderr)
        return 3

    os.makedirs(out, exist_ok=True)
    ledger = os.path.join(out, "ledger.tsv")
    if not os.path.exists(ledger):
        open(ledger, "w", encoding="utf-8").write("date\tpacket\tmodel\tvendor\tstatus\tseconds\n")
    today = datetime.date.today().isoformat()
    results = []  # (vendor, model, status, seconds)

    def record(vendor, model, fn):
        t0 = time.time()
        status, body = fn()
        secs = int(time.time() - t0)
        with open(os.path.join(out, vendor + ".txt"), "w", encoding="utf-8") as f:
            f.write(f"packet: {packet}\nmodel:  {model}\nstatus: {status}\n\n{body}\n")
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(f"{today}\t{stem}\t{model}\t{vendor}\t{status}\t{secs}\n")
        results.append((vendor, model, status, secs))
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
    if apple:
        jobs.append(("apple", f'Shortcut "{apple}"', lambda: ask_apple(apple, text, focus)))
    if jobs:
        print(f"Asking {len(jobs)} reviewers (a few minutes, no cost)...", flush=True)
    with cf.ThreadPoolExecutor(max_workers=max(len(jobs), 1)) as ex:
        list(ex.map(lambda j: record(*j), jobs))

    def answered():
        return sorted({v for v, _, s, _ in results if s == "answered" and v != "apple"})

    # Top up: free models fail often. Keep asking other vendors, one at a time,
    # until enough have answered or the list runs out.
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
    vendors = answered()
    apple_ok = any(v == "apple" and s == "answered" for v, _, s, _ in results)
    sha = hashlib.sha256(text.encode()).hexdigest()
    rid = hashlib.sha256(f"{sha}{time.time()}{len(vendors)}".encode()).hexdigest()[:10]
    if vendors:
        label = "thin" if len(vendors) == 1 else "open"
    else:
        label = "private-lane-only" if apple_ok else "unreviewed"
    with open(os.path.join(out, f"receipt-{rid}.txt"), "w", encoding="utf-8") as f:
        f.write(f"receipt {rid}\ndate {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\npacket {packet}\n"
                f"packet_sha256 {sha}\nlabel {label}\nvendors_answered {len(vendors)}\n"
                f"vendors {' '.join(vendors)}\nprivate_lane {'answered, both codes repeated' if apple_ok else 'no'}\n")
    plus = " + private lane" if apple_ok and vendors else ""
    print()
    if label == "unreviewed":
        print(f"Label line: Review: [unreviewed] · receipt {rid}   (nobody answered)")
        return 4
    if label == "private-lane-only":
        print(f"Label line: Review: [thin] · private lane only · receipt {rid}")
    elif label == "thin":
        print(f"Label line: Review: [thin] · 1 vendor{plus} · receipt {rid}")
    else:
        print(f"Label line: Review: [converged] · {len(vendors)} vendors{plus} · receipt {rid}\n"
              f"  Earn it first: give every finding a disposition in {stem}-dispositions.md, next to the packet.\n"
              "  Until that file exists the review is still open.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
