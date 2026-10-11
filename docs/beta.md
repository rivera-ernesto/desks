# Beta notes

Thank you for trying this. The question the beta has to answer is simple: **does a Desk give you
something your current way of using Claude Code does not?** A "no" is a useful answer.

## What to try (about an hour in total, on real work)

1. **Install** with the prompt in the README. Note anything that was unclear or that asked you
   something you could not answer.
2. **Open one Desk on something real** that is not code and that you have been putting off.
3. **Ask for a recommendation** on it, something you would actually act on. Watch for the label at
   the end of the reply.
4. **Run `desk setup`** to add the free review key, then ask for another recommendation and
   compare. Open one of the answer files in `desks/<topic>/reviews/` and judge for yourself
   whether the objections were worth having.
5. **Close it** (`desk close`), open a **new session**, type `desk <same-topic>`, and see whether
   it picks up without you explaining.
6. If you already have your own rules, agents or plugins: run `desk adopt` and see whether what
   it proposes makes sense.

## What to report

Use the "Desk report" issue form, or just write to the person who invited you. The most useful
things:

- the first moment you were confused;
- a review that changed an answer for the better, or one that was noise;
- anything Desk did that you did not ask for;
- whether you opened a second Desk without being asked to.

## Known limits of 0.1

- Free review models are often busy. The script retries and tops up; a review can still come back
  `[thin]`.
- Without Python 3 on the machine, only the same-vendor review works.
- The plugin install path is less tested than the prompt install.
- One Desk at a time per folder is the tested case.
