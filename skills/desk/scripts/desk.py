#!/usr/bin/env python3
"""The plumbing under a Desk, so the session never improvises git.

    python3 desk.py status
    python3 desk.py open  <topic> [--parent <topic>] [--reopen]
    python3 desk.py close [<topic>] --merge | --pr [--title "Five Words At Most"]
    python3 desk.py close [<topic>]            (the recorded `Close:` line decides; the topic is found from the working copy)
    python3 desk.py receive [<topic>]          (no topic: lists what is ready; else takes the topic in, all or nothing)
    python3 desk.py digest [--fetch] [--freeze <file> --next "..."] [--compare <file>]
    python3 desk.py children [<topic>]
    python3 desk.py migrate <topic>            (copies state left outside versioned history into the working copy)
    python3 desk.py note  <open-topic> <other-topic> "what came up, in a sentence or two"
    python3 desk.py set   "Close" "merge"      (records a setup answer in CLAUDE.md)
    python3 desk.py get   "Close"              (prints a recorded answer; exit 1 if none)
    python3 desk.py add   "Setup" "use my researcher agent for reading"   (adds a line, keeps earlier ones)
    python3 desk.py scan                       (the folder's own open, review and close routines)
    python3 desk.py tidy
    python3 desk.py remove [--yes]             (takes Desks out; lists first; the records and transcript archive always stay)

Three levels, detected, never required:
  folder   not a git repository: the topic is desks/<topic>/ and that is all
  git      a repository: each topic gets its own branch desk/<topic> in its own
           working copy under .claude/worktrees/, so several Desks can run at
           once and the main folder is never left half-edited
  github   a repository with a GitHub remote and the gh tool: close can push the
           branch and open a pull request

Run it from the folder Claude Code was opened on. It never pushes to a public
repository unless told to, never forces, never deletes unmerged work.
Standard library only.
"""
import datetime
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(os.path.dirname(HERE), "templates")


def run(args, cwd=None, check=False):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        die(f"`{' '.join(args)}` failed:\n{(p.stderr or p.stdout).strip()}")
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def die(msg, code=1):
    print("STOP: " + msg, file=sys.stderr)
    sys.exit(code)


def main_root():
    """The main folder, even when called from inside a topic's working copy."""
    rc, common, _ = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"])
    if rc != 0:
        return os.getcwd(), False
    return os.path.dirname(common) if os.path.basename(common) == ".git" else os.getcwd(), True


BLOCK = re.compile(r"(<!-- desk:start -->)(.*?)(<!-- desk:end -->)", flags=re.S)


def block_file(root):
    """The file that holds the Desk block. `CLAUDE.local.md` wins when it has one:
    that is where the block goes in a shared project whose `CLAUDE.md` is not
    yours to change. It is personal and stays out of the project's history."""
    for name in ("CLAUDE.local.md", "CLAUDE.md"):
        path = os.path.join(root, name)
        try:
            if BLOCK.search(open(path, encoding="utf-8").read()):
                return path
        except OSError:
            pass
    return None


def settings(root):
    """Lines like `- Desk root: desks/` inside the marked block."""
    out = {}
    path = block_file(root)
    if not path:
        return out
    m = BLOCK.search(open(path, encoding="utf-8").read())
    for line in m.group(2).splitlines():
        k = re.match(r"\s*-\s*([A-Za-z ]+):\s*(.+?)\s*$", line)
        if k:
            v = k.group(2)
            if len(v) > 1 and v[0] == v[-1] == "`" and "`" not in v[1:-1]:
                v = v[1:-1].strip()
            out[k.group(1).strip().lower()] = v
    return out


def is_off(cfg, key):
    """`off`, or `off` followed by a remark: `- Git: off (the folder has its own branches)`.
    Only the first word is read, and only to switch something of Desk's off, never on."""
    return re.match(r"off\b", cfg.get(key, "").strip().lower()) is not None


def close_mode(cfg):
    """How this folder closes, from its `Close:` line.

    ('', '') no line · ('merge', '') · ('review', '') · ('run', command) ·
    ('follow', file) · ('?', the line) when it is none of those. A line this
    script does not understand is never treated as if it were not there.
    """
    raw = cfg.get("close", "").strip()
    if not raw:
        return "", ""
    if raw.lower() in ("merge", "review"):
        return raw.lower(), ""
    m = re.match(r"house\s+(run|follow)\s+(.+)$", raw)
    if m:
        arg = m.group(2).strip()
        if len(arg) > 1 and arg[0] == arg[-1] == "`":
            arg = arg[1:-1].strip()
        if arg:
            return m.group(1), arg
    return "?", raw


def open_mode(cfg, key="open"):
    """How this folder runs a step (`Open:` or `Review:`): ('', '') Desks itself · ('desks', '') the user
    chose Desks' own in a folder that has its own · ('follow', file) the session follows a written
    routine · ('run', command) Desks runs the command · ('?', the line) a line not understood."""
    raw = cfg.get(key, "").strip()
    if not raw:
        return "", ""
    if raw.lower() == "desks":
        return "desks", ""
    m = re.match(r"house\s+(run|follow)\s+(.+)$", raw)
    if m:
        arg = m.group(2).strip()
        if len(arg) > 1 and arg[0] == arg[-1] == "`":
            arg = arg[1:-1].strip()
        if arg:
            return m.group(1), arg
    return "?", raw


