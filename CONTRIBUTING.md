# Contributing

Desk is small on purpose. The contract (`skills/desk/SKILL.md`) is what every session reads, so
every line in it costs every user some of their allowance on every Desk.

## What is welcome

- **A report of how a real Desk went**, especially where it failed. Use the "Desk report" issue
  form. This is the most useful contribution.
- **A new surface**: how to drive a tool well (a connector, a browser, an app), written as rules
  that cost something to learn. It goes in `skills/desk/reference/surfaces.md` or a new reference
  file, never in the contract.
- **A new review lane**, as a function in `scripts/review.py` or a documented `reviewers.txt` line.
- **Translations** of the docs and the site.

## Rules of the house

1. **A mechanism before a line.** If a script, a template or a check can carry a lesson, put it
   there instead of adding a sentence to the contract.
2. **Amend before adding.** Tighten an existing line where you can. A change that adds a rule to
   `SKILL.md` should say which line it could not be folded into.
3. **A rule needs a reason from use.** Say what happened, at least once, that the rule would have
   prevented. "It seems safer" is not a reason.
4. **Nothing personal.** No real names, places, accounts or private details in examples, tests or
   commit messages. Invent them.
5. **No new dependencies.** The script uses the Python standard library only.
6. **Free models only** in the default review path. The script refuses anything else, and that
   stays.

## Before you open a pull request

- `claude plugin validate .` passes.
- `python3 skills/desk/scripts/review.py --check` runs.
- If you changed the site: `npm run build` in `site/` passes.
- You ran one real Desk with your change and say in the PR what happened.

## Ports

Desks for another assistant is welcome, here or in your own repository. What carries over as it
is: `skills/desk/SKILL.md` (the contract is plain instructions), the reference files, the
templates, and `scripts/review.py` and `scripts/desk.py`, which do not depend on Claude. What you
rewrite: how the contract gets loaded (here, a skill and one block in `CLAUDE.md`), the three
workers (here, subagent files), and the surfaces file. In a port, the author named in the review
prompt should be the model you are porting to, and the review should exclude that model's vendor.
Not every assistant can do all of it. A port that does part of it honestly is still a port.
