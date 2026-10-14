# Changelog

## Unreleased

- **A cloud session on this repository runs as a Desk.** It loads the skill and workers from
  copies in `.claude/` (a test keeps them identical), and `DESK_REVIEW_KEY=proxy` lets the review
  use a key the network adds, one the session never sees; `review.py --check` says whether it is attached.
- **Commands are written in English only.** The Spanish aliases `cierra` and `abre desk` are gone
  from the command table. A command plainly given in the user's own language still works, and so
  does a word their Desk block records as theirs. Ordinary talk ("enough for today") is a reason
  to offer the close, never to start it.
- A test checks that the version is the same everywhere a person copies it from.
- **A folder's own closing routine is the close.** `Close: house run <command>` or
  `Close: house follow <file>`: the routine must finish for the Desk to be closed, Desk writes nothing and
  does no git of its own, and the session note only points at the folder's record. Nothing runs
  on a line the user has not confirmed: `desk.py set` keeps a copy of the confirmed line outside
  the folder, and a line that arrived or changed some other way stops the close.
- **Fixed:** a `Close:` line the script did not understand was ignored and the close fell back to
  a direct merge. It now stops and prints the line.
- **Fixed:** a settings line with backticks inside its value was not read at all, and
  `Git: off` followed by a remark was not read as off.
- `desk.py close <topic>` needs no flag once `Close: merge` or `Close: review` is recorded.
- **Fixed before release** (found reading this change as code): a backslash in a recorded value
  was mangled when it replaced an existing line; the command printed for confirming a line was
  not safe to paste; `house follow` accepted a file outside the folder; an unreadable list of
  confirmations was silently replaced; setting `Close:` to something else did not forget the old yes;
  the confirmed line was compared in a tidied form, so backticks added or removed by hand went unnoticed.
- `[unreviewed]` is no longer a way to finish a piece of advice: the reply says it is not ready to
  act on, and the review runs before the next advice. A receipt covers one packet; a new
  recommendation needs its own.
- `desk feedback`: the Desk drafts a report of the session with the private parts removed; the
  person sends it, or does not.
- Unit tests for both scripts, run in CI. `close` refuses an empty README.
- The Desk block can live in `CLAUDE.local.md`, for a shared project whose `CLAUDE.md` is not
  yours to change.
- README, site and Spanish quickstart open with what a person would say ("I want to sell my old
  camera") and Claude proposing the topic name; `desk <topic>` is shown as the way back in.
  "With names removed" now reads "with names and contact details removed".

## 0.1.7 (2026-10-11)

- The Desk leads: it opens with a read and a proposed move, carries the habits itself, offers
  what was not asked when it has evidence, and gives a brief across all topics. `Lead: quiet`
  turns the initiative off.

No migration needed.

## 0.1.6 (2026-10-11)

- A Desk shows what it added to a short request, each addition with its source and guesses
  labelled as guesses, before it starts.

No migration needed.

## 0.1.5 (2026-10-11)

Found by a second full test Desk, in a folder that already had rules, an agent and client folders.

- **Fixed:** recording several `Setup` lines kept only the last (`desk.py add`), and recording a
  setting removed a blank line from the block.
- `desk.py open` says when a README that was already there lacks the Desk sections;
  `desk.py status` shows notes waiting in inboxes; `close` says when it is run from the wrong folder.
- `desk adopt` handles a house rule that restricts running scripts, and uses the user's own agents
  where the block names them.
- `review.py --help` prints the usage.

No migration needed.

## 0.1.4 (2026-10-11)

- The site is in English and Spanish, every page.
- A profile can start from something the user already wrote.

No migration needed.

## 0.1.3 (2026-10-11)

Found by running a full Desk on the installed skill, and by reviewing 0.1.2's own new rule.

- **Fixed:** noting something for another topic no longer opens a second branch from inside a
  session. `desk.py note` leaves it in that topic's `inbox/`; the next Desk there folds it in.
- `desk.py set` records a setup answer in the main folder and saves it by itself, so a later
  close is not blocked by a half-edited `CLAUDE.md`.
- The dispositions file is `<packet>-dispositions.md`, no longer confusable with the answers
  folder. Adopting reviewers' findings needs no second review.
- Close checks every note of the topic for placeholders; `decisions.md` is created with the topic.
- Reviews wait less for slow models; a wrong packet path says so.

**Migration from 0.1.2:** none required. Existing `<packet>-reviews.md` files can stay as they are.

## 0.1.2 (2026-10-11)

- A Desk can hold more than one topic: what comes up in passing is filed under its own topic
  instead of being refused. (Its first wording had a defect, fixed in 0.1.3.)

No migration needed.

## 0.1.1 (2026-10-11)

- The project is named Desks; the repository moved to `rivera-ernesto/desks`.
- Install: the points a test install had to guess are settled.
- Site: an example of messy input.

No migration needed from 0.1.0.

## 0.1.0 (2026-10-11, first public version, early)

First extraction.

- The Desk contract as one skill, with reference files read on demand.
- Cross-vendor review script: free models only, one per vendor, privacy refusal, ledger, receipts.
- Optional lanes: reviewers the user already pays for, and a private lane through a macOS Shortcut.
- Three workers: `desk-reader`, `desk-screen`, `desk-runner`.
- Install by prompt into an existing folder, or as a plugin.
- `desk adopt`, to fit around an existing setup; a profile; import and update.
- Three levels detected, never required: plain folder, git (a branch and working copy per topic),
  GitHub (pull request on close).

Not in 0.1, on purpose: a maintainer session that receives and merges several Desks, usage
metering scripts, packaged test suites, signed releases.
