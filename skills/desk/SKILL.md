---
name: desk
description: Open or continue a Desk, a focused working session on one topic with reviewed answers, cheap workers and a written close. Use when the user writes "desk <topic>", "open desk <topic>", "abre desk <tema>", "/desk", asks to continue or close a desk, asks for a second opinion from other AI models, or starts real work on a topic that already has a folder under desks/.
---

# Desk

A Desk is one working session on one topic. It is for real work that is mostly not code: selling
something, planning a trip, drafting posts, researching a decision, running a small project. This
file is the whole contract. Read it once when the Desk opens and follow it until the Desk closes.

"You" below is the agent. "The user" is the person you work for.

## Commands

| The user writes | Do |
|---|---|
| `desk <topic>` · `/desk <topic>` · `abre desk <tema>` | Open or continue that topic (§ 1) |
| `desk` with no topic | Run `scripts/desk.py status`; list the topics with the "Next step" of each; ask which |
| `desk review` | Review your last substantive answer now (§ 3) |
| `desk close` · `cierra` | Close the Desk (§ 7) |
| `desk setup` | Walk through every setup question at once (`reference/setup.md`) |
| `desk adopt` · `desk import` | Fit Desk to the tools, folders and habits already here (`reference/adopt.md`) |
| `desk profile` | Build or update the user's profile (`reference/profile.md`) |
| `desk update` · `desk remove` | Get the current version, or take Desk out (`reference/adopt.md` § Updating) |

A first message that is clearly work on a topic, with no command, is still a Desk: suggest a short
topic name (or an existing one that fits), ask only to confirm it, and open it on the answer.
Reading and talking need no topic.

`scripts/` and `reference/` are in this skill's own folder. Run the scripts from the folder the
session was opened on.

## 1) Opening

1. Run `python3 <skill folder>/scripts/desk.py open <topic>`. It prints where to work. Work there
   and nowhere else. It also prints the **level**, which it detects and never demands:
   - `folder`: no git. The topic is `desks/<topic>/`.
   - `git`: the topic has its own branch and its own working copy, so the main folder is never
     left half-edited and several Desks can run at once.
   - `github`: as `git`, and the close can open a pull request.
2. **New topic:** the script copied the README template. Fill the goal in one sentence from what
   the user said. Nothing else yet.
3. **Existing topic:** read its `README.md` (state, what was learned, next step) and the newest
   file in `sessions/`. Read nothing else until the task needs it.
4. Say one boot line: topic · new or continued · level · review mode (§ 3) · anything that needs
   attention. Then start on the work. Never open with "what would you like me to do?" when the
   README already names a next step: propose it.

**Git stays under the hood.** The user never has to type or understand it. You do the plumbing
through `desk.py`, and you commit your own files, by path, at each milestone with a plain message.
Never `git add -A`, never switch branches or stash in the main folder, never force, never commit
files you did not write. Say "saved" and "sent for your review", not "committed" and "pushed",
unless the user speaks git.

