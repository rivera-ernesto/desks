#!/usr/bin/env python3
"""The plumbing under a Desk, so the session never improvises git.

    python3 desk.py status
    python3 desk.py open  <topic>
    python3 desk.py close <topic> --merge | --pr [--title "Five Words At Most"]
    python3 desk.py close <topic>              (the recorded `Close:` line decides)
    python3 desk.py note  <open-topic> <other-topic> "what came up, in a sentence or two"
    python3 desk.py set   "Close" "merge"      (records a setup answer in CLAUDE.md)
    python3 desk.py add   "Setup" "use my researcher agent for reading"   (adds a line, keeps earlier ones)
    python3 desk.py tidy

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
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

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


def open_mode(cfg):
    """How this folder opens a topic: ('', '') Desks itself · ('follow', file) the folder's own
    routine, which the session follows · ('?', the line) a line this script does not understand.
    There is no `run` form yet: the session reads the file and runs the opener it names (#28)."""
    raw = cfg.get("open", "").strip()
    if not raw:
        return "", ""
    m = re.match(r"house\s+follow\s+(.+)$", raw)
    if m:
        arg = m.group(1).strip()
        if len(arg) > 1 and arg[0] == arg[-1] == "`":
            arg = arg[1:-1].strip()
        if arg:
            return "follow", arg
    return "?", raw


def confirmed_file():
    conf = os.environ.get("DESK_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".config", "desk")
    return os.path.join(conf, "house-close.json")


def confirmed_close(root):
    """The house close the user said yes to for this folder, as recorded by `desk.py set`.

    It is kept outside the folder on purpose: a `Close: house ...` line can
    arrive with a clone or a pull, and nothing that arrives that way may run.
    """
    try:
        with open(confirmed_file(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return ""
    return data.get(os.path.realpath(root), "") if isinstance(data, dict) else ""


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


def confirm_close(root, line, data=None):
    """Record the user's yes for this folder, or forget it when `line` is empty."""
    data = confirmed_all() if data is None else data
    key, path = os.path.realpath(root), confirmed_file()
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


def seed(folder, topic):
    new = not os.path.exists(os.path.join(folder, "README.md"))
    os.makedirs(os.path.join(folder, "sessions"), exist_ok=True)
    os.makedirs(os.path.join(folder, "reviews"), exist_ok=True)
    if new:
        text = open(os.path.join(TEMPLATES, "README.md"), encoding="utf-8").read()
        open(os.path.join(folder, "README.md"), "w", encoding="utf-8").write(text.replace("{{topic}}", topic))
    dec = os.path.join(folder, "decisions.md")
    if not os.path.exists(dec):
        open(dec, "w", encoding="utf-8").write("# Decisions\n\nOne dated line each: what was decided, why, and what was ruled out.\n")
    return new


def cmd_status():
    root, is_git = main_root()
    cfg = settings(root)
    lv = level(root, is_git, cfg)
    print(f"folder:   {root}")
    print(f"level:    {lv}")
    print(f"desk root: {cfg.get('desk root', 'desks/')}")
    print(f"settings: {block_file(root) or 'none (defaults)'}")
    omode, oarg = open_mode(cfg)
    if omode:
        print("opens:    " + (f"with this folder's own routine (follow {oarg}); topics it keeps elsewhere are not listed"
                              if omode == "follow" else f"`Open: {oarg}` is not understood; open will stop"))
    if is_git:
        remote, gh_ok, vis = github(root)
        print(f"branch:   {default_branch(root)} (default)")
        print("github:   " + ("no GitHub remote" if not remote else ("gh not logged in" if not gh_ok else f"ready, repository is {vis or 'of unknown visibility'}")))
        _, out, _ = run(["git", "worktree", "list", "--porcelain"], cwd=root)
        open_topics = re.findall(r"branch refs/heads/desk/(.+)", out)
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
    print("python3:  ok")
    return 0


def cmd_open(topic):
    topic = slug(topic)
    root, is_git = main_root()
    cfg = settings(root)
    omode, oarg = open_mode(cfg)
    if omode == "?":
        die(f"`Open: {oarg}` is not one this script understands. It reads `house follow <file>`. Nothing was opened.", 2)
    if omode == "follow":  # the folder opens topics its own way; making a second home for the topic is the bug (#28)
        if not inside(root, oarg) or not os.path.isfile(os.path.join(root, oarg)):
            die(f"this folder opens topics with `{oarg}`, which is not there. Nothing was opened.")
        print(f"open:   this folder opens topics its own way: follow {oarg} for '{topic}', and work where it says.")
        print("        Desks made no topic folder, branch or working copy here.")
        return 0
    droot = cfg.get("desk root", "desks/").strip("/")
    lv = level(root, is_git, cfg)
    if lv == "folder":
        work = root
    else:
        branch = f"desk/{topic}"
        work = worktree_of(root, branch)
        if not work:
            work = os.path.join(root, ".claude", "worktrees", f"desk-{topic}")
            # keep working copies out of the user's commits without touching their .gitignore
            exclude = os.path.join(root, ".git", "info", "exclude")
            try:
                if ".claude/worktrees/" not in open(exclude, encoding="utf-8").read():
                    open(exclude, "a", encoding="utf-8").write("\n.claude/worktrees/\n")
            except OSError:
                pass
            exists = run(["git", "rev-parse", "--verify", "--quiet", branch], cwd=root)[0] == 0
            args = ["git", "worktree", "add", work, branch] if exists else \
                   ["git", "worktree", "add", "-b", branch, work, default_branch(root)]
            run(args, cwd=root, check=True)
    folder = os.path.join(work, droot, topic)
    new = seed(folder, topic)
    print(f"level:  {lv}")
    print(f"topic:  {topic} ({'new' if new else 'continued'})")
    print(f"work in: {folder}")
    inbox = os.path.join(folder, "inbox")
    left = sorted(os.listdir(inbox)) if os.path.isdir(inbox) else []
    if left:
        print(f"inbox:  {len(left)} note(s) left by other desks in {inbox}: fold each into the README, then delete it")
    if not new and "## Next step" not in open(os.path.join(folder, "README.md"), encoding="utf-8").read():
        print("readme: this README was here before Desks. Add the sections State, Next step, Open and What we learned to it; keep everything it already says")
    if lv != "folder":
        print(f"branch: desk/{topic}  ·  working copy: {work}")
        print(f"note:   files in {root} that were never committed are not in the working copy; read them from there by full path")
    return 0


def cmd_close(topic, how, title):
    topic = slug(topic)
    root, is_git = main_root()
    cfg = settings(root)
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
    branch = f"desk/{topic}"
    work = root if lv == "folder" else worktree_of(root, branch)
    if not work:
        die(f"no open desk named {topic}")
    folder = os.path.join(work, droot, topic)
    if not os.path.isfile(os.path.join(folder, "README.md")):
        die(f"there is no topic '{topic}' under {os.path.join(work, droot)}. Run this from the folder the session was opened on.")
    notes = sorted(f for f in os.listdir(os.path.join(folder, "sessions")) if f.endswith(".md")) if os.path.isdir(os.path.join(folder, "sessions")) else []
    if not notes:
        die("no session note yet: write sessions/<date>-<title>.md from the template first")
    if not open(os.path.join(folder, "README.md"), encoding="utf-8").read().strip():
        die(f"{os.path.join(folder, 'README.md')} is empty: the next session would start from nothing")
    check = [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith(".md")]
    check += [os.path.join(folder, "sessions", f) for f in notes]
    for f in check:
        left = re.findall(r"\{\{[^}]*\}\}", open(f, encoding="utf-8").read())
        if left:
            die(f"{f} still has unfilled placeholders: {', '.join(left[:4])}")
    if house:
        return close_house(root, topic, folder, notes[-1], mode, arg, cfg.get("close", "").strip())
    if lv == "folder":
        print("closed (folder level): nothing to merge. The README is the state.")
        return 0
    _, dirty, _ = run(["git", "status", "--porcelain"], cwd=work)
    if dirty:
        die("uncommitted files in the working copy. Commit the ones you wrote, by path:\n" + dirty)
    base = default_branch(root)
    title = title or f"{topic}: {notes[-1][:-3]}"
    if how == "--pr":
        if lv != "github":
            die("no GitHub remote with gh logged in; use --merge, or set GitHub up first")
        _, _, vis = github(root)
        if vis.upper() == "PUBLIC" and cfg.get("public pushes", "").lower() != "yes":
            die("this repository is PUBLIC. Pushing would publish the desk. That needs the user's word; "
                "record `- Public pushes: yes` in the CLAUDE.md block only if they say so.")
        run(["git", "push", "-u", "origin", branch], cwd=work, check=True)
        rc, out, err = run(["gh", "pr", "create", "--base", base, "--head", branch, "--title", title,
                            "--body-file", os.path.join(folder, "sessions", notes[-1])], cwd=work)
        if rc != 0 and "already exists" not in err:
            die("could not open the pull request:\n" + err)
        print("pull request: " + (out or err).splitlines()[-1])
        print("The working copy stays until the pull request is merged; then run `desk.py tidy`.")
        return 0
    _, cur, _ = run(["git", "branch", "--show-current"], cwd=root)
    _, main_dirty, _ = run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root)
    if cur != base or main_dirty:
        die(f"the main folder must be on {base} with no half-finished changes before merging (it is on {cur or 'no branch'}"
            f"{', with changes' if main_dirty else ''}). Nothing was changed.")
    rc, _, err = run(["git", "merge", "--no-ff", branch, "-m", f"desk {title}"], cwd=root)
    if rc != 0:
        run(["git", "merge", "--abort"], cwd=root)
        die("the merge had conflicts and was undone. Nothing was changed:\n" + err)
    run(["git", "worktree", "remove", work], cwd=root, check=True)
    run(["git", "branch", "-d", branch], cwd=root)
    _, sha, _ = run(["git", "rev-parse", "--short", "HEAD"], cwd=root)
    print(f"merged into {base} and tidied. The topic now lives in {os.path.join(root, droot, topic)}")
    print(f"to undo this whole desk later: git revert -m 1 {sha}")
    return 0


def close_house(root, topic, folder, note, mode, arg, line):
    """The folder has its own closing routine, so that routine is the close.

    This script writes nothing here and does no git: no merge, no push, no
    pull request. `run` executes the recorded command and stops if it fails.
    `follow` names a written procedure the session carries out itself; this
    script cannot see that, and says so instead of pretending to have checked.
    """
    was = confirmed_close(root)  # the whole value as it was read back when they said yes, not a tidied form of it
    if was != line:
        die("this folder's closing routine has not been confirmed by the user in this exact form:\n"
            f"    Close: {line}\n"
            + (f"The form they confirmed was:\n    Close: {was}\n" if was else "")
            + "Show them the line. Only on their yes, record it:\n"
            f"    desk.py set Close {shlex.quote(line)}\nNothing was run.")
    lines = [x for x in open(os.path.join(folder, "sessions", note), encoding="utf-8").read().splitlines() if x.strip()]
    if len(lines) > 20:
        print(f"note:   sessions/{note} is {len(lines)} lines. With a house close the session note only points at "
              "the folder's own record of the session; it does not retell it.")
    if mode == "follow":
        if not inside(root, arg):
            die(f"the closing procedure this folder names is outside it: {arg}. Nothing was run.")
        if not os.path.isfile(os.path.join(root, arg)):
            die(f"the closing procedure this folder names is not there: {os.path.join(root, arg)}. Nothing was run.")
        print(f"closed with this folder's own routine: {arg}")
        print("That routine was reported done by the session, not checked by this script, which wrote nothing and did no git.")
        return 0
    print(f"running this folder's closing routine: {arg}", flush=True)
    env = dict(os.environ, DESK_TOPIC=topic, DESK_TOPIC_FOLDER=folder)
    rc = subprocess.run(arg, shell=True, cwd=root, stdin=subprocess.DEVNULL, env=env).returncode
    if rc != 0:
        die(f"this folder's closing routine failed (exit {rc}). The Desk is not closed, and this script changed "
            "nothing. Fix what it reported; run it again only if that routine is safe to run twice.")
    print("closed with this folder's own routine. This script wrote nothing and did no git.")
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
        top = run(["git", "rev-parse", "--show-toplevel"], cwd=os.getcwd())
        work = top[1].strip() if top[0] == 0 else os.getcwd()
        if not os.path.isdir(os.path.join(work, droot)):
            die(f"this folder keeps its topics its own way (`Open: house follow {oarg}`), and {work} has no "
                f"{droot}/ to leave a note in. Leave it the way {oarg} says. Nothing was written.")
    else:
        work = root if lv == "folder" else worktree_of(root, f"desk/{current}")
    if not work:
        die(f"no open desk named {current}")
    inbox = os.path.join(work, droot, other, "inbox")
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
    if key.lower() == "open":
        om, oa = open_mode({"open": value})
        if om == "?":
            die(f"`Open: {value}` is not one this script understands. It reads `house follow <file>`. Nothing was recorded.", 2)
        if not inside(root, oa):
            die(f"`{oa}` is outside this folder. An opening procedure is a file inside it. Nothing was recorded.", 2)
    if len(value.splitlines()) > 1:
        die("a setting is one line. Put a longer routine in a script and name the script. Nothing was recorded.", 2)
    if mode == "follow" and not inside(root, arg):
        die(f"`{arg}` is outside this folder. A closing procedure is a file inside it. Nothing was recorded.", 2)
    yes = confirmed_all() if key.lower() == "close" else None  # before anything is written
    body, line = m.group(2), f"- {key}: {value}"
    pat = re.compile(rf"^[ \t]*-[ \t]*{re.escape(key)}:.*$", flags=re.M | re.I)
    if pat.search(body) and not append:
        body = pat.sub(lambda _: line, body, count=1)
    elif line not in body:
        body = body.rstrip("\n") + "\n" + line + "\n"
    open(path, "w", encoding="utf-8").write(text[:m.start(2)] + body + text[m.end(2):])
    print(f"recorded in {path}: {line}")
    if mode in ("run", "follow"):  # the user's yes to this exact text, kept where a pull cannot reach it
        read_back = settings(root).get("close", "").strip()  # exactly what a close will read from the file
        confirm_close(root, read_back, yes)
        print(f"confirmed for this folder: {read_back}")
    elif yes is not None:  # the routine is no longer this folder's close: an old yes must not come back with it
        confirm_close(root, "", yes)
    if is_git and run(["git", "ls-files", "--error-unmatch", name], cwd=root)[0] == 0:
        rc, _, err = run(["git", "commit", "--only", name, "-m", f"desk: record {key}"], cwd=root)
        print("saved to history" if rc == 0 else "not saved to history (" + (err.splitlines() or ["nothing to save"])[-1] + ")")
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


def main(a):
    if len(a) >= 2 and a[1] == "status":
        return cmd_status()
    if len(a) >= 3 and a[1] == "open":
        return cmd_open(" ".join(a[2:]))
    if len(a) >= 3 and a[1] == "close" and (len(a) == 3 or a[3] in ("--merge", "--pr", "--title")):
        title = a[a.index("--title") + 1] if "--title" in a and a.index("--title") + 1 < len(a) else ""
        how = a[3] if len(a) > 3 and a[3] in ("--merge", "--pr") else ""
        return cmd_close(a[2], how, title)
    if len(a) >= 4 and a[1] in ("set", "add"):
        return cmd_set(a[2], " ".join(a[3:]), append=(a[1] == "add"))
    if len(a) >= 5 and a[1] == "note":
        return cmd_note(a[2], a[3], " ".join(a[4:]))
    if len(a) >= 2 and a[1] == "tidy":
        return cmd_tidy()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
