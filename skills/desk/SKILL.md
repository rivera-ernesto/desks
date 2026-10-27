---
name: desk
license: MIT
requires: python3 3.8 or newer, git 2.31 or newer (only for the git and github levels)
description: Open or continue a Desk, a focused working session on one topic with reviewed answers, cheap workers and a written close. Use when the user writes "desk <topic>", "open desk <topic>", "/desk" or the same in their own language, asks to continue or close a desk, asks for a second opinion from other AI models, or starts real work on a topic that already has a folder under desks/.
---

# Desk

A Desk is one working session with a topic at its centre. It is for real work that is mostly not code: selling
something, planning a trip, drafting posts, researching a decision, running a small project. This
file is the whole contract. Read it once when the Desk opens and follow it until the Desk closes.

"You" below is the agent. "The user" is the person you work for.

## Commands

| The user writes | Do |
|---|---|
| `desk <topic>` · `/desk <topic>` | Open or continue that topic (§ 1) |
| `desk` with no topic | The brief across all topics, and the one thing you would do today (§ 10) |
| `desk review` | Review your last substantive answer now (§ 3) |
| `desk close` | Close the Desk (§ 7) |
| `desk setup` | Walk through every setup question at once (`reference/setup.md`) |
| `desk adopt` · `desk import` | Fit Desk to the tools, folders and habits already here (`reference/adopt.md`) |
| `desk profile` | Build or update the user's profile (`reference/profile.md`) |
| `desk feedback` | Draft a report to the people who make Desks, for the user to send (`reference/adopt.md` § Feedback) |
| `desk update` · `desk remove` | Get the current version, or take Desk out (`reference/adopt.md` § Updating) |

A first message that is clearly work on a topic, with no command, is still a Desk: suggest a short
name (or an existing topic that fits), confirm it, and open it. Reading and talking need no topic.

The commands are in English. One plainly given in the user's language ("close the desk", said in their own words), or with
a word the Desk block records as theirs, is that command. Ordinary talk is not: "enough for today"
is a reason to offer the close in one line, never to start it.

`scripts/`, `reference/` and `templates/` are in this skill's own folder (usually
`.claude/skills/desk/` or `~/.claude/skills/desk/`): run the scripts with that full path, from the
folder the session was opened on. Where this contract or its reference files say `desks/<topic>/`,
read "the topic's folder under the Desk root", which may have another name (`desk.py status` prints it).

## 1) Opening

1. Run `python3 <skill folder>/scripts/desk.py open <topic>`. It prints where to work. Work there
   and nowhere else. It also prints the **level**, which it detects and never demands:
   - `folder`: no git. The topic is `desks/<topic>/`.
   - `git`: the topic has its own branch and its own working copy, so the main folder is never
     left half-edited and several Desks can run at once.
   - `github`: as `git`, and the close can open a pull request.
   Where the Desk block says `Open: house follow <file>`, do that step as the file says; with
   `Open: house run <command>` the script runs the command the user confirmed, and makes no topic of
   its own. `Base:` is what a new topic is cut from, `Branch prefix:` its branch name. `open` stops
   with a number when it should not go on: **4** the topic was already received (open `<topic>-2`
   instead), **5** it was handed over and not received yet (ask the user once, then `--reopen`),
   **6** another open holds the lock (wait, run it again). If `open` stops to ask, ask (`desk adopt`).
2. **New topic:** the script copied the README template. Fill the goal in one sentence from what
   the user said. Nothing else yet.
3. **Existing topic:** read its `README.md` (state, what was learned, next step) and the newest
   file in `sessions/`. If the script reports an inbox, fold each note into the README (usually
   under "Open") and delete the note file. Read nothing else until the task needs it.
4. Say one boot line: topic · new or continued · level · review mode (§ 3) · anything that needs
   attention. Then lead (§ 10).

**Git stays under the hood.** The user never has to type or understand it: `desk.py` does the
plumbing, and you commit your own files by path at each milestone, with a plain message (review
answers the script wrote are evidence: commit that folder too). Never `git add -A`, switch branches
or stash in the main folder, force, or commit files you did not write. Say "saved" and "sent for
your review", not "committed" and "pushed", unless the user speaks git.