**Setup happens as you go.** Do not front-load questions. The first time something is needed
(a place to keep history, a review key, GitHub, the user's profile), ask that one question, with
your recommended default first, and record the answer in the Desk block of `CLAUDE.md` so no
session asks again. The questions and their defaults are in `reference/setup.md`.

## 2) Working rules

- **Write only in the place `desk.py open` printed**, unless the user points you at another file.
  Files the user never saved to history are not in a topic's working copy: read them from the main
  folder by full path, and do not edit them there.
- **Discuss first.** A question or an observation from the user ("how come…?", "it seems…") is an
  opening to discuss. Explain the cause and propose; do not go and change things.
- **Build, send, publish, buy or delete only on the user's explicit go.** Gather and propose first.
- **Check the premise before you execute.** Name what must be true for the task to be worth doing.
  If you can verify it with the tools at hand, verify it without asking. If it is false or cannot be
  verified, stop and say so. Do not work around a missing foundation.
- **A plan is in phases, and it is researched before it is written.** Before the first plan, look
  at what the folder and the README already hold on the topic. Then fill `templates/plan.md`:
  small phases, each with a result the user can check. A list of generic actions is not a plan.
- **Decisions land in the folder before they go anywhere else.** Add a dated line to
  `decisions.md` when something is decided, and keep the README's state current.
- **Facts about other people and prices go stale.** Write `verified <date>` next to them, and check
  again before acting on one older than a week.
- **Do not agree by default.** Your first job on any claim the user makes is to check the premise
  it hinges on. Say so plainly when it does not hold.

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
   user it is running (about three minutes, no cost). It asks free models from other vendors and
   prints a label line with a receipt.
3. Read every answer. Give each finding a disposition (adopted, rejected and why, or left to the
   user) in `<packet>-reviews.md`. Change your answer accordingly.
4. End the reply with the label line, copied from the script's output.

**Review modes**, said once in the boot line:

- `cross-vendor`: a review key is set up. The full loop.
- `same-vendor`: no key. Give the packet to a fresh `desk-reader` subagent with the instruction to
  attack it, and label the reply `Review: [same-vendor]`. This catches slips. It does not catch
  what every Claude model would miss, and the user should know that. Offer `desk setup` once.

**Labels.** `[converged]` several vendors answered and every finding has a disposition ·
`[thin]` only one vendor answered · `[same-vendor]` reviewed by a Claude subagent only ·
`[unreviewed]` no review ran · `[quick]` the user asked, in their own words, to skip it. A label
without a receipt is only valid for `[same-vendor]`, `[unreviewed]` and `[quick]`. Never write a
label the script did not print. If an answer changes after its review, it is unreviewed again.

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

Name the worker when you delegate: an unnamed subagent runs on your own model and saves nothing.
Delegate only when the work takes more tool calls than briefing the worker does. A worker returns
evidence. Check any "not found" it reports before you rely on it, and when you pass on what it
saw, say it is the worker's reading. The names may appear with a `desk:` prefix.

## 6) Browsers, accounts, screens

Read `reference/surfaces.md` before the first browser, screen or phone-simulator step. The floor:

- **Read-only on the user's logged-in accounts** unless they ask, in this session, for that kind of
  action ("post it", "reply to them"). No posting, sending, liking, following, joining, or marking
  things read. A permission does not carry to the next session.
- **The step that commits** (post, send, publish, pay) stays in this conversation, never in a
  worker. One action, verify it, then repeat.
- **If you change something by mistake**, put it back at once and then report it.

## 7) Closing

A long session costs more per reply the longer it runs, because every turn re-reads all of it.
So **propose the close yourself**, once, at a milestone (something decided, sent or finished) when
the session has grown long or has been compacted. Say in one line what a fresh Desk on this topic
would start from. Close on the user's word; keep going if they say so.

To close, read `reference/close.md`. In short:

1. Rewrite the topic's `README.md` so the next session needs nothing else.
2. Write `sessions/<date>-<title>.md` from `templates/session.md`.
3. Give every snag of the session one of three ends: fixed in the README, kept as an open item
   (an Issue at the `github` level), or dropped with a reason.
4. Propose, do not impose, anything you noticed about how the user works (`reference/profile.md`).
5. Save your files, then `desk.py close <topic> --merge`, or `--pr` at the `github` level when the
   user reviews before merging. The script refuses while placeholders or unsaved files remain.

Final reply: what was done, what is open, where the files are, and a title for the conversation.

## 8) Keeping usage low

- Read what the task needs when it needs it, never at the start.
- Screens and long outputs go to a worker (§ 5). Screenshots are the most expensive thing a session
  can hold.
- When you revise a document, show the change, not the whole document again.
- Size the answer to the decision, not to the topic.
- More in `reference/usage.md`, including what was measured.
