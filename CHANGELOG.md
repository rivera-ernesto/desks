# Changelog

## Unreleased

### 0.3.0 candidate

Principle: Desks owns the mechanism; a folder keeps only its policy, as lines in the Desk block. Every
item below removes a manual step a folder had to script itself. Net surface: the scripts grow by
about 900 lines for twelve items; items 6 and 12 are new machinery (a thin delegation contract and
the digest) and are counted as such. The contract stays under 300 lines.

- **One opener, one closer (item 1).** `desk.py open` cuts a topic from `Base:` (fetched; a missing
  base stops it, never the checked-out branch), takes a lock (a pid and a 10-minute TTL; a dead owner
  or an old lock is reclaimed, a live fresh one is waited for), refuses to reopen a topic whose close
  was already received (exit 4, names `<topic>-2`) and asks once before reopening one that was handed
  over and not received (exit 5, `--reopen`). It never creates folders in the main folder and prints
  the working copy. `desk.py close` finds the topic from the working copy. `Branch prefix:` and
  `Ready trailer:` name the branch family and the line that marks a handed-over head.
- **Hooks are first-class (item 2).** `Open:`, `Review:` and `Close:` take `house follow <file>` or
  `house run <command>`; a `run` command only runs in the form the user confirmed (per step).
  `House git:` states which git steps the folder's routine owns. After a house close Desks still
  warns about unsaved files and a missing ready trailer, and prints the next step.
- **One review lane (item 3).** `Gate:` (run as `<command> <file> public|private`; any non-zero exit,
  a first line starting `REFUSE`, or a gate that cannot run, refuses) replaces the built-in scan and
  the private-terms list when present. `Private lane:` is a command reading the packet path, answer on
  stdout, exit 3 for too large. `Reviews:` and `Dispositions:` name the folder and file. A family
  counts only when its answer, minus tool calls and reasoning blocks, has 200 characters; failed
  families are replaced from the live list until three answered; fewer than three, or only the
  private lane, exits 6 and is `[thin]`. `--verify` works from any folder (receipts are indexed in
  `~/.config/desk/receipts.tsv`), says `converged` only when every row of the dispositions table has
  a disposition and the packet is unchanged. `--background` returns at once and a watchdog stops a
  hung run; `--status` reads it; `--help` exits 0.
- **Review is not skippable (item 4).** `desk.py close` refuses a `[converged]`, `[thin]` or `[open]`
  label with no verifiable receipt, a stale packet, and `[quick]` unless `- Quick loop: allowed`.
- **State only where it is versioned (item 5).** `open` and `note` refuse a path git ignores;
  `Pointers only: yes` seeds only the README pointer; `status` reports state the main folder holds;
  `desk.py migrate <topic>` copies it into the working copy; `Sessions:` moves the session notes.
- **Delegation contract (item 6, thin).** `desk.py open <child> --parent <topic>` cuts from the
  parent's branch, writes `brief.md` from `templates/brief.md`, enforces `Depth cap:` (default 3,
  `none`) and prints `Usage reserve:` for that level. `desk.py children` lists running, ready and
  received children. Not in this version: resuming a paused child, scheduling.
- **Permission wording (item 7).** A refusal is asked once through the app's prompt and retried once
  on a yes; a standing yes is never written into the project's permission settings; adopt never opens
  a key file.
- **Install and docs (item 8).** One update path in INSTALL.md (#48); the skill header declares its
  `license:` and what it `requires:` (#76); `--help` exits 0 for both scripts; the settings table
  lists every line of the Desk block.
- **Lessons land (item 9).** Every line under `## Lessons` ends with `→ topic`, `→ house <file>`,
  `→ issue <ref>` or `→ dropped: <reason>`; the close refuses one without. `Close sections:` lists
  the headings a note must have.
- **Receive (item 11).** `desk.py receive [<topic>]` lists, or takes a ready topic in all or nothing:
  a scratch merge (or `Receive merge:`), `Receive checks:`, then the target moves; any failure leaves
  the working copy, branch and trailer untouched and the digest shows `blocked`. Exit 0 received,
  2 nothing ready, 3 blocked, 4 escalation (`Escalate:` names a tab-separated rules file: `path`,
  `doctrine`, `max-lines`, `undeclared`, `anomalies`; computed from git and the file, a missing file
  escalates). `--escalated-ok "<why>" --head <sha>` is a reader's decision at that exact head.
  `Differed log:` collects the close note's "Where Desks differed" rows in the same step.
- **Digest (item 12).** `desk.py digest [--fetch]` prints lane, working copy, ready and blocked
  topics, escalations, children and base staleness with exit codes 0, 2, 3, 4, 5;
  `--freeze <file> --next "<step>"` writes that state and refuses while a child runs (exit 6);
  `--compare <file>` checks a later boot against it (exit 1 on a difference).

- Site: Astro 7.3.8; canonical addresses, language pairs, a share image per language, a sitemap
  and robots.txt, a not-found page in both languages, and a build that fails when any of them is
  missing. The pages name the three kinds of folder, the three workers, `desk setup` and `desk profile`,
  and say what the install runs.

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
