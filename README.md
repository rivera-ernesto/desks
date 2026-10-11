# Desks

**A way of working for Claude Code: work sorted by topic, answers checked by other AI vendors, a written close.**

You type `desk sell-camera`. Claude opens a folder for that topic, works on it with you, has its
recommendations attacked by models from other companies before you read them, sends the heavy
reading to cheaper workers, and when the session gets long, writes down where things stand so the
next session picks up without you explaining anything.

Desks is the project; a Desk is one session. It is for real work that is mostly not code: selling something, planning, drafting, researching a
decision, running a small project. It needs a paid Claude plan and Claude Code (the desktop app's
Code tab, or the terminal). It is not made by, or affiliated with, Anthropic.

> **Status: 0.1, early.** It is extracted from a setup one person has used daily. It has not yet
> been proven by people who are not that person. Reports of where it fails are the most useful
> thing you can send.

## Install

Open the folder you want to work in with Claude Code and paste:

```text
Set up Desks in this folder. Get version v0.1.3 of https://github.com/rivera-ernesto/desks, read its INSTALL.md and follow it. First show me the list of files you will create or change, and wait for my yes. Keep everything I already have.
```

Read [INSTALL.md](INSTALL.md) first if you like to know what a prompt will do; it is short.
It also covers installing as a plugin, and installing from a downloaded copy.

Then:

```text
desk my-first-topic
```

## What you get

| | |
|---|---|
| **Sorted for you** | Write the way you think, several subjects at once. Each one is filed under its own topic, so nothing said in passing is lost. |
| **One topic, one folder** | `desks/<topic>/` holds the state, the decisions and a note per session. Plain files you can read. History, branches and pull requests happen under the hood when git is there. You never type it. |
| **Reviewed answers** | Advice and anything high-stakes is sent, with names removed, to free models from other vendors. Claude answers their objections before you see the result, and the reply carries a label you can verify. |
| **Proposals, not questions** | Claude settles what it can and brings a reviewed proposal. It stops for your word only on money, anything public, contacting someone, access, and anything permanent. |
| **Nothing sent without your go** | Reading is free. Posting, sending, buying and deleting wait for you. Your logged-in accounts are read-only unless you say otherwise. |
| **Cheaper sessions** | Reading, screen work and long outputs go to workers on a smaller model. The session proposes its own close before it gets expensive. |
| **A close that carries over** | The topic's README is rewritten so a fresh session can continue from it alone. |

## The review, honestly

- **With a free OpenRouter key** (three minutes, `desk setup`): several vendors review each
  substantive answer. Free models are weaker than Claude. They are not there to be right; they are
  there to disagree, and Claude has to answer each objection.
- **Without a key**: a separate Claude subagent attacks the answer, and the reply says
  `[same-vendor]`. That catches slips. It does not catch what every Claude model would miss.
- **What leaves your machine**: only the review packet, a single file with identifying details
  removed. The script refuses packets containing email addresses, phone numbers, keys, or any word
  on your private list. Free models may keep what they receive.
- **Labels**: `[converged]` several vendors answered and each objection was dealt with · `[thin]`
  one vendor · `[same-vendor]` · `[unreviewed]` · `[quick]` you asked to skip it.

## Already have a setup?

Desk adds one skill, three workers and one marked block in `CLAUDE.md`. It does not replace your
rules, agents, plugins or connected tools. `desk adopt` looks at what you have and proposes how to
fit around it: your project folders as the Desk root, your own workers, and any other AI
subscription you pay for as a stronger reviewer.

## What is in here

```
skills/desk/SKILL.md      the contract: everything a Desk session follows
skills/desk/reference/    read on demand: review, setup, adopt, surfaces, close, usage
skills/desk/scripts/      review.py and desk.py (Python standard library only)
skills/desk/templates/    topic README, session note, plan, review packet
agents/                   desk-reader, desk-screen, desk-runner
examples/                 a worked topic, with invented details
docs/                     beta notes, benchmark protocol, guía en español
site/                     the website
```

## Docs

- [Inicio rápido en español](docs/es/inicio-rapido.md)
- [Beta: what to try and how to report](docs/beta.md)
- [Comparing Desk with your current setup](docs/benchmark.md)
- [A worked example](examples/sell-camera/README.md)
- [Security and what leaves your machine](SECURITY.md)
- [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)

## Related projects

Desk reuses what Claude Code already provides (skills, subagents, plugins, working copies). For
neighbouring needs, others may fit better:
[PAL MCP Server](https://github.com/BeehiveInnovations/pal-mcp-server) (multi-model toolkit for
coding), [CCPM](https://github.com/automazeio/ccpm) (issue-driven project management for software),
[Superpowers](https://github.com/obra/superpowers) (a software-development method as skills),
[obsidian-claude-pkm](https://github.com/ballred/obsidian-claude-pkm) (planning in an Obsidian
vault). What Desk adds is the combination: free review across vendors with a receipt, a short fixed
list of things that wait for a person, and a focus on work that is not code.

Want something different? It is MIT: fork it and make it yours.

## Why

Good results from a modest plan. A Desk spends the expensive model on the conversation and the
judgment, sends the reading to smaller models, and has answers checked by models that cost
nothing, so that fewer wrong answers reach you and less compute is burned getting there. Review
by other vendors reduces confident mistakes. It does not eliminate them, and nothing here claims
it does.

## Ports

This repository is the version for Claude Code. The idea is not tied to it: the contract, the
review script and the templates are plain text and plain Python. If you use another assistant,
you can use Desks to build your own version for it. See [CONTRIBUTING.md](CONTRIBUTING.md) § Ports.

## License

MIT. See [LICENSE](LICENSE).
