# A Desk in a cloud session

Claude Code can run a session on a cloud machine instead of the user's own (Claude Code on the
web, or a session started from the phone or desktop app in the cloud). `desk.py` and
`providers.py` notice it by themselves (`CLAUDE_CODE_REMOTE=true`; `DESK_CLOUD=1` or `0` overrides).
What changes is that the machine is not the user's, starts from a fresh copy of the repository,
and is thrown away after the session. Everything below follows from that.

## What works, what is reduced, what is off

| Part | On the user's machine | In a cloud session |
|---|---|---|
| The skill and the three workers | `.claude/` of the folder, `~/.claude/`, or the plugin | **Works** when installed in the repository's `.claude/` (committed) or as a plugin. An install in `~/.claude/` is not on the cloud machine. |
| The Desk block | `CLAUDE.md` or `CLAUDE.local.md` | **Works** from a committed `CLAUDE.md`. `CLAUDE.local.md` is not in the repository, so it is not there: the defaults apply. |
| Opening a topic (`git` level) | Its own branch `desk/<topic>` in its own working copy | **Changed:** the topic lives on the session's own branch, in the checkout itself. Only that branch can be pushed, and a second working copy would be lost with the machine. |
| Closing | Merge into the main branch, or a pull request | **Changed:** all saved and pushed on the session's branch, or the close refuses. Its pull request is where it is reviewed and merged. A `Close: merge` or `review` line is for the user's machine and is not used. |
| `github` level, pull requests from `desk.py` | `gh` logged in | **Off in `desk.py`:** `gh` is usually not logged in. The session opens the pull request with its own GitHub tools. |
| A folder's own close (`Close: house …`) | Confirmed once, remembered in `~/.config/desk/` | **Reduced:** the confirmation is not kept between sessions, so the close asks for the user's yes again. A command that needs the user's machine fails and the Desk is not closed. |
| Review key for OpenRouter | `~/.config/desk/openrouter.key`, `OPENROUTER_API_KEY`, or the dashboard | **Works** from the environment's settings: a network secret for openrouter.ai with `DESK_REVIEW_KEY=proxy` (the session never sees the key), or the variable `OPENROUTER_API_KEY`. The key file is not there. |
| Endpoints (a shared model, your own, an Apple Intelligence gateway) | Dashboard: `providers.py serve` | **Works** from variables: `DESK_ENDPOINT_<NAME>_URL`, `_MODEL`, `_KEY` (or `proxy`), `_LANE`. The host must be allowed in the environment's network access. A model on the user's own computer is reachable only through a gateway with a public address. |
| Your own command lanes (`reviewers.txt`) | Any installed command | **Off** unless the file and the command are on the cloud machine; the dashboard says which. |
| Apple Intelligence through a macOS Shortcut | Mac only | **Off, explicitly:** there is no Mac. A gateway endpoint declared with `_LANE=private` takes its place, with the same two-code check. |
| Private terms | `~/.config/desk/private-terms.txt` | **Works** from the variable `DESK_PRIVATE_TERMS`, terms separated by `;`. Without it, names are not checked, and the review says so. |
| Profile (`Profile:` line) | Any path, often outside the folder | **Reduced:** only a profile inside the repository is there. Keep a private profile out of a public repository. |
| Same-vendor pass | A `desk-reader` subagent | **Works.** |
| `desk-screen`, browsers, computer use, phone simulator | The user's browser and screen | **Reduced:** no logged-in browser and no screen of the user's; reading public pages works where the network allows. Say what is missing and continue (`reference/surfaces.md`). |
| Phone, Remote Control | A switch the user turns | **Not needed:** a cloud session is already reachable from the app. |
| History and transcripts | Kept on the machine | **Gone with the machine:** only what is pushed survives. Commit by path and push at each milestone, not only at the close. |
| Dashboard | `providers.py`, `providers.py serve` to edit | **Works** as text or a page to show (`providers.py html <file>`). Nobody can open a page served on the cloud machine, so the edits are the steps it prints, done in the environment's settings. |

## Moving keys from a machine to a cloud environment

On the machine that has the keys, `python3 <skill folder>/scripts/providers.py export` lists each
key it finds, by name and where it came from, never its value, and the exact steps to load it into
the cloud environment's settings. With `--env-file <path>` it also writes the values to a file
outside any repository, readable by the user only, to paste from and then delete. Loading them is
the user's step (`[needs you: access]`): there is no tool that changes those settings for them.
