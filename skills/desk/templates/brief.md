# Brief: {{topic}}

Opened by `{{parent}}` at level {{level}}. Usage reserve at this level: {{reserve}}. The parent checks it
from the host's usage reading before it starts this child and again before it starts another; there is
no counter shared across the tree.

## The user's words, verbatim

> {{paste what the user said about this work, unedited; do not paraphrase}}

## The plan, pinned

The plan this child works from is the one at commit `{{plan_commit}}` of the parent's branch. If the plan
changes, the parent re-briefs; the child does not follow a newer one on its own.

## Goal

{{one sentence: the result the parent will check}}

## You may touch

- {{paths or folders}}

## You may not touch

The parent's own files, anything outside the list above, and anything the folder's rules keep for the user.

## Finish with

A numbered list, one line per item, each saying what was done and where. Then a coverage line: every
item of this brief is either in the list or named as not done, with the reason. Save your files,
close with `desk.py close`. The parent checks each line against the diff before it takes your branch in.
If you open a child of your own, re-brief it the same way: the user's words verbatim and the plan pinned.
