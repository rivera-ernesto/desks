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

- **Rules that restrict what Desk needs.** If their rules say to ask before running scripts or
  commands, theirs win: ask once for a standing yes for Desk's own two scripts (`desk.py`,
  `review.py`), and record it. Without that yes, ask each time.
- **A README that was already there** stays theirs. Add the Desk sections to it (State, Next
  step, Open, What we learned) and keep everything it says. `desk.py open` tells you when a
  topic's README lacks them.

## Record

Record each thing agreed with `desk.py add "Setup" "<one line>"`, and single answers with
`desk.py set` (`Desk root`, `Close`), so the next session does not ask again. Ask the `Close:`
question here too (`reference/setup.md`).

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

## Feedback

Desks is early, and what its makers need most is how real sessions went. `desk feedback`, or your
own offer at a close when a snag was caused by Desks itself (a rule that did not fit, a script
that failed, a step that confused them). Offer it once per session at most.

1. Draft the report from this session, short: the kind of topic in general terms, the review mode,
   where it helped, where it got in the way, what they already use, and the Desks version from
   the Desk block. **Remove everything private**: names, places, amounts, the content of the work.
   Describe the snag, not their life.
2. Show them the draft. They edit it or drop it.
3. Sending is theirs (`[needs you: public]`: the tracker is public). On their yes, whichever is
   there: `gh issue create --repo rivera-ernesto/desks --title "<title>" --body-file <draft>`, or
   give them the link `https://github.com/rivera-ernesto/desks/issues/new?template=desk-report.yml`
   and the text to paste. If they prefer to send it privately to whoever invited them, hand them
   the text and leave it there.
4. Never send anything about a session on your own, and never include a review packet or a file.
