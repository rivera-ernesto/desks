---
description: Open a sub-desk from the current Desk - a child session with a brief, registered under this topic. Local or cloud, on a cheaper model by default.
---

Open a sub-desk for: $ARGUMENTS

This is the sub-desk step of the `desk` skill (SKILL.md § 8), not a second procedure. Do not
rebuild it by hand.

1. **Where.** If `$ARGUMENTS` is empty, ask for the task. You must be inside a Desk; if none is open, say
   so and offer `desk <topic>` first. Before starting a child, check the usage reserve from the host's
   reading (SKILL.md § 8) and `desk.py children` when a local topic exists. A cloud parent has no local
   topic: start the child with the host's tool and the brief as its prompt.
2. **Local or cloud, nothing else.**
   - *Cloud*: the task lives in a public repository that already exists and needs nothing from this
     machine. Pass `target: "cloud"` and the `repository` to the host's session-start tool.
   - *Local*: it needs the machine (`gh` to create repositories, keys, Apple apps, the folder's own
     files). This is the default when unsure.
   If the host has no session-start tool, run step 3 for a local child, then give the user the
   working-copy path and the one line to open it there.
3. **Name and register it (local).** Make the child's name a short slug of the task. Run `python3 <skill folder>/scripts/desk.py open <child> --parent <topic>`
   and fill `brief.md` (from `templates/brief.md` in the skill folder): the user's words verbatim, the goal in one sentence, what
   the child may touch, and how it ends. Start the session in the working copy it printed.
   If `open` says the folder opens topics its own way, follow that routine for the child and name it so
   its parent is plain (`<topic>--<child>`).
   **Cloud:** there is no local topic; write the same brief as the session's prompt and add one line
   under Open in this topic's README: `sub-desk <child> (cloud, <owner/repo>)`.
4. **Brief and model.** The prompt carries the task, the area, what "done" looks like, and only the
   minimum of the parent's context. It tells the child to open as a Desk (`/desk <child>`) and to end with
   the numbered list SKILL.md § 8 asks for. Use a Sonnet-class model by default. Keep the top model
   for work that needs altitude (design, people, strategy), and say why when you do.
   The child keeps every gate of the folder: creating a repository or anything money, public or outside
   waits for the user's word, and the brief says so.
   Tell the child to end its final message with `Archivable: yes/no` and why (SKILL.md § 8).
5. **Tell the user in one line:** the child's name, local or cloud, the model, and that you will send
   it later ideas on this topic.

The standing rules (the parent sends later ideas to the child with `SendMessage`; a cloud session cannot answer; a Desk may open a sub-desk on its own) are in SKILL.md § 8 and apply without this command.
