# Closing a Desk

The test of a good close: a fresh session that reads only `desks/<topic>/README.md` can continue
the work without asking the user what happened.

1. **Update the README** (the topic's standing notes):
   - *State*: where things stand today, in a few lines. Replace the old state; do not append to it.
   - *What we learned*: rules that will hold next time ("the buyer group only answers on weekends",
     "prices here are quoted without tax"). Tighten or delete older ones that this session proved
     wrong. This section should get better, not longer.
   - *Next step*: the single most useful next action, and what it waits on.
   - *Open*: what is undecided, and whose move it is.
2. **Add dated lines to `decisions.md`** for anything decided that is not there yet: what, why,
   and what was ruled out.
3. **Write the session note**: copy `templates/session.md` to
   `sessions/<date>-<short-title>.md`. Keep it short. It is the history; the README is the state.
4. **Give every snag one of three ends.** A snag is something about *how the work went* that will
   happen again: a wrong assumption, a tool that misbehaved, a step you had to redo.
   - *Fixed*: it is now a line in the README's "What we learned", or a change to a template.
   - *Open*: it is in the README's "Open" list.
   - *Dropped*: one line in the session note saying why it does not matter.
   Nothing is left only in the conversation.
5. **Offer what you noticed** about how the user works, as a question (`reference/profile.md`
   § Learning as you go). At most one or two, and only if they would hold next time.
6. **Save and close.** If no `Close:` line is recorded yet, ask once and record it with
   `desk.py set` before anything else. Commit your files by path with one plain message, then:
   - `desk.py close <topic> --merge` folds the Desk into the main folder and removes its working
     copy. This is the default for solo work.
   - `desk.py close <topic> --pr` (the `github` level, when the block says `Close: review`) sends
     the branch and opens a pull request whose text is the session note. Give the user the link.
   - At the `github` level, each item still in the README's "Open" list that someone must act on
     can be an Issue: `gh issue create` with a title a stranger would understand. Ask once whether
     they want that; record `- Issues: on`.
   - The script refuses while placeholders or unsaved files remain. Fix what it names; do not
     work around it.
7. **Final reply**: what was done, what is open, the paths of the files, and a suggested title for
   the conversation so the user can find it again.

A Desk that keeps going after its close just closes again later: update the same files.

## A folder with its own close

Some folders had a way of closing a session before Desk arrived: their own record of the session,
their own branches and review, their own place for lessons. Closing the Desk way there drops all
of it without a word. So when the block says `Close: house …`, **that routine is the close.** It
stays the authority and runs unchanged; Desk adds pointers to it and never a second account of the
session.

Two forms, one line in the block:

- `Close: house run <command>`: the routine is one command (`make close`, a script).
  `desk.py close <topic>` runs it from the main folder, with `DESK_TOPIC` and `DESK_TOPIC_FOLDER`
  set and no keyboard input. If it fails the Desk is not closed: stop and say so. Do not run it a
  second time unless you know that is safe.
- `Close: house follow <file>`: the routine is a written procedure. Read the file and carry it
  out to the end before anything below. If a step fails, stop and say so; the Desk is not closed.
  `desk.py close <topic>` runs nothing in this form and says the routine was reported, not checked.
  It cannot tell whether you did the procedure. Do not claim more than that either.

In both forms:

1. **What the session made goes where the folder would have put it without Desk.** The topic
   folder points there. Lessons too: if the folder has a place for durable rules, they land there
   and "What we learned" points to it.
2. **Update the topic's README**: state, next step, open items, and where the folder's own record
   of the session is.
3. **Write the session note from `templates/session-house.md`**: a few lines that point at that
   record. Do not retell the session; the script warns when the note is long.
4. **Run `desk.py close <topic>`, with no flag.** It checks Desk's own notes first, so a
   placeholder left in the README cannot stop the close after the routine has already run. It
   writes nothing and does no merge, push or pull request: saving is the routine's business.
   A folder whose routine also makes its own branches records `Git: off` as well.
5. Steps 4, 5 and 7 above (snags, what you noticed, final reply) still apply. A snag the folder's
   routine already gives an end to is not given a second one.

**Nothing runs on a line the user has not confirmed.** `desk.py set Close "house …"`, run only
after their yes to that exact line, records it and keeps a copy outside the folder
(`~/.config/desk/house-close.json`). A line that arrived another way, by hand, a clone or a pull,
or that changed since, makes the close stop and print it. Show the user the line; record it only
on their yes. This is `[needs you: access]`. The copy covers the line, not what the line points
at: a script the command runs, or a procedure file, can change with a pull and the line stays the
same. If you notice it changed, say so before the close. Setting `Close:` to anything else forgets
the yes; a procedure file is a file inside the folder.

**No `Close:` line, but the folder looks like it has a routine** (a closing script, a "closing"
section in its rules): ask once, proposing the line. With no answer, close the Desk way and say
in the final reply what the folder's routine would have done that this close did not.
