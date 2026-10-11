# desk adopt: fit Desk to what is already here

Desk is meant to sit beside whatever the user already runs, not replace it. Run this once after
installing into a folder that is already in use, or when the user says they have other tools.
Look first, then propose a short list, then change only what they agree to.

## Look (read-only; use `desk-reader` if it is more than a few files)

- `CLAUDE.md` here and in the user's home configuration: rules that already cover what Desk does.
- `.claude/agents`, `.claude/skills`, installed plugins: workers and skills that overlap.
- Connected tools (connectors, MCP servers): mail, calendar, drive, trackers, chat.
- The folder's own structure: where notes, decisions and project files already live.
- Other AI tools on the machine: command-line clients for other subscriptions.

## Propose

- **Their rules win.** Where their `CLAUDE.md` and this contract disagree, say where, and follow
  theirs unless they choose otherwise. Never rewrite their file; the installer adds one marked
  block and nothing else.
- **Desk root.** If they already keep projects somewhere (`projects/`, `clients/`, a notes vault),
  offer to use that as the Desk root in place of `desks/`. It is one line in the `CLAUDE.md` block:
  `Desk root: projects/`. A topic's README can be the README that is already there: add the Desk
  sections to it, keep the rest.
- **Workers.** If they already have a cheap reading agent, use theirs and say so. The three Desk
  workers are defaults, not requirements.
- **Reviewers.** Each other AI subscription with a command-line client can be a review lane, and a
  stronger one than a free model. Find the command that takes a prompt on standard input and
  prints the answer, test it by hand, then add `name | command` to `~/.config/desk/reviewers.txt`.
  If their client cannot run that way, leave it out.
- **Connected tools** are surfaces like any other: reading is free, anything that sends or changes
  waits for their go (`reference/surfaces.md`).
- **Memory.** If they use Claude's own memory, keep using it for preferences about how to work.
  What belongs to a topic goes in that topic's README, where the next session reads it.

## Record

Write what was agreed as a short "Setup" section in the `CLAUDE.md` block, so the next session
does not ask again.

## Importing how the user already works

People arrive with history: a notes folder, project folders, exported chats, a task list. Do not
convert it all. For each thing they point at:

1. Have `desk-reader` survey it and report what is there (kinds of files, how recent, what looks
   like an active project). No copying yet.
2. Propose which items are **live topics**. For each, create the topic with `desk.py open` and
   write its README from the source: goal, state, next step, what was already learned. Link to
   the original files by path; leave them where they are.
3. Everything else stays where it is. A topic is created when work starts on it, not before.

Rules they wrote for another assistant (custom instructions, a system prompt, a rules file) are
worth reading once: carry over what is a preference, and ask about anything that conflicts with
the five things that always wait for their word.

## Updating

`desk update`: read `CHANGELOG.md` in the source repository, tell the user what changed since the
`- Version:` line in the Desk block, and on their yes run the install steps again. The skill
folder is replaced; `desks/`, the profile, `~/.config/desk/` and the rest of `CLAUDE.md` are never
touched. If the changelog lists a **Migration** for a version in between, do each one in order
and say what it changed. Do not check for updates on your own; it costs a network call per session
and nobody asked.

`desk remove`: list the files from the "Removing" section of the source's `INSTALL.md`, and delete
them on the user's yes. `desks/` and the profile are theirs and stay.

## When Desk itself gets in the way

A snag caused by Desk (a rule that did not fit, a script that failed) is worth more upstream than
in one folder. At the close, offer to draft a "Desk report" for the project's issue tracker, with
everything private removed. Sending it is the user's call (`[needs you: public]`).
