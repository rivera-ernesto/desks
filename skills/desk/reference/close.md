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
6. **Save and close.** Commit your files by path with one plain message, then:
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
