# Exit codes, per command

A number means one thing inside one command and another in the next: read it against the command that
printed it. Every refusal prints `STOP: <reason>` on stderr and says whether anything was changed.
Any command that is given something it does not understand exits 2 and prints its usage.

| Command | Code | Meaning |
|---|---|---|
| `open` | 0 | opened, continued or reattached |
| | 1 | refused (a path git ignores, an unreadable setting, a failed opener); nothing was opened |
| | 3 | no `Base:` to cut from; nothing was opened |
| | 4 | the topic was already received: open `<topic>-2` instead |
| | 5 | the topic was closed as ready and not yet received: needs `--reopen` and the user's yes |
| | 6 | another open holds a live lock; wait and run it again |
| | 7 | the child would be deeper than `Depth cap:` |
| `close` | 0 | closed (the `Closed line:` is printed) |
| | 1 | refused: placeholders, a note missing sections or lessons without a destination, a label without a receipt that checks out, unsaved files, the wrong branch, the main folder not on the base, a failed merge or routine; the Desk is not closed |
| | 2 | no topic or no `Close:` line recorded |
| | 8 | `Close: house run` finished but left no ready trailer on the branch head: not recorded as closed |
| `receive` | 0 | the topic was taken in (or, with no topic, the ready ones are listed) |
| | 2 | nothing ready |
| | 3 | blocked: the merge, the checks or the target failed; working copy, branch and trailer are untouched |
| | 4 | escalation: a reader must decide (`--escalated-ok "<why>" --head <sha>`); this includes a rules file that is missing, empty, or has a rule or option Desks does not know |
| `digest` | 0 | nothing waiting |
| | 2 | ready topics waiting (also: not a git folder) |
| | 3 | a blocked topic |
| | 4 | an open escalation |
| | 5 | the base is ahead of this working copy |
| | 6 | `--freeze` refused: a child is still running, or no `--next` was given |
| | 1 | `--compare`: the state differs from the frozen one |
| `get` | 1 | no such answer recorded |
| `remove` | 0 | listed, or removed with `--yes`; records and the transcript archive are never touched |
| `review.py` | 0 | enough families answered; the label stays `[open]` until every finding has a disposition |
| | 1 | the packet was refused by the gate or the built-in scan, or no private lane can take it; `--verify`: no receipt, a stale packet, or a receipt outside its packet's review folder |
| | 2 | usage, or the packet file is missing |
| | 3 | no key and no other lane |
| | 4 | nobody answered |
| | 5 | not sent: the folder reviews its own way, or its Desk block cannot be read |
| | 6 | fewer families answered than wanted, or only the private lane (`[thin]`) |
| | 7 | a background run was stopped by its watchdog |

**`--alongside` is self-declared.** `review.py --alongside` tells the script that the folder's own review
routine started it as a second opinion, which lets it run in a folder that says `Review: house ...`.
Any caller can pass it; nothing proves it. It is a courtesy, not a security check, and the privacy gate does
not depend on it: the gate runs either way.
