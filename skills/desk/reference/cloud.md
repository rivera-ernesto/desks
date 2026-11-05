# A Desk in a cloud session

Claude Code can run a session on a cloud machine instead of the user's own (Claude Code on the
web, or a cloud session started from the desktop or phone app). `desk.py` notices it by itself
(`CLAUDE_CODE_REMOTE=true`; `DESK_CLOUD=1` or `0` overrides). The machine is not the user's, starts
from a fresh clone of the repository, and is thrown away after the session. Everything below
follows from that.

| Part | On the user's machine | In a cloud session |
|---|---|---|
| The skill and the three workers | The folder's `.claude/`, `~/.claude/`, or the plugin | **Works** only when installed in the repository's `.claude/` and committed. Neither `~/.claude/` nor a plugin installed on the user's machine, nor one the repository's settings turn on, is on the cloud machine. |
| The Desk block | `CLAUDE.md` or `CLAUDE.local.md` | **Works** from a committed `CLAUDE.md`. `CLAUDE.local.md` is not in the repository: the defaults apply. |
| Opening a topic (git levels) | Its own branch and working copy | **Changed:** the topic lives on the session's own branch, in the checkout. Only that branch can be pushed, and a second working copy would be lost with the machine. A child topic (`--parent`) is refused: open it as its own cloud session. |
| Closing | Merge into the base, or a pull request | **Changed:** the close checks that the topic is committed and the branch pushed, then prints the `Closed line:`. Nothing is merged. The session's pull request is where the work is reviewed. A recorded `Close: merge` or `review` is for the user's machine and is not used. |
| A folder's own close (`Close: house …`) | Confirmed once, remembered in `~/.config/desk/` | **Reduced:** the confirmation is not kept between sessions, so the close asks for the user's yes again. A command that needs the user's machine fails, and the Desk is not closed. |
| `gh` pull requests from `desk.py` | `gh` logged in | **Off:** `gh` is usually not logged in. The session opens the pull request with its own GitHub tools. |
| Review key | `~/.config/desk/openrouter.key` or `OPENROUTER_API_KEY` | **Works** from the environment's settings: a network secret for `openrouter.ai` (header `Authorization`, prefix `Bearer`), nothing more: with no key of its own the script finds the one the environment adds (`reference/setup.md`, Review key). `review.py --test` says whether it works. |
| Other providers, private terms, your own lanes | Files in `~/.config/desk/` | **Reduced:** the folder is empty on a fresh machine. Without a private-terms list names are not checked, and the review says so. |
| Apple's private lane | A macOS Shortcut | **Off:** there is no Mac. |
| Same-vendor pass | A `desk-reader` subagent | **Works** when the workers are installed as above. |
| Browser, screen, the user's logged-in accounts | The user's machine | **Off:** reading public pages works where the environment's network allows. Say what is missing and continue (`reference/surfaces.md`). |
| History and transcripts | Kept on the machine | **Gone with the machine:** only what is pushed survives. Commit by path and push at each milestone, not only at the close. |

## Two repositories attached (#106)

With two repositories attached, the session's project folder is their parent, so this repository's
`.claude/settings.json` hooks never load (the `CLAUDE.md` block does). Silently, a `respawn` plus `/clear`
reopens nothing and the Stop checks do not run. What Desks does about it:

- The Desk block tells the session to run `desk.py open` with no topic on a first message that names none:
  it uses the pending respawn marker once, or lists the topics.
- The SessionStart hook leaves a stamp each time it runs. In a cloud session `open` and `status` warn
  (`hooks unverified here`) when no stamp is newer than the machine's start. Locally there is never a warning.
- Optional root fix, in the environment's setup script: put the two hook entries of this repository's
  `.claude/settings.json` into `~/.claude/settings.json`, which loads wherever the project folder is.
  Parse the file, merge the `SessionStart` and `Stop` entries without dropping others, check the result still
  parses, then write it. Use the path of this checkout's `desk.py`, not a copy.
