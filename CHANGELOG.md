# Changelog

## Unreleased

- Site: Astro 7.3.8; canonical addresses, language pairs, a share image per language, a sitemap
  and robots.txt, a not-found page in both languages, and a build that fails when any of them is
  missing. The pages name the three kinds of folder, the three workers, `desk setup` and `desk profile`,
  and say what the install runs.
- **A cloud session on this repository runs as a Desk.** It loads the skill and workers from
  copies in `.claude/` (a test keeps them identical), and `DESK_REVIEW_KEY=proxy` lets the review
  use a key the network adds, one the session never sees; `review.py --check` says whether it is attached.
- **A Desk opened in a cloud session works like a local one** (`reference/cloud.md`, with the
  table of what works, what is reduced and what is off there). At the git levels the topic lives on
  the session's own branch, and the close refuses until everything is committed and pushed.
- **One provider layer, `providers.py`**: OpenRouter (free models only) and any endpoint that
  speaks the OpenAI chat API (a shared model, your own, an Apple Intelligence gateway), each
  declared by `base_url`, `model`, where its key comes from (`env:`, `file:`, `proxy`, `none`) and
  its lane (`vendor` or `private`, the latter with the two-code check). A cloud environment
  declares endpoints with `DESK_ENDPOINT_<NAME>_*` variables and private terms with
  `DESK_PRIVATE_TERMS`.
- **The dashboard**: `providers.py` shows which providers answer (one cheap ping each), which review
  lanes this environment has, and the exact step for each missing piece; `html <file>` writes it
  as a page, `serve` edits it on the user's machine (a pasted key goes to a private file), and
  `export` lists the keys a machine has, by name and origin, for a cloud environment. `desk dashboard`
  and `/dashboard` show it inside a Desk. Key values are never shown, logged or written to a
  repository; tests check it.

## 0.2.0 (2026-10-19)

- **Licence:** MIT now says, in the README, that it covers the instructions, documentation, site
  text and examples too, not only the scripts; the name is not licensed by it.
- Every close ends with one `Closed line:` that the session copies into its reply, like the review
  label: no line, not closed (#66).
- **The house close's last two steps are in the contract** (#66): after the folder's routine, the
  short note from `session-house.md`, then `desk.py close`, quoting its line. They lived only in a
  reference file the session never opened. The stop names `session-house.md` under a house close.
- **Fixed:** with `Open: house follow`, `desk.py close` looked for the topic in the main folder
  and never in the working copy the folder's own opener made, so every house close failed at its
  last step (#65). A failed close now says "The Desk is not closed".
- **A refusal is an answer** (#63): when a permission is denied, the session stops that step and
  says what it was for; it never reaches the same end another way, and never calls a Desk closed
  unless the close command finished. The contract stays at 260 lines.
- `desk.py get <Key>` prints a recorded answer (#64).
- **`desk adopt` finds a folder's own routines** (#53). New `desk.py scan` reads what the
  folder's instructions say to read first and lists the scripts that open, review or close, by name
  and first comment lines in several languages, ranking the ones that procedure names; it runs
  none. `desk.py open` stops before making a second home for a topic when such routines exist and
  nothing is recorded yet (`Open: desks` keeps Desks' own open).
- **`Review: house follow <file>`** (#28): `review.py` then refuses to send on its own and runs
  only as the second opinion the folder's routine starts with `--alongside`.
- After a house close the session does no git of its own (#60); the close step runs with no flag
  and asks the `Close:` question when none is recorded (#59); adopt records lines only with
  `desk.py set`, keeps a standing yes out of permission settings, and checks the key only with
  `--check` (#54, #55, #61); `desk.py set` does not commit with `Git: off` and says which branch it
  committed on (#56); install recommends `CLAUDE.local.md` for a tracked `CLAUDE.md` and writes the
  version actually installed (#57); `review.py` honours `DESK_CONFIG_DIR` (#62).
- **Install text:** a previous install is recognised by the `name: desk` in `SKILL.md`'s front
  matter (#47); `review.py --check` exiting 3 without a key is expected, not a failed step (#46);
  INSTALL.md and the site now give the same update path, `desk update`, and say how it relates to
  pasting the install prompt again (#48).
- **Fixed, found by the first testers:** `desk.py --help` exits 0 (#50); a git folder with no
  commit says why it runs at the folder level (#45); `status` shows "no next step written yet"
  instead of the template's placeholder (#33); the close names the session template and lists
  every unfilled placeholder in one run (#44); a merge that fails because git does not know who
  the user is says so, instead of calling it a conflict (#42); `review.py --verify` reports whether
  the dispositions exist and says `converged` only then (#29); old ledgers are closed after reading (#49).
- **A folder's own way of opening a topic is the open** (#28). With `Open: house follow <file>`,
  `desk.py open` makes no topic folder, branch or working copy and says to follow the file, so a
  topic is no longer kept in two places. `desk.py note` then writes where the session works, or
  stops and says so when that place keeps no topic folders; `desk.py status` names the routine. A
  line the script does not understand stops the open. `desk adopt` proposes the line.
- **Fixed:** dates (`2026-10-15`, with a time, or a range like `2026-10-14..16`) were read as
  phone numbers, and a dated packet was never sent (#24). A real number next to a date is still
  refused.
- **Fixed:** a private term matched inside a longer word ("Mara" in "maracuya"); it now matches
  whole words and phrases only (#51). Setup asks for the list at the first review, and the review
  says so when there is no list, since names are then not checked at all.
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
- Site: a button in the header switches between light and dark by hand and remembers the choice.
  Without a choice, or with JavaScript off, the site follows the system setting as before.

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