def confirmed_file():
    conf = os.environ.get("DESK_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".config", "desk")
    return os.path.join(conf, "house-close.json")


def confirm_key(root, step="close"):
    return os.path.realpath(root) if step == "close" else f"{os.path.realpath(root)}#{step}"


def confirmed_close(root, step="close"):
    """The house routine the user said yes to for this folder and step, as recorded by `desk.py set`.

    It is kept outside the folder on purpose: a `Close: house ...` line can
    arrive with a clone or a pull, and nothing that arrives that way may run.
    """
    try:
        with open(confirmed_file(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return ""
    return data.get(confirm_key(root, step), "") if isinstance(data, dict) else ""


def confirmed_all():
    """Every folder's confirmed line, for rewriting. A file that cannot be read is never replaced:
    it holds other folders' confirmations too."""
    path = confirmed_file()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        die(f"{path} cannot be read as the list of confirmed closing routines. Move it aside and "
            "confirm again. Nothing was recorded.")
    return data


def confirm_close(root, line, data=None, step="close"):
    """Record the user's yes for this folder and step, or forget it when `line` is empty."""
    data = confirmed_all() if data is None else data
    key, path = confirm_key(root, step), confirmed_file()
    if line:
        data[key] = line
    elif key not in data:
        return
    else:
        del data[key]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    os.replace(path + ".tmp", path)


def inside(root, rel):
    """True when `rel`, read from `root`, stays inside it."""
    top = os.path.realpath(root)
    return os.path.commonpath([top, os.path.realpath(os.path.join(top, rel))]) == top


def default_branch(root):
    rc, out, _ = run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=root)
    if rc == 0 and out:
        return out.split("/", 1)[1]
    for b in ("main", "master"):
        if run(["git", "rev-parse", "--verify", "--quiet", b], cwd=root)[0] == 0:
            return b
    return run(["git", "branch", "--show-current"], cwd=root)[1]


def github(root):
    """(has a GitHub remote, gh is logged in, visibility or '')."""
    rc, url, _ = run(["git", "remote", "get-url", "origin"], cwd=root)
    if rc != 0 or "github.com" not in url:
        return False, False, ""
    if not shutil.which("gh") or run(["gh", "auth", "status"], cwd=root)[0] != 0:
        return True, False, ""
    rc, vis, _ = run(["gh", "repo", "view", "--json", "visibility", "-q", ".visibility"], cwd=root)
    return True, True, vis if rc == 0 else ""


def level(root, is_git, cfg):
    if not is_git or is_off(cfg, "git"):
        return "folder"
    if run(["git", "rev-parse", "--verify", "--quiet", "HEAD"], cwd=root)[0] != 0:
        return "folder"  # a repository with no commit yet cannot branch
    remote, gh_ok, _ = github(root)
    return "github" if (remote and gh_ok and not is_off(cfg, "github")) else "git"


def level_note(root, is_git, cfg, lv):
    """Why a git folder runs at the folder level, when the reason is not one the user chose (#45)."""
    if lv == "folder" and is_git and not is_off(cfg, "git") and \
            run(["git", "rev-parse", "--verify", "--quiet", "HEAD"], cwd=root)[0] != 0:
        return " (this repository has no commit yet; the git level starts after the first commit)"
    return ""


def slug(topic):
    s = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    if not s:
        die("give the topic a short name, like sell-camera", 2)
    return s


def worktree_of(root, branch):
    _, out, _ = run(["git", "worktree", "list", "--porcelain"], cwd=root)
    path = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = line[9:]
        elif line == f"branch refs/heads/{branch}":
            return path
    return None


# ---- topics, branches, base, lock (0.3.0) -------------------------------------------------

LOCK_TTL = 600  # seconds: a lock older than this is stale whatever its owner says


def prefix_of(cfg):
    p = cfg.get("branch prefix", "desk/").strip() or "desk/"
    return p if p.endswith("/") else p + "/"


def trailer_of(cfg):
    return cfg.get("ready trailer", "Desk-Status: ready").strip() or "Desk-Status: ready"


def git_dir(root):
    rc, common, _ = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root)
    return common if rc == 0 else os.path.join(root, ".git")


def state_dir(root, *more):
    d = os.path.join(git_dir(root), "desk-state", *more)
    os.makedirs(d, exist_ok=True)
    return d


def base_ref(root, cfg):
    """The ref a new topic is cut from and received topics are measured against: `Base:`, else the default branch."""
    return cfg.get("base", "").strip() or default_branch(root)


def fetch_base(root, ref):
    """Fetch the remote part of `origin/<branch>`. True when fresh, False when offline or local."""
    if "/" in ref and run(["git", "remote", "get-url", ref.split("/", 1)[0]], cwd=root)[0] == 0:
        return run(["git", "fetch", "--quiet", ref.split("/", 1)[0], ref.split("/", 1)[1]], cwd=root)[0] == 0
    return False


def ref_exists(root, ref):
    return run(["git", "rev-parse", "--verify", "--quiet", ref + "^{commit}"], cwd=root)[0] == 0


def is_ancestor(root, a, b):
    return run(["git", "merge-base", "--is-ancestor", a, b], cwd=root)[0] == 0


def topic_branches(root, cfg, topic):
    """`<prefix><topic>` and any `<prefix><topic>--<title>` a closing routine renamed it to, newest first."""
    pre = prefix_of(cfg)
    _, out, _ = run(["git", "for-each-ref", "--sort=-committerdate", "--format=%(refname:short)",
                     f"refs/heads/{pre}{topic}", f"refs/heads/{pre}{topic}--*"], cwd=root)
    return [b for b in out.splitlines() if b]


def topic_of_branch(cfg, branch):
    pre = prefix_of(cfg)
    return branch[len(pre):].split("--", 1)[0] if branch.startswith(pre) else ""


def head_ready(root, cfg, ref):
    """True when the commit at `ref` carries the ready trailer as a line of its own message."""
    _, msg, _ = run(["git", "log", "-1", "--format=%B", ref], cwd=root)
    want = trailer_of(cfg)
    return any(l.strip() == want for l in msg.splitlines())


def receive_target(root, cfg, branch=None):
    """The branch a ready topic is taken into: its parent's branch for a child, else `Receive into:`,
    else the local name of `Base:`, else the default branch."""
    if branch:
        _, parent, _ = run(["git", "config", f"branch.{branch}.deskparent"], cwd=root)
        if parent:
            pb = topic_branches(root, cfg, parent)
            return pb[0] if pb else None  # a child whose parent branch is gone is never taken into the base by default
    into = cfg.get("receive into", "").strip()
    if into:
        return into
    b = base_ref(root, cfg)
    return b.split("/", 1)[1] if b.startswith("origin/") else b


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class Lock:
    """One lock file for the parts of `open` that change git: pid and time inside, a 10-minute TTL.

    A lock whose owner is gone, or that is older than the TTL, is reclaimed; a live, fresh one is
    waited for (DESK_LOCK_WAIT seconds, default 30) and then reported, never broken. A reclaim
    removes only the text it judged stale. What remains is a window of a few instructions between
    that re-read and the unlink; the work under the lock (a worktree add) fails loudly if it ever
    overlaps, and nothing is lost."""

    def __init__(self, root):
        self.path = os.path.join(state_dir(root), "open.lock")
        self.mine = f"{os.getpid()} {int(time.time())}"

    def stale(self):
        """The text of the lock when it is stale (so only that text is removed), else ''.

        A lock whose text cannot be read (empty, or not a pid and a time) is live until its file is
        older than the TTL: a writer may be an instant away from finishing, and the file is only ever
        created whole (see `__enter__`), so an unreadable one is a foreign or damaged file, not a race."""
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = f.read()
            pid, at = int(raw.split()[0]), int(raw.split()[1])
        except (ValueError, IndexError):
            try:
                old = time.time() - os.stat(self.path).st_mtime > LOCK_TTL
            except OSError:
                return ""  # gone while we looked: just try again
            return "?" if old else ""
        except OSError:
            return ""  # gone while we looked: just try again
        return raw if time.time() - at > LOCK_TTL or not alive(pid) else ""

    def create(self):
        """Make the lock file with its content already in it: write a temp file, then link it into place.
        `link` fails if the lock exists, so there is never a moment when the lock exists and is empty."""
        tmp = f"{self.path}.{os.getpid()}.{secrets.token_hex(4)}"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(self.mine)
        try:
            os.link(tmp, self.path)
        finally:
            os.unlink(tmp)

    def __enter__(self):
        deadline = time.time() + float(os.environ.get("DESK_LOCK_WAIT", "30"))
        while True:
            try:
                self.create()
                return self
            except FileExistsError:
                was = self.stale()
                if was:
                    try:  # remove it only if it is still the lock we judged stale; a fresh one made meanwhile stays
                        with open(self.path, encoding="utf-8") as f:
                            now = f.read()
                        if (was == "?" and self.stale() == "?") or now == was:
                            os.unlink(self.path)
                    except OSError:
                        pass
                    continue
                if time.time() > deadline:
                    die("another Desk is being opened right now (a live lock in "
                        f"{self.path}). Wait a minute and run it again. Nothing was changed.", 6)
                time.sleep(0.2)

    def __exit__(self, *a):
        try:
            if open(self.path, encoding="utf-8").read() == self.mine:
                os.unlink(self.path)
        except OSError:
            pass


def sessions_dir(work, cfg, topic, droot):
    pat = cfg.get("sessions", "").strip()
    if pat:
        return os.path.join(work, pat.replace("{topic}", topic).strip("/"))
    return os.path.join(work, droot, topic, "sessions")


def ignored(work, rel):
    """True when git ignores `rel` in `work`: state written there would never be saved (#25, #31)."""
    return run(["git", "check-ignore", "-q", rel], cwd=work)[0] == 0


def current_topic(cfg):
    """The topic of the working copy the command runs in, or ''."""
    rc, top, _ = run(["git", "rev-parse", "--show-toplevel"], cwd=os.getcwd())
    if rc != 0:
        return ""
    _, br, _ = run(["git", "branch", "--show-current"], cwd=top)
    return topic_of_branch(cfg, br)


def topic_work(root, cfg, topic):
    """(working copy path, branch) of an open topic, or (None, None)."""
    for b in topic_branches(root, cfg, topic):
        w = worktree_of(root, b)
        if w:
            return w, b
    return None, None


def depth_of(root, cfg, branch):
    d, seen = 0, set()
    while branch and branch not in seen:
        seen.add(branch)
        _, parent, _ = run(["git", "config", f"branch.{branch}.deskparent"], cwd=root)
        if not parent:
            break
        pb = topic_branches(root, cfg, parent)
        branch, d = (pb[0] if pb else ""), d + 1
    return d


def reserve_at(cfg, depth):
    """The usage reserve for the child level `depth + 1`, from `Usage reserve: 50` or `50, 40, 30` (the last repeats)."""
    vals = [v.strip() for v in re.split(r"[,;]", cfg.get("usage reserve", "")) if v.strip()]
    return vals[min(depth, len(vals) - 1)] if vals else ""


def seed(folder, topic, pointers=False, work=None):
    """Create the topic's folder. Refuses a folder git ignores: state there is never saved (#25)."""
    if work and run(["git", "rev-parse", "--is-inside-work-tree"], cwd=work)[0] == 0:
        rel = os.path.relpath(os.path.join(folder, "README.md"), work)
        if ignored(work, rel):
            die(f"{rel} is ignored by git, so what a Desk writes there would never be saved. Point the Desk root "
                "at a tracked folder (`desk.py set \"Desk root\" ...`) or stop ignoring it. Nothing was created.")
    new = not os.path.exists(os.path.join(folder, "README.md"))
    os.makedirs(folder, exist_ok=True)
    if not pointers:
        os.makedirs(os.path.join(folder, "sessions"), exist_ok=True)
        os.makedirs(os.path.join(folder, "reviews"), exist_ok=True)
    if new:
        text = open(os.path.join(TEMPLATES, "README.md"), encoding="utf-8").read()
        open(os.path.join(folder, "README.md"), "w", encoding="utf-8").write(text.replace("{{topic}}", topic))
    dec = os.path.join(folder, "decisions.md")
    if not pointers and not os.path.exists(dec):
        open(dec, "w", encoding="utf-8").write("# Decisions\n\nOne dated line each: what was decided, why, and what was ruled out.\n")
    return new


STATE_FILES = ("README.md",)


def holds_state(folder, work):
    """What a topic folder in the main checkout keeps beyond a pointer README: the files that
    are ignored, untracked or anything but README.md (#31). A finding, not an error."""
    found = []
    for d, _, files in os.walk(folder):
        for f in files:
            rel = os.path.relpath(os.path.join(d, f), work)
            if f in STATE_FILES and os.path.dirname(rel) == os.path.relpath(folder, work):
                text = open(os.path.join(d, f), encoding="utf-8", errors="replace").read()
                if len(text.splitlines()) <= 15:
                    continue
                found.append(rel + " (a README longer than a pointer)")
            else:
                found.append(rel)
    return found


def cmd_status():
    root, is_git = main_root()
    cfg = settings(root)
    lv = level(root, is_git, cfg)
    print(f"folder:   {root}")
    print(f"level:    {lv}{level_note(root, is_git, cfg, lv)}")
    print(f"desk root: {cfg.get('desk root', 'desks/')}")
    print(f"settings: {block_file(root) or 'none (defaults)'}")
    omode, oarg = open_mode(cfg)
    if omode in ("follow", "run"):
        print(f"opens:    with this folder's own routine ({omode} {oarg}); topics it keeps elsewhere are not listed")
    elif omode == "?":
        print(f"opens:    `Open: {oarg}` is not understood; open will stop")
    if is_git:
        remote, gh_ok, vis = github(root)
        print(f"branch:   {default_branch(root)} (default)")
        print(f"base:     {base_ref(root, cfg)}")
        print("github:   " + ("no GitHub remote" if not remote else ("gh not logged in" if not gh_ok else f"ready, repository is {vis or 'of unknown visibility'}")))
        _, out, _ = run(["git", "worktree", "list", "--porcelain"], cwd=root)
        pre = re.escape(prefix_of(cfg))
        open_topics = [t.split("--", 1)[0] for t in re.findall(rf"branch refs/heads/{pre}(.+)", out)]
        print("open desks: " + (", ".join(open_topics) or "none"))
    dr = os.path.join(root, cfg.get("desk root", "desks/"))
    if os.path.isdir(dr):
        topics = sorted(d for d in os.listdir(dr) if os.path.isfile(os.path.join(dr, d, "README.md")))
        print("topics:   " + (", ".join(topics) or "none"))
        now = datetime.datetime.now().timestamp()
        for d in topics:  # the facts for a brief across topics; the recommendation is the session's
            f = os.path.join(dr, d, "README.md")
            text = open(f, encoding="utf-8").read()
            m = re.search(r"^## Next step\s*\n+(.+?)(?:\n\s*\n|\n## |\Z)", text, flags=re.M | re.S)
            step = " ".join(m.group(1).split())[:160] if m else "(no Next step section)"
            if "{{" in step:  # the template's own text is not a next step (#33)
                step = "(no next step written yet: not started)"
            days = int((now - os.path.getmtime(f)) // 86400)
            print(f"  {d}: notes {days} day(s) old · next: {step}")
        waiting = []
        for d in sorted(os.listdir(dr)):
            box = os.path.join(dr, d, "inbox")
            n = len(os.listdir(box)) if os.path.isdir(box) else 0
            if n:
                waiting.append(f"{d} ({n})")
        if waiting:
            print("notes waiting: " + ", ".join(waiting) + "  <- tell the user; they were left by other desks")
        if is_git:  # state in the main checkout is state no branch holds (#31)
            keep = {t: holds_state(os.path.join(dr, t), root) for t in sorted(os.listdir(dr)) if os.path.isdir(os.path.join(dr, t))}
            keep = {t: v for t, v in keep.items() if v}
            for t, v in keep.items():
                print(f"STATE OUTSIDE HISTORY: {os.path.join(dr, t)} holds {len(v)} file(s) that no branch carries "
                      f"(e.g. {v[0]}). `desk.py migrate {t}` copies them into the topic's working copy.")
            if cfg.get("pointers only", "").lower() == "yes" and keep:
                print("pointers only: yes, so each of these is a finding")
    print("python3:  ok")
    return 0


def run_hook(root, cmd, topic, folder, work, step):
    """Run a recorded `house run` command, only in the exact form the user confirmed for this step."""
    line = cfg_line(root, step)
    if confirmed_close(root, step) != line:
        die(f"this folder's `{step.capitalize()}:` routine has not been confirmed by the user in this exact form:\n"
            f"    {step.capitalize()}: {line}\nShow them the line. Only on their yes, record it:\n"
            f"    desk.py set {step.capitalize()} {shlex.quote(line)}\nNothing was run.")
    print(f"running this folder's {step} routine: {cmd}", flush=True)
    env = dict(os.environ, DESK_TOPIC=topic, DESK_TOPIC_FOLDER=folder, DESK_WORK=work or root, DESK_STEP=step)
    return subprocess.run(cmd, shell=True, cwd=work or root, stdin=subprocess.DEVNULL, env=env).returncode


def cfg_line(root, step):
    return settings(root).get(step, "").strip()


def cmd_open(topic, reopen=False, parent=None):
    topic = slug(topic)
    root, is_git = main_root()
    cfg = settings(root)
    omode, oarg = open_mode(cfg)
    if omode == "?":
        die(f"`Open: {oarg}` is not one this script understands. It reads `house follow <file>`, `house run <command>` or `desks`. Nothing was opened.", 2)
    if omode == "" and not cfg.get("open", "").strip():
        _, first, found = scan(root)
        own = [rel for not_named, rel, _ in found["open"] if not not_named]
        if own:  # #53: the routines exist but nobody recorded them; ask before making a second home
            die(f"this folder seems to open topics its own way ({', '.join(own[:2])}, named in {first[0]}). "
                "Ask the user the setup question first: `desk.py scan` shows what was found, and "
                "`desk.py set \"Open\" \"house follow <file>\"` records their yes. To use Desks' own open "
                "anyway, record `desk.py set \"Open\" \"desks\"`. Nothing was opened.")
    if omode == "follow":  # the folder opens topics its own way; making a second home for the topic is the bug (#28)
        if not inside(root, oarg) or not os.path.isfile(os.path.join(root, oarg)):
            die(f"this folder opens topics with `{oarg}`, which is not there. Nothing was opened.")
        print(f"open:   this folder opens topics its own way: follow {oarg} for '{topic}', and work where it says.")
        print("        Desks made no topic folder, branch or working copy here.")
        return 0
    if omode == "run":
        rc = run_hook(root, oarg, topic, "", None, "open")
        if rc != 0:
            die(f"this folder's opening routine failed (exit {rc}). Nothing was opened by Desks.")
        print("opened with this folder's own routine. Desks made no topic folder, branch or working copy here.")
        return 0
    droot = cfg.get("desk root", "desks/").strip("/")
    lv = level(root, is_git, cfg)
    work = branch = None
    fresh = ""
    if lv == "folder":
        work = root
    else:
        work, branch, fresh = open_working_copy(root, cfg, topic, reopen, parent)
    folder = os.path.join(work, droot, topic)
    new = seed(folder, topic, pointers=cfg.get("pointers only", "").lower() == "yes", work=None if lv == "folder" else work)
    print(f"level:  {lv}{level_note(root, is_git, cfg, lv)}")
    print(f"topic:  {topic} ({'new' if new else 'continued'})")
    print(f"work in: {folder}")
    inbox = os.path.join(folder, "inbox")
    left = sorted(os.listdir(inbox)) if os.path.isdir(inbox) else []
    if left:
        print(f"inbox:  {len(left)} note(s) left by other desks in {inbox}: fold each into the README, then delete it")
    if not new and "## Next step" not in open(os.path.join(folder, "README.md"), encoding="utf-8").read():
        print("readme: this README was here before Desks. Add the sections State, Next step, Open and What we learned to it; keep everything it already says")
    if lv != "folder":
        print(f"branch: {branch}  ·  working copy: {work}")
        print(f"worktree: {work}")
        if fresh:
            print(fresh)
        print(f"note:   files in {root} that were never committed are not in the working copy; read them from there by full path")
        if parent:
            d = depth_of(root, cfg, branch)
            res = reserve_at(cfg, d - 1)
            print(f"parent: {parent} (level {d})" + (f" · usage reserve at this level: {res}" if res else ""))
            brief = os.path.join(folder, "brief.md")
            if not os.path.exists(brief):
                text = open(os.path.join(TEMPLATES, "brief.md"), encoding="utf-8").read()
                plan = run(["git", "rev-parse", "--short=12", cut_of(root, cfg, parent)], cwd=root)[1]
                for k, v in (("parent", parent), ("topic", topic), ("level", str(d)), ("reserve", res or "none set"), ("plan_commit", plan)):
                    text = text.replace("{{" + k + "}}", v)
                open(brief, "w", encoding="utf-8").write(text)
                print(f"brief:  {brief} (fill the {{{{...}}}} parts and commit it before the child starts)")
    return 0


def cut_of(root, cfg, parent):
    return topic_branches(root, cfg, slug(parent))[0]


def open_working_copy(root, cfg, topic, reopen, parent):
    """(working copy, branch, note) for a topic at the git level; creates or reattaches under one lock."""
    base = base_ref(root, cfg)
    note = ""
    if parent:
        pb = topic_branches(root, cfg, slug(parent))
        if not pb:
            die(f"no topic named {parent} to open a child of. Nothing was opened.")
        cut = pb[0]
        d = depth_of(root, cfg, pb[0]) + 1
        cap = cfg.get("depth cap", "3").strip().lower()
        if cap not in ("none", "off", "unlimited") and cap.isdigit() and d > int(cap):
            die(f"{parent} is at level {d - 1}; a child would be at level {d}, past `Depth cap: {cap}`. Nothing was opened.", 7)
    else:
        cut = base
        if fetch_base(root, base):
            note = f"base:   {base} (fetched)"
        elif ref_exists(root, base):
            note = f"base:   {base} (offline: the local ref, which may be behind)"
        else:
            die(f"no {base} to cut the topic from. A topic starts from the configured base, never from whatever is checked out. Nothing was opened.", 3)
    w, b = topic_work(root, cfg, topic)
    if w:
        return w, b, note
    with Lock(root):
        run(["git", "worktree", "prune"], cwd=root)
        w, b = topic_work(root, cfg, topic)  # another open may have made it while we waited
        if w:
            return w, b, note
        fam = topic_branches(root, cfg, topic)
        work = os.path.join(root, ".claude", "worktrees", f"desk-{topic}")
        exclude = os.path.join(git_dir(root), "info", "exclude")  # working copies stay out of the user's commits
        try:
            os.makedirs(os.path.dirname(exclude), exist_ok=True)
            if ".claude/worktrees/" not in (open(exclude, encoding="utf-8").read() if os.path.exists(exclude) else ""):
                open(exclude, "a", encoding="utf-8").write("\n.claude/worktrees/\n")
        except OSError:
            pass
        if fam:
            b = fam[0]
            if head_ready(root, cfg, b):
                target = receive_target(root, cfg, b)
                if is_ancestor(root, b, base if not parent else cut) or (ref_exists(root, target) and is_ancestor(root, b, target)):
                    n = 2
                    while topic_branches(root, cfg, f"{topic}-{n}"):
                        n += 1
                    die(f"{b} was already received (its ready close is in {target}). Continue the work as a new topic cut fresh from "
                        f"the base: desk.py open {topic}-{n}. Nothing was opened.", 4)
                if not reopen:
                    die(f"{b} was closed as ready and has not been received yet. Opening it again continues work that was already handed over. "
                        f"If that is what the user wants, run: desk.py open {topic} --reopen. Nothing was opened.", 5)
            run(["git", "worktree", "add", work, b], cwd=root, check=True)
            return work, b, note
        b = prefix_of(cfg) + topic
        run(["git", "worktree", "add", "-b", b, work, cut], cwd=root, check=True)
        if parent:
            run(["git", "config", f"branch.{b}.deskparent", slug(parent)], cwd=root, check=True)
        return work, b, note


def closed_line(topic, how):
    """The one line a session copies into its reply, like a review label (#66): the close happened."""
    print(f"Closed line: Desk `{topic}` closed · {how}")


def load_review():
    """review.py as a module (it holds the receipts), or None when it is not next to this script."""
    try:
        spec = importlib.util.spec_from_file_location("review", os.path.join(HERE, "review.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except (Exception, SystemExit):
        return None


def section_body(text, name):
    """The text under the heading that starts with `name` (any level 2 or 3 heading), or ''."""
    m = re.search(rf"^#{{2,3}}[ \t]*{re.escape(name.strip())}\b[^\n]*\n(.*?)(?=^#{{1,3}}[ \t]|\Z)", text, flags=re.M | re.S | re.I)
    return m.group(1).strip() if m else ""


LESSON_HEADS = ("Lessons", "What we learned", "Hiccups")
DEST = re.compile(r"(?:→|->)\s*(topic|house\s+\S+|issue\s+\S+|dropped:\s*\S.*)\s*$", re.I)
LABEL = re.compile(r"Review:\s*\[([a-z][a-z -]*)(?::[^\]]*)?\]([^\n]*)", re.I)
LABELS_NEEDING_RECEIPT = {"converged", "thin", "open", "private-lane-only"}


def lesson_problems(text, work, root):
    """Every lesson line names where it lands (#32): `→ topic`, `→ house <file>`, `→ issue <ref>` or `→ dropped: <reason>`."""
    out = []
    for head in LESSON_HEADS:
        for line in section_body(text, head).splitlines():
            line = line.strip()
            if not line.startswith(("-", "*")) or len(line) < 3:
                continue
            m = DEST.search(line)
            if not m:
                out.append(f"lesson without a destination: {line[:90]} (end it with → topic, → house <file>, → issue <ref> or → dropped: <reason>)")
            elif m.group(1).lower().startswith("house"):
                path = m.group(1).split(None, 1)[1].strip("`")
                if not any(os.path.isfile(os.path.join(b, path)) for b in (work, root)) or not inside(work, path):
                    out.append(f"lesson names a house file that is not there: {path}")
    return out


def label_problems(text, cfg, work, root):
    """A reply label comes from a receipt, never from typing (#15). [same-vendor] and [unreviewed] say less than they could
    prove, so they need none; `[quick]` needs the user's profile to allow it; the others need a receipt that checks out."""
    out, rv = [], None
    for m in LABEL.finditer(text):
        label, tail = m.group(1).strip().lower(), m.group(2)
        if label in ("same-vendor", "unreviewed"):
            continue
        if label == "quick" or "quick" in label:
            if cfg.get("quick loop", "").strip().lower() not in ("allowed", "yes"):
                out.append("a `[quick]` label: this folder's Desk block does not list `- Quick loop: allowed`; the loop is not skippable by the session")
            continue
        rid = re.search(r"receipt\s+([0-9a-f]{10})\b", tail)
        if label not in LABELS_NEEDING_RECEIPT:
            out.append(f"an unknown review label [{label}]")
            continue
        if not rid:
            out.append(f"[{label}] has no receipt: write the label line exactly as review.py printed it")
            continue
        rv = rv or load_review()
        if rv is None:
            out.append("review.py is not next to desk.py, so the receipt cannot be checked")
            break
        state = rv.receipt_state(rid.group(1), [work, root, os.getcwd()])
        if not state:
            out.append(f"[{label}] receipt {rid.group(1)} was not found: the label is unverified")
        elif state["now"] in ("stale", "unverified"):  # whatever the label says, this receipt does not back it
            out.append(f"[{label}] receipt {rid.group(1)} is {state['now']}: " + state["why"])
        elif label == "converged" and state["now"] != "converged":
            out.append(f"[converged] receipt {rid.group(1)} is {state['now']}: " + state["why"])
        elif label in ("thin", "private-lane-only") and state["label"] not in ("thin", "private-lane-only", "open"):
            out.append(f"[{label}] does not match receipt {rid.group(1)}, which says {state['label']}")
    return out


def template_paths(cfg, work, root):
    """(found files, names that were not found) for `Close note:`, which may list several files separated by `;` or `,`."""
    found, missing = [], []
    for rel in [r.strip().strip("`") for r in re.split(r"[;,]", cfg.get("close note", "")) if r.strip()]:
        hit = next((os.path.join(b, rel) for b in (work, root) if inside(b, rel) and os.path.isfile(os.path.join(b, rel))), None)
        (found if hit else missing).append(hit or rel)
    return found, missing


def template_path(cfg, work, root):
    return (template_paths(cfg, work, root)[0] or [None])[0]


def required_sections(cfg, work, root):
    """What the close note must have: `Close sections:` if listed, else every `##` heading of the `Close note:` templates."""
    listed = [s.strip() for s in cfg.get("close sections", "").split("|") if s.strip()]
    if listed:
        return listed
    out = []
    for t in template_paths(cfg, work, root)[0]:
        with open(t, encoding="utf-8") as f:
            out += [m.group(1).strip() for m in re.finditer(r"^##[ \t]+(.+?)[ \t]*$", f.read(), flags=re.M)]
    return out


def close_problems(cfg, work, root, topic, note_text, readme_text):
    probs = []
    for m in template_paths(cfg, work, root)[1]:
        probs.append(f"`Close note:` names a template that is not there: {m}")
    for sec in required_sections(cfg, work, root):
        if not section_body(note_text, sec):
            probs.append(f"the close note has no section '{sec}' with something in it")
    probs += lesson_problems(note_text, work, root)
    probs += label_problems(note_text + "\n" + readme_text, cfg, work, root)
    return probs


def head_trailer_commit(work, cfg, topic):
    """Give the branch head the ready trailer, so `receive` and `digest` can see the topic is handed over."""
    if head_ready(work, cfg, "HEAD"):
        return
    rc, _, err = run(["git", "commit", "--allow-empty", "-q", "-m", f"desk: {topic} ready\n\n{trailer_of(cfg)}"], cwd=work)
    if rc != 0:
        if "tell me who you are" in err or "auto-detect email" in err:  # not a conflict (#42)
            die("git does not know who you are, so it cannot record the close. Nothing was changed. The user sets it once:\n"
                '  git config --global user.name "Their Name"\n  git config --global user.email their@email')
        die("could not record the ready trailer:\n" + err)


# ---- the transcript archive (0.3.0) ---------------------------------------------------------

SOURCE_LINE = re.compile(r"^([ \t]*)Source ID / UUID:[ \t]*(.*)$", re.M)
SHA_LINE = re.compile(r"^[ \t]*Transcript sha256:.*\n?", re.M)
UUID = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")


def host_projects():
    """Where the host (Claude Code) keeps its session transcripts. `DESK_TRANSCRIPTS_SRC` overrides it."""
    return os.environ.get("DESK_TRANSCRIPTS_SRC") or os.path.join(os.path.expanduser("~"), ".claude", "projects")


def project_folder_name(path):
    """The host names a project's folder after its path, every non-alphanumeric character turned into `-`."""
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(path))


def find_transcript(source_id, folders):
    """The transcript file for `source_id` (searched in every project folder), else the newest one in the
    project folders of `folders`; ('', '') when there is none. A `source_id` that is given but not found is
    never replaced by the newest: that would archive some other conversation under its name."""
    base = host_projects()
    if source_id:
        for d in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            hit = os.path.join(base, d, source_id + ".jsonl")
            if os.path.isfile(hit):
                return hit, source_id
        return "", source_id
    best = ""
    for f in folders:
        d = os.path.join(base, project_folder_name(f))
        for n in os.listdir(d) if os.path.isdir(d) else []:
            if n.endswith(".jsonl") and (not best or os.path.getmtime(os.path.join(d, n)) > os.path.getmtime(best)):
                best = os.path.join(d, n)
    return best, os.path.basename(best)[:-6] if best else ""


def inside_work_tree(path):
    """True when `path` (which may not exist yet) lies inside a git working tree."""
    d = os.path.abspath(path)
    while d and not os.path.isdir(d):
        d = os.path.dirname(d)
    return run(["git", "rev-parse", "--is-inside-work-tree"], cwd=d or "/")[1] == "true"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def archive_transcript(cfg, root, work, note_path):
    """With `Transcripts: <directory>`, copy this session's transcript there and write its sha256 next to the
    source ID in the close note. Off when the line is unset or `off`. Returns the lines to print; dies, before
    anything is closed, when it cannot do what was asked."""
    raw = cfg.get("transcripts", "").strip()
    if not raw or is_off(cfg, "transcripts"):
        return []
    target = os.path.abspath(os.path.expanduser(raw))
    if inside_work_tree(target):
        die(f"`Transcripts: {raw}` is inside a git working tree, and a transcript must never be copied into one "
            "(it could be committed and pushed). Choose a folder outside every repository. The Desk is not closed.")
    with open(note_path, encoding="utf-8") as f:
        text = f.read()
    m = SOURCE_LINE.search(text)
    found = UUID.search(m.group(2)) if m else None
    src, sid = find_transcript(found.group(0) if found else "", [work, root])
    if not src:
        die((f"no transcript for session {sid} was found under {host_projects()}" if sid else
             f"no transcript was found under {host_projects()} for this project") +
            ". The host may have deleted it, or the Source ID line names another session. Fix the line, or set "
            "`Transcripts: off` for this folder. The Desk is not closed.")
    os.makedirs(target, mode=0o700, exist_ok=True)
    dest = os.path.join(target, sid + ".jsonl")
    tmp = f"{dest}.{os.getpid()}.tmp"
    shutil.copyfile(src, tmp)
    os.chmod(tmp, 0o600)
    os.replace(tmp, dest)
    digest = sha256_of(dest)
    text = SHA_LINE.sub("", text)
    if m:
        m = SOURCE_LINE.search(text)
        text = text[:m.end()] + f"\n{m.group(1)}Transcript sha256: {digest}" + text[m.end():]
    else:
        text = text.rstrip("\n") + f"\n\nSource ID / UUID: {sid}\nTranscript sha256: {digest}\n"
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(text)
    return [f"transcript: copied to {dest} (sha256 {digest[:16]}...), recorded in the close note"]


def cmd_close(topic, how, title):
    root, is_git = main_root()
    cfg = settings(root)
    topic = slug(topic) if topic else current_topic(cfg)
    if not topic:
        die("say which topic to close, or run this from the topic's working copy", 2)
    droot = cfg.get("desk root", "desks/").strip("/")
    lv = level(root, is_git, cfg)
    mode, arg = close_mode(cfg)
    if mode == "?":
        die(f"the `Close:` line of this folder is not one this script understands:\n    Close: {arg}\n"
            "It reads `merge`, `review`, `house run <command>` or `house follow <file>`. Nothing was run.")
    house = mode in ("run", "follow")
    if house and how:
        die(f"this folder closes with its own routine (`Close: house {mode} {arg}`), and {how} does not "
            "override it. Run `desk.py close <topic>` with no flag. Nothing was run.")
    if not house and not how:
        how = {"merge": "--merge", "review": "--pr"}.get(mode, "")
        if not how:
            die("no `Close:` line is recorded for this folder: pass --merge or --pr, or record one with `desk.py set`", 2)
    branch = ""
    if open_mode(cfg)[0] == "follow":
        # #65: the folder's own opener made the working copy; the topic is where the session works.
        work = house_work()
        if not os.path.isfile(os.path.join(work, droot, topic, "README.md")) and \
                os.path.isfile(os.path.join(root, droot, topic, "README.md")):
            work = root
    elif lv == "folder":
        work = root
    else:
        here = house_work()  # the working copy the command runs in, found from where it is run, not from the main folder
        _, cur, _ = run(["git", "branch", "--show-current"], cwd=here)
        work, branch = (here, cur) if topic_of_branch(cfg, cur) == topic else topic_work(root, cfg, topic)
    if not work:
        die(f"no open desk named {topic}")
    if not branch and lv != "folder":
        _, branch, _ = run(["git", "branch", "--show-current"], cwd=work)
    if not house and lv != "folder" and topic_of_branch(cfg, branch) != topic:
        # a session sitting on main, or on another topic's branch, must never have that branch pushed or merged
        die(f"the branch checked out in {work} is {branch or 'none'}, which is not the branch of topic {topic}. "
            "Run the close from that topic's working copy. Nothing was pushed or merged.")
    folder = os.path.join(work, droot, topic)
    if not os.path.isfile(os.path.join(folder, "README.md")):
        where = "the working copy the folder's own opener made, the one you work in" if open_mode(cfg)[0] == "follow" \
            else "the folder the session was opened on"
        die(f"there is no topic '{topic}' under {os.path.join(work, droot)}. Run this from {where}. "
            "The Desk is not closed.")
    sdir = sessions_dir(work, cfg, topic, droot)
    notes = sorted(f for f in os.listdir(sdir) if f.endswith(".md")) if os.path.isdir(sdir) else []
    if not notes:
        die(f"no session note yet: write {os.path.join(sdir, '<date>-<title>.md')} from "
            f"{template_path(cfg, work, root) or os.path.join(TEMPLATES, 'session-house.md' if house else 'session.md')}. Every .md in the topic folder must also have no "
            "{{…}} placeholder left: the README that open made has some.")
    if not open(os.path.join(folder, "README.md"), encoding="utf-8").read().strip():
        die(f"{os.path.join(folder, 'README.md')} is empty: the next session would start from nothing")
    check = [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith(".md")]
    check += [os.path.join(sdir, f) for f in notes]
    unfilled = []  # all of them in one run, so it never takes two failed closes to learn what is left (#44)
    for f in check:
        left = re.findall(r"\{\{[^}]*\}\}", open(f, encoding="utf-8").read())
        if left:
            unfilled.append(f"  {f}: {', '.join(left[:4])}" + (f" and {len(left) - 4} more" if len(left) > 4 else ""))
    if unfilled:
        die("unfilled placeholders, fill or remove each:\n" + "\n".join(unfilled))
    note_text = open(os.path.join(sdir, notes[-1]), encoding="utf-8").read()
    probs = close_problems(cfg, work, root, topic, note_text, open(os.path.join(folder, "README.md"), encoding="utf-8").read())
    if probs:
        die("the close is refused until each of these is fixed. The Desk is not closed:\n" + "\n".join("  - " + p for p in probs))
    archived = archive_transcript(cfg, root, work, os.path.join(sdir, notes[-1]))
    for line in archived:
        print(line)
    if archived and lv != "folder":
        # The close note now carries the hash. Desks saves that one file itself, even under a house close (the only
        # git step it takes there): the routine that follows must find a clean tree, and the hash must reach the branch.
        note_rel = os.path.relpath(os.path.join(sdir, notes[-1]), work)
        if run(["git", "diff", "--quiet", "--", note_rel], cwd=work)[0] != 0:
            run(["git", "commit", "-q", "--only", "-m", f"desk: {topic} transcript archived", "--", note_rel], cwd=work)
    if house:
        return close_house(root, topic, folder, work, lv, cfg, notes[-1], note_text, mode, arg, cfg.get("close", "").strip())
    if lv == "folder":
        print("closed (folder level): nothing to merge. The README is the state.")
        closed_line(topic, "folder level, the README is the state")
        return 0
    _, dirty, _ = run(["git", "status", "--porcelain"], cwd=work)
    if dirty:
        die("uncommitted files in the working copy. Commit the ones you wrote, by path:\n" + dirty)
    base = receive_target(root, cfg, branch)
    if base is None:
        die("its parent topic's branch is gone, so there is nothing to merge this child into or open a pull request against. "
            "Reopen the parent or re-parent the child by hand. Nothing was pushed or merged.")
    title = title or f"{topic}: {notes[-1][:-3]}"
    if how == "--pr":
        if lv != "github":
            die("no GitHub remote with gh logged in; use --merge, or set GitHub up first")
        _, _, vis = github(root)
        if vis.upper() == "PUBLIC" and cfg.get("public pushes", "").lower() != "yes":
            die("this repository is PUBLIC. Pushing would publish the desk. That needs the user's word; "
                "record `- Public pushes: yes` in the CLAUDE.md block only if they say so.")
        head_trailer_commit(work, cfg, topic)
        run(["git", "push", "-u", "origin", branch], cwd=work, check=True)
        rc, out, err = run(["gh", "pr", "create", "--base", base, "--head", branch, "--title", title,
                            "--body-file", os.path.join(sdir, notes[-1])], cwd=work)
        if rc != 0 and "already exists" not in err:
            die("could not open the pull request:\n" + err)
        print("pull request: " + (out or err).splitlines()[-1])
        print("The working copy stays until the pull request is merged; then run `desk.py tidy`.")
        closed_line(topic, "sent for review as a pull request, not merged yet")
        return 0
    _, cur, _ = run(["git", "branch", "--show-current"], cwd=root)
    _, main_dirty, _ = run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root)
    if cur != base or main_dirty:
        die(f"the main folder must be on {base} with no half-finished changes before merging (it is on {cur or 'no branch'}"
            f"{', with changes' if main_dirty else ''}). Nothing was changed.")
    head_trailer_commit(work, cfg, topic)
    rc, _, err = run(["git", "merge", "--no-ff", branch, "-m", f"desk {title}"], cwd=root)
    if rc != 0:
        run(["git", "merge", "--abort"], cwd=root)
        if "tell me who you are" in err or "auto-detect email" in err:  # not a conflict (#42)
            die("git does not know who you are, so it cannot record the merge. Nothing was changed. The user sets it once:\n"
                '  git config --global user.name "Their Name"\n  git config --global user.email their@email')
        die("the merge failed and was undone (a conflict, a hook, or another git error). Nothing was changed:\n" + err)
    run(["git", "worktree", "remove", work], cwd=root, check=True)
    run(["git", "branch", "-d", branch], cwd=root)
    _, sha, _ = run(["git", "rev-parse", "--short", "HEAD"], cwd=root)
    print(f"merged into {base} and tidied. The topic now lives in {os.path.join(root, droot, topic)}")
    print(f"to undo this whole desk later: git revert -m 1 {sha}")
    closed_line(topic, f"merged into {base} ({sha})")
    return 0


def next_step(folder):
    try:
        text = open(os.path.join(folder, "README.md"), encoding="utf-8").read()
    except OSError:
        return ""
    m = re.search(r"^## Next step\s*\n+(.+?)(?:\n\s*\n|\n## |\Z)", text, flags=re.M | re.S)
    return " ".join(m.group(1).split())[:200] if m else ""


def close_house(root, topic, folder, work, lv, cfg, note, note_text, mode, arg, line):
    """The folder has its own closing routine, so that routine is the close.

    Desks does no git of its own here: no merge, no push, no pull request, no rename. What the
    routine owns is what `House git:` says, and nothing else is the session's to improvise.
    `run` executes the recorded command and stops if it fails. `follow` names a written
    procedure the session carries out itself; Desks cannot see that, and says so.
    Desks keeps its own last steps: the checks above ran first; afterwards it looks for unsaved
    files, for the ready trailer, and prints the next step.
    """
    was = confirmed_close(root)  # the whole value as it was read back when they said yes, not a tidied form of it
    if was != line:
        die("this folder's closing routine has not been confirmed by the user in this exact form:\n"
            f"    Close: {line}\n"
            + (f"The form they confirmed was:\n    Close: {was}\n" if was else "")
            + "Show them the line. Only on their yes, record it:\n"
            f"    desk.py set Close {shlex.quote(line)}\nNothing was run.")
    lines = [x for x in note_text.splitlines() if x.strip()]
    if len(lines) > 20 and not cfg.get("close sections", "").strip():
        print(f"note:   the session note {note} is {len(lines)} lines. With a house close the session note only points at "
              "the folder's own record of the session; it does not retell it.")
    owns = cfg.get("house git", "").strip()
    print("git:    the folder's routine owns " + (owns if owns else "every git step of the close") +
          "; do no git of your own around it.")
    if mode == "follow":
        if not inside(root, arg):
            die(f"the closing procedure this folder names is outside it: {arg}. Nothing was run.")
        if not os.path.isfile(os.path.join(root, arg)):
            die(f"the closing procedure this folder names is not there: {os.path.join(root, arg)}. Nothing was run.")
        print(f"closed with this folder's own routine: {arg}")
        print("That routine was reported done by the session, not checked by this script, which wrote nothing and did no git.")
        how = f"this folder's own routine ({arg}), reported done by the session, not checked"
    else:
        print(f"running this folder's closing routine: {arg}", flush=True)
        env = dict(os.environ, DESK_TOPIC=topic, DESK_TOPIC_FOLDER=folder, DESK_WORK=work, DESK_STEP="close")
        rc = subprocess.run(arg, shell=True, cwd=work if lv != "folder" else root, stdin=subprocess.DEVNULL, env=env).returncode
        if rc != 0:
            die(f"this folder's closing routine failed (exit {rc}). The Desk is not closed, and this script changed "
                "nothing. Fix what it reported; run it again only if that routine is safe to run twice.")
        print("closed with this folder's own routine. This script wrote nothing and did no git.")
        how = f"this folder's own routine ran and finished ({arg})"
    if lv != "folder" and os.path.isdir(work):
        _, dirty, _ = run(["git", "status", "--porcelain"], cwd=work)
        if dirty:  # saving is the routine's business (it owns the git steps); say it, never save for it
            print("warning: the working copy has files nobody saved; if the routine should have saved them, it did not:\n" +
                  "\n".join("    " + l for l in dirty.splitlines()[:8]))
        if not head_ready(work, cfg, "HEAD"):
            if mode == "run":  # Desks can see this one, so it is not a warning: the topic would be invisible to receive and digest
                print(f"NOT RECORDED as closed: the routine ran, but the branch head carries no `{trailer_of(cfg)}` line, so "
                      "`desk.py receive` and `digest` cannot see this topic as ready. Make the routine commit it, then run the close again.",
                      file=sys.stderr)
                return 8
            print(f"warning: the branch head carries no `{trailer_of(cfg)}` line, so `desk.py receive` and `digest` cannot see this topic as ready.")
    step = next_step(folder)
    if step:
        print(f"next step: {step}")
    closed_line(topic, how)
    return 0


def cmd_note(current, other, text):
    """Something about another topic came up. Leave it where that topic's next session finds it.

    It is written inside the open desk's own working copy, one small file per
    note, so no second branch is created and two sessions that both leave a
    note for the same topic can never collide when they are merged.
    """
    current, other = slug(current), slug(other)
    if not text.strip():
        die("say what came up", 2)
    root, is_git = main_root()
    cfg = settings(root)
    droot = cfg.get("desk root", "desks/").strip("/")
    lv = level(root, is_git, cfg)
    omode, oarg = open_mode(cfg)
    if omode == "follow":
        # The session works where the folder's opener put it, not in a copy Desks made.
        work = house_work()
        if not os.path.isdir(os.path.join(work, droot)):
            die(f"this folder keeps its topics its own way (`Open: house follow {oarg}`), and {work} has no "
                f"{droot}/ to leave a note in. Leave it the way {oarg} says. Nothing was written.")
    else:
        work = root if lv == "folder" else topic_work(root, cfg, current)[0]
    if not work:
        die(f"no open desk named {current}")
    inbox = os.path.join(work, droot, other, "inbox")
    if lv != "folder" and ignored(work, os.path.relpath(os.path.join(inbox, "x.md"), work)):
        die(f"{inbox} is ignored by git: a note left there would never reach {other}. Nothing was written (#25).")
    os.makedirs(inbox, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = os.path.join(inbox, f"{stamp}-from-{current}.md")
    open(path, "w", encoding="utf-8").write(f"From the desk `{current}`, {stamp[:10]}:\n\n{text.strip()}\n")
    print(f"noted for {other}: {path}")
    return 0


def cmd_set(key, value, append=False):
    """Record a setup answer as `- Key: value` in the Desk block of the main folder's CLAUDE.md.

    The block lives in the main folder, not in a topic's working copy, because
    every Desk reads it from there. When the file is under git it is saved by
    itself, so a later close never finds the main folder half-edited.
    """
    root, is_git = main_root()
    path = block_file(root)
    if not path:
        die("no Desk block in CLAUDE.md or CLAUDE.local.md of the main folder; run the install first")
    text = open(path, encoding="utf-8").read()
    m = BLOCK.search(text)
    name = os.path.basename(path)
    key, value = key.strip().rstrip(":"), value.strip()
    mode, arg = close_mode({"close": value}) if key.lower() == "close" else ("", "")
    if mode == "?":
        die(f"`Close: {value}` is not one this script understands. It reads `merge`, `review`, "
            "`house run <command>` or `house follow <file>`. Nothing was recorded.", 2)
    step = key.lower() if key.lower() in ("open", "review") else ""
    if step:  # the same forms for both steps (#28)
        om, oa = open_mode({"open": value})
        if om == "?":
            die(f"`{key.capitalize()}: {value}` is not one this script understands. It reads `house follow <file>`, `house run <command>` or `desks`. Nothing was recorded.", 2)
        if om == "follow" and not inside(root, oa):
            die(f"`{oa}` is outside this folder. An opening procedure is a file inside it. Nothing was recorded.", 2)
    if len(value.splitlines()) > 1:
        die("a setting is one line. Put a longer routine in a script and name the script. Nothing was recorded.", 2)
    if mode == "follow" and not inside(root, arg):
        die(f"`{arg}` is outside this folder. A closing procedure is a file inside it. Nothing was recorded.", 2)
    yes = confirmed_all() if key.lower() == "close" or step else None  # before anything is written
    body, line = m.group(2), f"- {key}: {value}"
    pat = re.compile(rf"^[ \t]*-[ \t]*{re.escape(key)}:.*$", flags=re.M | re.I)
    if pat.search(body) and not append:
        body = pat.sub(lambda _: line, body, count=1)
    elif line not in body:
        body = body.rstrip("\n") + "\n" + line + "\n"
    open(path, "w", encoding="utf-8").write(text[:m.start(2)] + body + text[m.end(2):])
    print(f"recorded in {path}: {line}")
    kind = mode if key.lower() == "close" else (open_mode({"open": value})[0] if step else "")
    which = "close" if key.lower() == "close" else step
    if kind in ("run", "follow"):  # the user's yes to this exact text, kept where a pull cannot reach it
        read_back = settings(root).get(which, "").strip()  # exactly what the step will read from the file
        confirm_close(root, read_back, yes, which)
        print(f"confirmed for this folder: {read_back}")
    elif yes is not None and which:  # the routine is no longer this folder's: an old yes must not come back with it
        confirm_close(root, "", yes, which)
    if is_git and run(["git", "ls-files", "--error-unmatch", name], cwd=root)[0] == 0:
        _, cur, _ = run(["git", "branch", "--show-current"], cwd=root)
        if is_off(settings(root), "git"):  # #56: with Git: off the folder's own routine saves, not Desks
            print(f"not saved to history: Git is off here. {name} changed in {root}; save it the folder's own way.")
        else:
            rc, _, err = run(["git", "commit", "--only", name, "-m", f"desk: record {key}"], cwd=root)
            print(f"saved to history on {cur or 'the checked-out branch'}" if rc == 0
                  else "not saved to history (" + (err.splitlines() or ["nothing to save"])[-1] + ")")
    return 0


# What a folder's own routines look like, in the words people name and describe them with (#53).
# Recall matters more than precision here: the session reads every candidate before proposing.
KINDS = {
    "open": r"\b(open|opens|start|starts|begin|new topic|worktree|abre|abrir|abrí|inicia|iniciar|nuevo)\b",
    "review": r"\b(review|reviews|reviewer|reviewers|gate|privacy|revisa|revisar|revisión|compuerta|privacidad)\b",
    "close": r"\b(close|closes|closing|closeout|wrap|wrap-up|hand ?off|handoff|cerrar|traspaso)\b",
}
READ_FIRST = re.compile(r"(read|lee|leer|lea)\b[^\n]{0,80}?`?\.?/?([\w./-]+\.md)`?[^\n]{0,40}?\b(first|primero|antes)\b", re.I)
SCRIPT_DIRS = ("Scripts", "scripts", "bin", "tools", "routines", "hooks")


def head_comment(path, n=12):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [next(f, "") for _ in range(n)]
    except OSError:
        return ""
    text = " ".join(l.strip().lstrip("#/;-* ").strip() for l in lines
                    if l.strip().startswith(("#", "//", ";", "--", '"""', "*")) and not l.startswith("#!"))
    return " ".join(text.split())


def scan(root):
    """The folder's own opening, review and closing routines, found without running anything."""
    rules = [f for f in ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md") if os.path.isfile(os.path.join(root, f))]
    first = []
    for f in rules:
        for m in READ_FIRST.finditer(open(os.path.join(root, f), encoding="utf-8", errors="replace").read()):
            rel = m.group(2).lstrip("./")
            if os.path.isfile(os.path.join(root, rel)) and rel not in first:
                first.append(rel)
    named = " ".join(open(os.path.join(root, f), encoding="utf-8", errors="replace").read() for f in first)
    found, seen = {k: [] for k in KINDS}, set()
    wanted = {d.lower() for d in SCRIPT_DIRS}
    for d in sorted(e for e in os.listdir(root) if e.lower() in wanted):  # the name as it is on disk
        top = os.path.join(root, d)
        if not os.path.isdir(top):
            continue
        ident = (os.stat(top).st_dev, os.stat(top).st_ino)  # Scripts/ and scripts/ are one folder on a case-blind disk
        if ident in seen:
            continue
        seen.add(ident)
        for name in sorted(os.listdir(top)):
            path = os.path.join(top, name)
            if not os.path.isfile(path) or name.startswith(("test_", "test-", ".")):
                continue
            rel = f"{d}/{name}"
            head = head_comment(path)
            words = name.replace("-", " ").replace("_", " ").rsplit(".", 1)[0]
            # The name counts three times the header; a script goes under the step it scores highest on.
            score = {k: 3 * len(re.findall(pat, words, re.I)) + len(re.findall(pat, head, re.I)) for k, pat in KINDS.items()}
            best = max(score.values())
            in_first = name in named
            for k in KINDS:
                if best and score[k] == best:
                    found[k].append((not in_first, -best, rel, head[:90]))
    for k in found:
        found[k] = [(a, r, h) for a, _, r, h in sorted(found[k])]
    return rules, first, found


def house_work():
    """Under `Open: house follow`, the working copy the folder's own opener made: where the session is."""
    top = run(["git", "rev-parse", "--show-toplevel"], cwd=os.getcwd())
    return top[1].strip() if top[0] == 0 else os.getcwd()


def cmd_get(key):
    """One recorded answer, as the scripts read it (#64: sessions kept reaching for this)."""
    root, _ = main_root()
    value = settings(root).get(key.strip().rstrip(":").lower(), "").strip()
    if not value:
        print(f"{key}: not recorded", file=sys.stderr)
        return 1
    print(value)
    return 0


def cmd_scan():
    root, _ = main_root()
    rules, first, found = scan(root)
    print("instructions: " + (", ".join(rules) or "none"))
    print("read first:   " + (", ".join(first) or "nothing the instructions name as read-first"))
    any_found = False
    for k in ("open", "review", "close"):
        rows = found[k]
        named = [r for r in rows if not r[0]]
        shown = named or rows[:3]
        if shown:
            any_found = True
        print(f"{k}:")
        for _, rel, head in shown:
            print(f"  {rel}" + ("  (named in " + ", ".join(first) + ")" if named else "") + (f"  -- {head}" if head else ""))
        if not shown:
            print("  nothing found")
        elif not named and len(rows) > 3:
            print(f"  and {len(rows) - 3} more by name only")
    if first and any_found:
        proc = first[0]
        print(f"suggest:      Open: house follow {proc} · Review: house follow {proc} · Close: house follow {proc}")
        print("              Read the procedure and each script's header before proposing them; record only on the user's yes.")
    elif any_found:
        print("suggest:      read each candidate's header; propose a line only for one that does that step for this folder.")
    else:
        print("suggest:      no routines of its own found: Desks' defaults fit (reference/setup.md).")
    return 0


def cmd_tidy():
    """Remove working copies whose branch is already merged. Never touches unmerged work."""
    root, is_git = main_root()
    if not is_git:
        return 0
    base = default_branch(root)
    run(["git", "fetch", "--quiet", "--prune"], cwd=root)
    _, merged, _ = run(["git", "branch", "--merged", base, "--format=%(refname:short)"], cwd=root)
    for b in [x for x in merged.splitlines() if x.startswith("desk/")]:
        w = worktree_of(root, b)
        if w and run(["git", "worktree", "remove", w], cwd=root)[0] != 0:
            print(f"kept {b}: its working copy has uncommitted files")
            continue
        run(["git", "branch", "-d", b], cwd=root)
        print(f"tidied {b}")
    return 0


# ---- receive, digest, children, migrate (0.3.0) -------------------------------------------

def desk_branches(root, cfg):
    pre = prefix_of(cfg)
    _, out, _ = run(["git", "for-each-ref", "--format=%(refname:short) %(objectname)", f"refs/heads/{pre}*"], cwd=root)
    return [tuple(l.split(" ", 1)) for l in out.splitlines() if " " in l]


def parent_of(root, branch):
    return run(["git", "config", f"branch.{branch}.deskparent"], cwd=root)[1]


def is_received(root, cfg, branch):
    target = receive_target(root, cfg, branch)
    if target is None:
        return False
    refs = [target] if parent_of(root, branch) else [target, base_ref(root, cfg)]
    return any(ref_exists(root, r) and is_ancestor(root, branch, r) for r in refs)


def ready_rows(root, cfg):
    """Topics whose branch head carries the ready trailer and is not yet in its target."""
    rows = []
    for b, sha in desk_branches(root, cfg):
        if head_ready(root, cfg, b) and not is_received(root, cfg, b):
            rows.append({"topic": topic_of_branch(cfg, b), "branch": b, "sha": sha, "target": receive_target(root, cfg, b)})
    return rows


def state_names(root, kind):
    d = os.path.join(git_dir(root), "desk-state", kind)
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def state_text(root, kind, name):
    try:
        return open(os.path.join(git_dir(root), "desk-state", kind, name), encoding="utf-8").read().strip()
    except OSError:
        return ""


def child_rows(root, cfg):
    rows = []
    for b, sha in desk_branches(root, cfg):
        parent = parent_of(root, b)
        if not parent:
            continue
        state = ("received" if is_received(root, cfg, b) else "ready") if head_ready(root, cfg, b) else "running"
        rows.append({"topic": topic_of_branch(cfg, b), "parent": parent, "state": state, "branch": b})
    return rows


def escalation_reasons(root, cfg, topic, sha, target):
    """Why this topic may not be taken in by the script alone. Computed from git and the rules file,
    never from what the close note claims about itself. No `Escalate:` line, no rules."""
    spec = cfg.get("escalate", "").strip()
    if not spec:
        return []
    path = os.path.join(root, spec)
    if not inside(root, spec) or not os.path.isfile(path):
        return [f"the rules file `{spec}` named in `Escalate:` is not there (the answer is escalate, not skip)"]
    _, names, _ = run(["git", "diff", "--name-only", f"{target}...{sha}"], cwd=root)
    changed = [n for n in names.splitlines() if n]
    _, num, _ = run(["git", "diff", "--numstat", f"{target}...{sha}"], cwd=root)
    size = sum(int(a) + int(b) for a, b, *_ in (l.split("\t") for l in num.splitlines()) if a.isdigit() and b.isdigit())
    droot = cfg.get("desk root", "desks/").strip("/")
    sdir = sessions_dir("", cfg, topic, droot)
    _, listing, _ = run(["git", "ls-tree", "-r", "--name-only", sha, "--", sdir], cwd=root)
    notes = sorted(n for n in listing.splitlines() if n.endswith(".md"))
    note = run(["git", "show", f"{sha}:{notes[-1]}"], cwd=root)[1] if notes else ""
    own = (f"{droot}/{topic}/", sdir + "/")
    out, ruled = [], 0
    for raw in open(path, encoding="utf-8").read().splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        kind, _, rest = raw.partition("\t")
        val = rest.split("\t")[0].strip()
        kind = kind.strip().lower()
        ruled += 1
        if kind in ("path", "doctrine"):
            if not val:
                out.append(f"the {kind} rule has no pattern (the answer is escalate, not skip)")
            for n in changed:
                if val and fnmatch.fnmatch(n, val):
                    out.append(f"{n} matches {kind} rule `{val}`")
        elif kind == "max-lines":
            if not val.isdigit():
                out.append(f"the max-lines rule has no number: `{val}` (the answer is escalate, not skip)")
            elif size > int(val):
                out.append(f"the diff is {size} lines, over the limit of {val}")
        elif kind == "undeclared":
            body = section_body(note, "Files")
            declared = {re.sub(r"^[-*]\s*`?([^`\s]+)`?.*$", r"\1", l.strip()) for l in body.splitlines() if l.strip().startswith(("-", "*"))}
            if not body:
                out.append("the close note declares no files (a section 'Files' listing what was touched)")
            else:
                extra = [n for n in changed if n not in declared and not n.startswith(own)]
                if extra:
                    out.append(f"the diff touches {len(extra)} file(s) the close note does not declare, e.g. {extra[0]}")
        elif kind == "anomalies":
            if not val.isdigit():
                out.append(f"the anomalies rule has no number: `{val}` (the answer is escalate, not skip)")
                continue
            rows = [l for l in (section_body(note, "Anomalies") or section_body(note, "Anomaly")).splitlines()
                    if l.strip().startswith(("-", "*", "|")) and not re.match(r"^[|\s:-]+$", l)
                    and not re.search(r"\bnone\b", l, re.I)]  # the whole word: "nonexistent file" is an anomaly
            rows = [l for l in rows if not re.match(r"^\|\s*(what|anomaly|row)\b", l, re.I)]
            if len(rows) >= int(val):
                out.append(f"the close note reports {len(rows)} anomaly row(s)")
        else:
            out.append(f"the rules file has a rule this script does not know: `{kind}` (the answer is escalate, not skip)")
    if not ruled:
        out.append(f"the rules file `{spec}` has no rules (the answer is escalate, not skip)")
    return out


def differed_rows(note):
    """The rows of the close note's table of where Desks did something other than the folder's routines."""
    rows = []
    for l in section_body(note, "Where Desks differed").splitlines():
        l = l.strip()
        if l.startswith("|") and not re.match(r"^[|\s:-]+$", l) and not re.match(r"^\|\s*(what|where|difference)\b", l, re.I) and "{{" not in l:
            rows.append(l)
    return rows


def cmd_receive(topic, ok_reason="", expect=""):
    root, is_git = main_root()
    cfg = settings(root)
    if not is_git:
        die("receive works on git folders: the branches are the list")
    rows = ready_rows(root, cfg)
    if not topic:
        if not rows:
            print("nothing ready to receive")
            return 2
        for r in rows:
            print(f"ready: {r['topic']}  {r['sha'][:12]}  -> {r['target'] or '(parent gone)'}")
        return 0
    topic = slug(topic)
    mine = [r for r in rows if r["topic"] == topic]
    if not mine:
        print(f"nothing ready for {topic}: no branch head carries `{trailer_of(cfg)}` that is not already received")
        return 2
    r = mine[0]
    if expect and not r["sha"].startswith(expect):
        return blocked(root, topic, f"the head is {r['sha'][:12]}, not the {expect} that was checked")
    reasons = escalation_reasons(root, cfg, topic, r["sha"], r["target"]) if r["target"] else []
    if reasons and not ok_reason:
        d = state_dir(root, "escalations")
        open(os.path.join(d, topic), "w", encoding="utf-8").write("\n".join(reasons) + "\n")
        print(f"ESCALATE {topic} at {r['sha'][:12]}: not taken in by the script alone:")
        for x in reasons:
            print("  - " + x)
        print(f"A reader who decides it may run: desk.py receive {topic} --escalated-ok \"<why>\" --head {r['sha'][:12]}")
        return 4
    target = r["target"]
    if target is None:
        return blocked(root, topic, "its parent topic's branch is gone, so there is nothing to take it into; reopen the parent or re-parent it by hand")
    if not ref_exists(root, target):
        return blocked(root, topic, f"the target `{target}` does not exist")
    tsha = run(["git", "rev-parse", target], cwd=root)[1]
    tw = worktree_of(root, target)
    if tw and run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=tw)[1]:
        return blocked(root, topic, f"the working copy of {target} at {tw} has uncommitted changes")
    droot = cfg.get("desk root", "desks/").strip("/")
    tmp = tempfile.mkdtemp(prefix="desk-receive-")
    wt, tb = os.path.join(tmp, "wt"), f"receive-tmp/{topic}"
    env = dict(os.environ, DESK_TOPIC=topic, DESK_BRANCH=r["branch"], DESK_SHA=r["sha"], DESK_TARGET=target, DESK_STEP="receive")
    why = ""
    new = ""
    try:
        run(["git", "branch", "-D", tb], cwd=root)
        if run(["git", "worktree", "add", "-q", "-b", tb, wt, tsha], cwd=root)[0] != 0:
            return blocked(root, topic, "could not make the scratch copy to merge in")
        cmd = cfg.get("receive merge", "").strip()
        if cmd:
            rc = subprocess.run(cmd, shell=True, cwd=wt, env=env, stdin=subprocess.DEVNULL).returncode
            if rc == 0 and run(["git", "merge-base", "--is-ancestor", r["sha"], "HEAD"], cwd=wt)[0] != 0:
                rc = 1
                why = "the merge command finished but the topic is not in the result"
        else:
            suffix = f" ({ok_reason})" if ok_reason else ""
            rc = run(["git", "merge", "--no-ff", "-q", "-m", f"desk: receive {topic}{suffix}", r["sha"]], cwd=wt)[0]
            if rc != 0:
                run(["git", "merge", "--abort"], cwd=wt)
        if rc != 0:
            why = why or "the merge did not complete"
        else:
            log = cfg.get("differed log", "").strip()
            _, listing, _ = run(["git", "ls-tree", "-r", "--name-only", r["sha"], "--", sessions_dir("", cfg, topic, droot)], cwd=root)
            notes = sorted(n for n in listing.splitlines() if n.endswith(".md"))
            diffs = differed_rows(run(["git", "show", f"{r['sha']}:{notes[-1]}"], cwd=root)[1]) if notes else []
            if log and diffs and inside(wt, log):
                lp = os.path.join(wt, log)
                os.makedirs(os.path.dirname(lp), exist_ok=True)
                head = "" if os.path.exists(lp) else "# Where Desks differed\n\n| date | topic | what | folder's routine | Desks |\n|---|---|---|---|---|\n"
                with open(lp, "a", encoding="utf-8") as f:
                    f.write(head + "".join(f"| {datetime.date.today().isoformat()} | {topic} {d}\n" for d in diffs))
                run(["git", "add", log], cwd=wt)
                run(["git", "commit", "-q", "-m", f"desk: where Desks differed ({topic})"], cwd=wt)
            checks = cfg.get("receive checks", "").strip()
            if checks:
                crc = subprocess.run(checks, shell=True, cwd=wt, env=env, stdin=subprocess.DEVNULL).returncode
                if crc != 0:
                    why = f"the declared checks failed (exit {crc})"
            if not why:
                new = run(["git", "rev-parse", "HEAD"], cwd=wt)[1]
                if run(["git", "rev-parse", target], cwd=root)[1] != tsha:
                    why = f"{target} moved while the checks ran"
        if not why:
            moved = run(["git", "merge", "--ff-only", "-q", new], cwd=tw)[0] == 0 if tw else \
                run(["git", "update-ref", f"refs/heads/{target}", new, tsha], cwd=root)[0] == 0
            if not moved:
                why = f"{target} could not be advanced"
    finally:
        run(["git", "worktree", "remove", "--force", wt], cwd=root)
        run(["git", "branch", "-D", tb], cwd=root)
        shutil.rmtree(tmp, ignore_errors=True)
    if why:
        return blocked(root, topic, why)
    w = worktree_of(root, r["branch"])
    if w and not run(["git", "status", "--porcelain"], cwd=w)[1]:
        run(["git", "worktree", "remove", w], cwd=root)
    elif w:
        print(f"kept the working copy {w}: it has uncommitted files")
    run(["git", "branch", "-d", r["branch"]], cwd=root)
    for kind in ("blocked", "escalations"):
        try:
            os.unlink(os.path.join(git_dir(root), "desk-state", kind, topic))
        except OSError:
            pass
    print(f"received {topic} into {target} at {new[:12]}. Nothing was pushed.")
    return 0


def blocked(root, topic, why):
    open(os.path.join(state_dir(root, "blocked"), topic), "w", encoding="utf-8").write(why + "\n")
    print(f"BLOCKED {topic}: {why}. The topic's working copy, branch and trailer are untouched; `desk.py digest` shows it as blocked.")
    return 3


def cmd_children(topic):
    root, _ = main_root()
    cfg = settings(root)
    topic = slug(topic) if topic else current_topic(cfg)
    rows = [c for c in child_rows(root, cfg) if not topic or c["parent"] == topic]
    for c in rows:
        print(f"{c['topic']}  {c['state']}  (child of {c['parent']}, branch {c['branch']})")
    if not rows:
        print("no children")
    return 0


def digest_data(root, cfg, fetch):
    here = house_work()
    _, branch, _ = run(["git", "branch", "--show-current"], cwd=here)
    maint = cfg.get("maintainer prefix", "").strip()
    topic = topic_of_branch(cfg, branch)
    lane = "maintainer" if maint and branch.startswith(maint) else (f"desk {topic}" if topic else "main folder")
    base = base_ref(root, cfg)
    if fetch:
        fetch_base(root, base)
    behind = None
    if ref_exists(root, base):
        _, n, _ = run(["git", "rev-list", "--count", f"HEAD..{base}"], cwd=here)
        behind = int(n) if n.isdigit() else None
    return {"lane": lane, "branch": branch, "working copy": here, "head": run(["git", "rev-parse", "--short=12", "HEAD"], cwd=here)[1],
            "base": base, "behind": behind,
            "ready": [f"{r['topic']} {r['sha'][:12]}" for r in ready_rows(root, cfg)],
            "blocked": [f"{n}: {state_text(root, 'blocked', n)}" for n in state_names(root, "blocked")],
            "escalations": [f"{n}: {(state_text(root, 'escalations', n).splitlines() or [''])[0]}" for n in state_names(root, "escalations")],
            "children": [f"{c['topic']} {c['state']} (of {c['parent']})" for c in child_rows(root, cfg) if c["state"] != "received"]}


def digest_code(d):
    if d["escalations"]:
        return 4
    if d["blocked"]:
        return 3
    if d["behind"]:
        return 5
    return 2 if d["ready"] else 0


def cmd_digest(fetch=False, freeze="", nxt="", compare=""):
    root, is_git = main_root()
    if not is_git:
        die("digest reads branches: this is not a git folder", 2)
    cfg = settings(root)
    d = digest_data(root, cfg, fetch)
    none = lambda xs: "; ".join(xs) if xs else "none"
    print(f"lane: {d['lane']}")
    print(f"branch: {d['branch'] or '(none)'}")
    print(f"working copy: {d['working copy']}")
    print(f"head: {d['head']}")
    print(f"base: {d['base']} · " + ("not found" if d["behind"] is None else ("current" if d["behind"] == 0 else f"STALE: this working copy is {d['behind']} commit(s) behind it")))
    print(f"ready, not received: {none(d['ready'])}")
    print(f"blocked: {none(d['blocked'])}")
    print(f"escalations open: {none(d['escalations'])}")
    print(f"children not received: {none(d['children'])}")
    code = digest_code(d)
    print(f"exit: {code}  (0 nothing waiting · 2 ready topics waiting · 3 a blocked topic · 4 an open escalation · 5 base stale)")
    if freeze:
        running = [c for c in d["children"] if " running " in c]
        if running or not nxt.strip():
            print("NOT FROZEN: " + ("children are still running: " + "; ".join(running) if running else "give the one next step with --next"), file=sys.stderr)
            return 6
        keep = {k: d[k] for k in ("lane", "base", "ready", "blocked", "escalations", "children")}
        keep["next"] = nxt.strip()
        with open(freeze, "w", encoding="utf-8") as f:
            json.dump(keep, f, indent=1, sort_keys=True)
        print(f"frozen state written: {freeze}")
    if compare:
        try:
            was = json.load(open(compare, encoding="utf-8"))
        except (OSError, ValueError):
            die(f"{compare} cannot be read as a frozen state", 2)
        diffs = [f"{k}: frozen {was.get(k)!r}, now {d.get(k)!r}" for k in ("lane", "base", "ready", "blocked", "escalations", "children") if was.get(k) != d.get(k)]
        print("frozen next step: " + str(was.get("next", "")))
        if diffs:
            print("DIFFERS from the frozen state:\n  " + "\n  ".join(diffs))
            return 1
        print("matches the frozen state")
        return 0
    return code


def cmd_migrate(topic):
    """Copy the state a topic left in the main folder, where no branch holds it, into the topic's working copy."""
    topic = slug(topic)
    root, is_git = main_root()
    cfg = settings(root)
    if not is_git:
        die("migrate is for git folders")
    work, _ = topic_work(root, cfg, topic)
    if not work:
        die(f"no open desk named {topic}: open it first, then migrate")
    droot = cfg.get("desk root", "desks/").strip("/")
    src = os.path.join(root, droot, topic)
    if not os.path.isdir(src):
        print("nothing to migrate")
        return 0
    moved = 0
    for rel in holds_state(src, root):
        rel = rel.split(" (")[0]
        s, d = os.path.join(root, rel), os.path.join(work, rel)
        if os.path.exists(d):
            print(f"kept (already in the working copy): {rel}")
            continue
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)
        moved += 1
        print(f"copied: {rel}")
    print(f"{moved} file(s) copied into {work}. Commit them there; delete the originals once the topic is received.")
    return 0


def cmd_remove(yes):
    """Take Desks out: the skill folder, the three `desk-*.md` agents and the marked block. Nothing else.

    The user's records (the Desk root and every session note in it), the transcript archive
    (`Transcripts:`), the review key and private terms in `~/.config/desk/` are theirs: this never
    reads those paths to delete them, and says that they stay. Without `--yes` it only lists."""
    skill = os.path.dirname(HERE)
    dest = os.path.dirname(os.path.dirname(skill))
    root, _ = main_root()
    cfg = settings(root)
    bf = block_file(root)
    gone = [skill] + sorted(os.path.join(dest, "agents", n) for n in (os.listdir(os.path.join(dest, "agents")) if os.path.isdir(os.path.join(dest, "agents")) else [])
                            if n.startswith("desk-") and n.endswith(".md"))
    print("would remove:" if not yes else "removing:")
    for g in gone:
        print("  " + g)
    if bf:
        print(f"  the marked Desk block in {bf}")
    print("stays, because it is yours: the Desk root " + os.path.join(root, cfg.get("desk root", "desks/").strip("/")) +
          (", the transcript archive " + os.path.expanduser(cfg["transcripts"]) if cfg.get("transcripts", "").strip() and not is_off(cfg, "transcripts") else "") +
          ", ~/.config/desk/. The records are plain Markdown; any other tool reads them.")
    if not yes:
        print("Nothing was removed. Run it again with --yes once the user has said yes.")
        return 0
    for g in gone:
        if os.path.islink(g) or os.path.isfile(g):
            os.unlink(g)
        else:
            shutil.rmtree(g, ignore_errors=True)
    if bf:
        with open(bf, encoding="utf-8") as f:
            text = f.read()
        with open(bf, "w", encoding="utf-8") as f:
            f.write(re.sub(r"\n*" + BLOCK.pattern + r"\n*", "\n\n", text, flags=re.S).strip("\n") + "\n")
    return 0


def flag(a, name, takes=False):
    """(present, value) for `--name [value]`; the pair is removed from `a`."""
    if name not in a:
        return False, ""
    i = a.index(name)
    val = a[i + 1] if takes and i + 1 < len(a) else ""
    del a[i:i + (2 if takes else 1)]
    return True, val


def main(a):
    a = list(a)
    if len(a) >= 2 and a[1] in ("-h", "--help", "help"):  # asking for help is not an error (#50)
        print(__doc__)
        return 0
    cmd = a[1] if len(a) > 1 else ""
    if cmd == "status":
        return cmd_status()
    if cmd == "open" and len(a) >= 3:
        rest = a[2:]
        reopen, _ = flag(rest, "--reopen")
        _, parent = flag(rest, "--parent", True)
        return cmd_open(" ".join(rest), reopen, parent or None)
    if cmd == "close":
        rest = a[2:]
        _, title = flag(rest, "--title", True)
        merge, _ = flag(rest, "--merge")
        pr, _ = flag(rest, "--pr")
        if len(rest) > 1 or (merge and pr):
            print(__doc__, file=sys.stderr)
            return 2
        return cmd_close(rest[0] if rest else "", "--merge" if merge else ("--pr" if pr else ""), title)
    if cmd == "receive":
        rest = a[2:]
        _, ok = flag(rest, "--escalated-ok", True)
        _, head = flag(rest, "--head", True)
        return cmd_receive(rest[0] if rest else "", ok, head)
    if cmd == "digest":
        rest = a[2:]
        fetch, _ = flag(rest, "--fetch")
        _, freeze = flag(rest, "--freeze", True)
        _, nxt = flag(rest, "--next", True)
        _, compare = flag(rest, "--compare", True)
        return cmd_digest(fetch, freeze, nxt, compare)
    if cmd == "children":
        return cmd_children(a[2] if len(a) > 2 else "")
    if cmd == "migrate" and len(a) >= 3:
        return cmd_migrate(a[2])
    if cmd in ("set", "add") and len(a) >= 4:
        return cmd_set(a[2], " ".join(a[3:]), append=(cmd == "add"))
    if cmd == "note" and len(a) >= 5:
        return cmd_note(a[2], a[3], " ".join(a[4:]))
    if cmd == "get" and len(a) >= 3:
        return cmd_get(" ".join(a[2:]))
    if cmd == "scan":
        return cmd_scan()
    if cmd == "tidy":
        return cmd_tidy()
    if cmd == "remove":
        return cmd_remove("--yes" in a[2:])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
