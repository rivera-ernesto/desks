---
description: Open a sub-desk from the current Desk - a child session with a brief, registered under this topic. Local or cloud, on a cheaper model by default.
---

Open a sub-desk for: $ARGUMENTS

This is the sub-desk step of the `desk` skill (SKILL.md § 8), not a second procedure. Do not
rebuild it by hand.

1. **Where.** You must be inside a Desk. If none is open, say so and offer `desk <topic>` first.
   Check `desk.py children` and the usage reserve `desk.py open` prints before starting one.
2. **Local or cloud, nothing else.**
   - *Cloud*: the task lives in a public repository that already exists and needs nothing from this
     machine. Pass `target: "cloud"` and the `repository` to the host's session-start tool.
   - *Local*: it needs the machine (`gh` to create repositories, keys, Apple apps, the folder's own
     files). This is the default when unsure.
   If the host has no session-start tool, run step 3 for a local child, then give the user the
   working-copy path and the one line to open it there.
3. **Register it (local).** Run `python3 <skill folder>/scripts/desk.py open <child> --parent <topic>`
   and fill `brief.md` from its template: the user's words verbatim, the goal in one sentence, what
   the child may touch, and how it ends. Start the session in the working copy it printed.
   **Cloud:** there is no local topic; write the same brief as the session's prompt and add one line
   under Open in this topic's README: `sub-desk <child> (cloud, <owner/repo>)`.
4. **Brief and model.** The prompt carries the task, the area, what "done" looks like, and only the
   minimum of the parent's context. It tells the child to open as a Desk (`/desk <child>`) and to end with
   the numbered list SKILL.md § 8 asks for. Use a Sonnet-class model by default. Keep the top model
   for work that needs altitude (design, people, strategy), and say why when you do.
5. **Tell the user in one line:** the child's name, local or cloud, the model, and that you will send
   it later ideas on this topic.

Rules that stay in force after this command (they are in SKILL.md § 8): the parent sends the child, with
`SendMessage`, the ideas the user writes later about that topic; a cloud session cannot answer, so
what it needs goes in the first brief or waits for its report; and a Desk may propose or open a
sub-desk on its own when a piece of work is a task of its own, without waiting for `/subdesk`.
