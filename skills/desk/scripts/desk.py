#!/usr/bin/env python3
"""The plumbing under a Desk, so the session never improvises git.

    python3 desk.py status
    python3 desk.py open  <topic>
    python3 desk.py close <topic> --merge | --pr [--title "Five Words At Most"]
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
import os
import re
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


def settings(root):
    """Lines like `- Desk root: desks/` inside the marked block of CLAUDE.md."""
    out = {}
    try:
        text = open(os.path.join(root, "CLAUDE.md"), encoding="utf-8").read()
    except OSError:
        return out
    m = re.search(r"<!-- desk:start -->(.*?)<!-- desk:end -->", text, flags=re.S)
    for line in (m.group(1) if m else "").splitlines():
        k = re.match(r"\s*-\s*([A-Za-z ]+):\s*`?([^`\n]+?)`?\s*$", line)
        if k:
            out[k.group(1).strip().lower()] = k.group(2).strip()
    return out


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
    if not is_git or cfg.get("git", "").lower() == "off":
        return "folder"
    if run(["git", "rev-parse", "--verify", "--quiet", "HEAD"], cwd=root)[0] != 0:
        return "folder"  # a repository with no commit yet cannot branch
    remote, gh_ok, _ = github(root)
    return "github" if (remote and gh_ok and cfg.get("github", "").lower() != "off") else "git"


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
    check = [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith(".md")]
    check += [os.path.join(folder, "sessions", f) for f in notes]
    for f in check:
        left = re.findall(r"\{\{[^}]*\}\}", open(f, encoding="utf-8").read())
        if left:
            die(f"{f} still has unfilled placeholders: {', '.join(left[:4])}")
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
    path = os.path.join(root, "CLAUDE.md")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        die("no CLAUDE.md in the main folder; run the install first")
    m = re.search(r"(<!-- desk:start -->)(.*?)(<!-- desk:end -->)", text, flags=re.S)
    if not m:
        die("CLAUDE.md has no Desk block; run the install first")
    key, value = key.strip().rstrip(":"), value.strip()
    body, line = m.group(2), f"- {key}: {value}"
    pat = re.compile(rf"^[ \t]*-[ \t]*{re.escape(key)}:.*$", flags=re.M | re.I)
    if pat.search(body) and not append:
        body = pat.sub(line, body, count=1)
    elif line not in body:
        body = body.rstrip("\n") + "\n" + line + "\n"
    open(path, "w", encoding="utf-8").write(text[:m.start(2)] + body + text[m.end(2):])
    print(f"recorded in {path}: {line}")
    if is_git and run(["git", "ls-files", "--error-unmatch", "CLAUDE.md"], cwd=root)[0] == 0:
        rc, _, err = run(["git", "commit", "--only", "CLAUDE.md", "-m", f"desk: record {key}"], cwd=root)
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
    if len(a) >= 4 and a[1] == "close" and a[3] in ("--merge", "--pr"):
        title = a[a.index("--title") + 1] if "--title" in a and a.index("--title") + 1 < len(a) else ""
        return cmd_close(a[2], a[3], title)
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