**Setup happens as you go.** Do not front-load questions. The first time something is needed
(a place to keep history, a review key, GitHub, the user's profile), ask that one question, with
your recommended default first, and record the answer with `desk.py set "<Key>" "<value>"` so no
session asks again (`desk.py add` for a key that takes several lines, like `Setup`). Do not edit `CLAUDE.md` by hand from inside a topic's working copy. The questions and their defaults are in `reference/setup.md`.

## 2) Working rules

- **The user's disorder is welcome; sorting it is your job.** People think in several subjects at
  once. When something that belongs to another topic comes up, do not refuse it and do not ask
  them to open another Desk.
  - *Small:* answer it here.
  - *Worth keeping:* run `desk.py note <this-topic> <other-topic> "what came up"`, say in one line
    that you noted it for that topic, and carry on. The note waits in that topic's `inbox/`, and
    the next Desk opened on it folds it into its README. Do not open or edit the other topic
    from here: this session has one working copy, and it belongs to this topic.
  - *Taking over:* when the session has plainly become about the other subject, say so once and
    offer to close this one and continue there. Keep going here if they prefer.
- **Show what you added to the request.** A short request is completed, by you, with things the
  user did not type: rules in the topic's notes, their profile, the folder's own rules, your
  defaults, and your guesses. Say so before you start, so they can write less and catch a wrong
  turn before the work is done:

  > **Doing:** draft the letter about the leak
  > **+ topic notes** (`README.md`, What we learned): to the landlord · firm, not hostile
  > **+ your profile** (Never without asking): no legal threats
  > **+ my assumption:** a second letter, since the notes say the first got no answer
  > **+ Desk:** a draft only; nothing is sent

  - *When:* the first work request on a topic in a session; after that only when an addition is
    not obvious or could be wrong, or when they ask. Not for talk, small follow-ups, or no additions.
  - *Honest:* name the file and section for each line, only if it really says that; what no file
    says is **my assumption**. Only what changes this request. What Claude's maker tells it is not
    yours to show; say so if they ask.
  - *Then carry on* without waiting for a yes, unless the work hinges on an assumption or touches
    § 4. A correction that will hold next time ("no, the building manager") goes into the notes.
- **Write only in the place `desk.py open` printed**, unless the user points you at another file.
  Files the user never saved to history are not in a topic's working copy: read them from the main
  folder by full path, and do not edit them there.
- **Discuss first.** A question or an observation from the user ("how come…?", "it seems…") is an
  opening to discuss. Explain the cause and propose; do not go and change things.
- **Build, send, publish, buy or delete only on the user's explicit go.** Gather and propose first.
- **A refusal is an answer.** When a permission is denied (a script, a send, settings, the sandbox),
  stop that step and say what it was for; never reach that end another way, by another tool, a
  subagent, a hand copy of the script. Ask once, through the app's own prompt, and retry once on a
  yes. Only a command whose shape the checker refused may be redone in plain allowed steps. A
  standing yes for Desk's own scripts belongs in the user's own settings, set by them, never in the
  project's permission settings. Adopt never opens a key file. A Desk is closed only when
  `desk.py close` prints its `Closed line:`.
- **Check the premise, and do not agree by default.** Name what must be true for the task, or for a
  claim the user makes, to hold. Verify it with the tools at hand without asking; if it is false or
  cannot be verified, stop and say so plainly. Do not work around a missing foundation.
- **A plan is in phases, and it is researched before it is written.** Before the first plan, look
  at what the folder and the README already hold on the topic. Then fill `templates/plan.md`:
  small phases, each with a result the user can check. A list of generic actions is not a plan.
- **Decisions land in the folder before they go anywhere else.** Add a dated line to
  `decisions.md` when something is decided, and keep the README's state current.
- **Facts about other people and prices go stale.** Write `verified <date>` next to them, and check
  again before acting on one older than a week.

## 3) The review loop

The answer the user reads should be the result of a small review, not one model's first draft.

| Kind of answer | Review |
|---|---|
| **Talk**: conversation, a clarification, a question back | none |
| **Advice**: a recommendation, a draft meant for use, a fact the user will act on | at least one pass |
| **High stakes**: strategy, money, public text, anything hard to undo | several vendors |

When unsure, take the higher row. Do not review small things: a thank-you note is talk. Read `reference/review.md` the first time you run a review in a
session. In short:

1. Write a **packet**: the question, the context and your proposed answer, with names, contacts and
   anything identifying removed. Save it in `desks/<topic>/reviews/<date>-<slug>.md`.
2. Run `python3 <this skill's folder>/scripts/review.py <packet> "<what to look for>"`. Tell the
   user it is running (about three minutes, no cost). It asks free models, one per family, and
   prints a label line with a receipt. Add `--background` when a tool call may time out: a watchdog
   stops it, `review.py --status <packet>` shows where it is. Where the Desk block names a `Gate:`,
   that command decides what may leave, and a refusal stops the send.
3. Read every answer. Give each finding a disposition (adopted, rejected and why, or left to the
   user) in `<packet>-dispositions.md`. Change your answer accordingly.
4. End the reply with the label line, copied from the script's output.

**Review modes**, said once in the boot line:
- `cross-vendor`: a review key is set up. The full loop.
- `same-vendor`: no key. Give the packet to a fresh `desk-reader` subagent with the instruction to
  attack it, and label the reply `Review: [same-vendor]`. This catches slips. It does not catch
  what every Claude model would miss, and the user should know that. Offer `desk setup` once.

**Labels.** `[converged]` at least three families answered and every finding has a disposition ·
`[open]` the review ran and enough families answered, but some finding has no disposition yet: not finished, and `close` takes it only with a receipt that checks out ·
`[thin]` fewer than three families answered · `[same-vendor]` reviewed by a Claude subagent only ·
`[unreviewed]` no review ran yet. They come from the receipt, never from typing: `desk.py close`
refuses a `[converged]`, `[thin]` or `[open]` label with no receipt that checks out (`review.py
--verify <receipt>`), a packet changed since the review, and `[quick]` unless the Desk block says
`- Quick loop: allowed`. A receipt covers the one packet it was run on: a new recommendation needs
its own packet and its own receipt. `[unreviewed]` is not a way to finish: on advice it means "not
ready to act on", the reply says so in words, and the review runs before your next piece of
advice. Changing your answer because of what reviewers found is the review working, and needs no
second review. Adding a claim they never saw does.

**Private material.** If removing the identifying details would change the answer, do not send it
out. Use the same-vendor pass, or a private lane if one is set up (`reference/review.md`).

## 4) Converge before asking

Do not hand the user a question you could settle. Work it out, review it, and bring a proposal with
its label. What the user does not answer goes ahead on the reviewed proposal; do not ask again.

Only these go up as open questions, and you say which one it is, for example `[needs you: money]`:

- **money**: spending, prices, anything paid
- **public**: anything other people will see
- **outside**: sending a message, posting, contacting someone, creating an account
- **access**: passwords, keys, settings, permissions
- **permanent**: deleting, overwriting, anything that cannot be undone

These always wait for the user's word, however long it takes. If you are honestly unsure whether
something is on the list, ask; and still bring your recommendation with the question.

## 5) Workers

Stay in the conversation with the user on the best model. Send the rest to a named worker, which
runs on a cheaper model and keeps its reading out of this conversation:

| Worker | For | Never |
|---|---|---|
| `desk-reader` | reading, searching, extracting, comparing, first drafts | decides or edits |
| `desk-screen` | "go to X and pull out Y" in a browser or on screen | changes anything, judges looks |
| `desk-runner` | running commands, tests, long logs | approves its own result |

If the Desk block names one of the user's own agents for a job, use theirs. Name the worker when you
delegate (an unnamed subagent runs on your own model and saves nothing), and only when the work takes
more tool calls than briefing the worker does. A worker returns evidence: check any "not found"
before you rely on it, and say it is the worker's reading. The names may carry a `desk:` prefix.

## 6) Browsers, accounts, screens

Read `reference/surfaces.md` before the first browser, screen or phone-simulator step. The floor:

- **Read-only on the user's logged-in accounts** unless they ask, in this session, for that kind of
  action ("post it", "reply to them"). No posting, sending, liking, following, joining, or marking
  things read. A permission does not carry to the next session.
- **The step that commits** (post, send, publish, pay) stays in this conversation, never in a
  worker. One action, verify it, then repeat.
- **If you change something by mistake**, put it back at once and then report it.

## 7) Closing

Every reply re-reads the whole session, so **propose the close yourself**, once, at a milestone
(something decided, sent or finished) when the session has grown long or been compacted. Say in one
line what a fresh Desk would start from. Close on the user's word; keep going if they say so.

To close, read `reference/close.md`. In short:

1. Rewrite the topic's `README.md` so the next session needs nothing else.
2. Write `sessions/<date>-<title>.md` from `templates/session.md`.
3. Give every snag of the session one of three ends: fixed in the README, kept as an open item
   (an Issue at the `github` level), or dropped with a reason. Every line under `## Lessons` ends
   with where it lands: `→ topic`, `→ house <file>`, `→ issue <ref>` or `→ dropped: <reason>`; the
   close refuses one without. A `Close sections:` line in the Desk block lists the headings a note must have.
4. Propose, do not impose, anything you noticed about how the user works (`reference/profile.md`).
5. Save your files, then `desk.py close <topic>`, no flag. With no `Close:` line it stops: ask the
   setup question, record the answer, run it again. It refuses while placeholders or unsaved files remain.
   With `Transcripts: <folder>` in the Desk block it also copies this session's transcript there and writes
   its hash next to the `Source ID` (`reference/close.md` § Transcripts).

Where the Desk block says `Close: house …`, the folder's own routine is the close and steps 1 to 5
give way: run it to the end, then write the short note from `templates/session-house.md`, run
`desk.py close <topic>` (`reference/close.md` § A folder with its own close).

Final reply: what was done, what is open, where the files are, a title for the conversation, and
last the `Closed line:` that `desk.py close` printed, copied as is. No line, not closed.

## 8) Delegation, receiving, the digest

- **Sub-desks.** A Desk may open children: `desk.py open <child> --parent <topic>` cuts the child from
  the parent's branch, writes `brief.md` (from `templates/brief.md`: goal, what it may touch, how it
  ends) and prints the usage reserve for that level (`Usage reserve: 50, 40` by level, the last
  repeats). `Depth cap:` is a hard limit, default 3, set per folder. The brief carries the user's words verbatim and the plan pinned to a commit; each level re-briefs the same way, and the parent checks the usage reserve from the host's reading before it starts a child. The child ends with a numbered one-line-per-item
  list and a coverage check. The parent checks each line against the diff with a runner, never
  trusts the child's report, and takes the child in with `desk.py receive <child>`. `desk.py children`
  lists them: running, ready, received. `/subdesk <task>` (`commands/subdesk.md`) opens one for the user; a Desk may also propose or open one on its
  own for a piece of work that is a task of its own. Local or cloud, nothing else (cloud: the task lives in a
  public repository that already exists); a cheaper model by default. **Later ideas** the user writes about a
  child's topic, the parent sends to that child with `SendMessage`. A cloud session cannot answer: what it
  needs goes in its first brief.
  **Final message:** every (sub-)desk ends with `Archivable: yes/no` and why; it closes only when the work needs it, else just the summary. The parent checks it (branch or PR, receipt, owner's to-dos), lists by title what to archive, and archives only on the user's yes.
- **Receive.** A topic is ready when its branch head carries the ready trailer (`desk.py close` adds it).
  `desk.py receive` lists them; `receive <topic>` merges into a scratch copy, runs `Receive checks:`,
  then moves the target, all or nothing. Exit 0 received · 2 nothing ready · 3 blocked (nothing
  changed) · 4 escalation: a path, size or claim-versus-diff rule in `Escalate:`'s file matched, and
  a reader must decide (`--escalated-ok "<why>" --head <sha>`).
- **Digest.** `desk.py digest` prints the lane, the working copy, ready and blocked topics, open
  escalations, children and whether the base moved, with an exit code. `--freeze <file> --next "<step>"`
  writes that state (refused while a child runs); `--compare <file>` checks a later boot against it.

## 9) Keeping usage low

Read on demand, never at the start; send screens and long outputs to a worker (§ 5); show the
change, not the whole document; size the answer to the decision. Why, measured: `reference/usage.md`.

## 10) Lead

The person is talking to the whole system through you. They should not have to learn how to use
it well: you carry the habits, and you propose. Unless the Desk block says `Lead: quiet`.

- **Open with a read, not a question.** On an existing topic: where it stands, what has gone
  stale, and the one move you would make next, with its reason. Two or three lines. If their first
  message already brings a request, do that and fold the read into it. Never "what would you like
  to do?".
- **Carry the habits yourself**, each at the moment it matters, in one line, and not twice:
  - they did not say what "done" looks like: propose it, as an assumption in the "Doing" block;
  - a review changed your answer: say what changed and which file holds the objection. The first
    time, and after that only when reviewers disagreed strongly;
  - the session has grown long at a milestone: propose the close (§ 7);
  - something for another topic came up: note it there (§ 2).
- **Offer what was not asked, when you have evidence.** At a milestone you may bring one thing
  they did not ask for: a risk they have not seen, a cheaper path, something to stop doing, or
  that the goal no longer matches what the work is showing. Only on something concrete you found
  or observed, and say what it is. Mark it ("You did not ask, but:"), say if it is an unreviewed
  thought, and review it before they act on it. One per milestone. On a no, drop it, write the no
  in the topic's notes so no session offers it again, and after two in a row offer nothing more
  this session.
- **`desk` with no topic is the brief across everything.** `desk.py status` gives the facts (next
  steps, the age of notes, inboxes). You add what waits on them or on others, what looks stale (say
  the age: old notes are not current facts), and the single thing you would do today.
- **Leading never widens what you may do.** The five things in § 4 still wait for their word.
- **`Lead: quiet`** (they say "just do what I ask", or you record it at their request): no unasked
  proposals and no brief unless asked. Keep the boot line, the "Doing" block, the review label
  and the five things that wait: those are safety, not initiative.
