#!/usr/bin/env python3
"""The plumbing under a Desk, so the session never improvises git.

    python3 desk.py status
    python3 desk.py open  <topic>
    python3 desk.py close <topic> --merge | --pr [--title "Five Words At Most"]
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
    notes = sorted(f for f in os.listdir(os.path.join(folder, "sessions")) if f.endswith(".md")) if os.path.isdir(os.path.join(folder, "sessions")) else []
    if not notes:
        die("no session note yet: write sessions/<date>-<title>.md from the template first")
    for f in [os.path.join(folder, "README.md"), os.path.join(folder, "sessions", notes[-1])]:
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
    if len(a) >= 2 and a[1] == "tidy":
        return cmd_tidy()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
