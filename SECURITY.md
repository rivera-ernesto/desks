# Security and privacy

Desk is instructions for an AI agent plus two small scripts. This page says plainly what it can
do on your machine, what leaves it, and where the weak points are.

## What leaves your machine

- **Review packets.** When cross-vendor review is on, one file per review is sent to OpenRouter
  and from there to several model vendors. Nothing else from your folder is sent by Desk.
- **Free models may keep or train on what they receive.** Treat a packet as something you would
  be willing to post anonymously. If that is not acceptable for a topic, use the same-vendor
  review or a private lane.
- **The privacy check is a seatbelt, not a guarantee.** The script refuses packets containing
  email addresses, phone-like numbers, key-like strings and the words on your private list. It is
  pattern matching and can miss things written unusually. The real control is that the packet is
  one readable file, written without identifying details, that you can read before it goes: set
  `Review: ask first` to approve each one.
- **Your review key** lives in `~/.config/desk/openrouter.key`, outside any project, and is sent
  only to openrouter.ai. It is never written to the chat or the repository.

## What Desk does to your files

- It writes inside the topic's folder, and the Desk block of `CLAUDE.md`.
- If the folder has a git history, each topic works on its own branch in its own working copy.
  Closing a topic merges it into your main branch as one merge commit, which one `git revert`
  undoes. The script refuses to merge on conflicts or with unsaved changes, and never forces.
- It never starts a history in a folder that already has one, never pushes to a public repository
  unless you said so, and never deletes unmerged work.

## The install prompt

Installing means telling an AI agent to follow a file fetched from the internet. That is a real
risk pattern, and you should treat any such prompt, from anyone, with suspicion. What limits it
here:

- The prompt names a **version tag**, which does not move, instead of a branch that can change.
- `INSTALL.md` is about a hundred lines and only copies files. Read it first.
- The agent must show you the list of files before copying, and stop if the fetched copy asks for
  anything beyond copying.
- Releases are not signed yet. If you need that assurance, download the zip, read it, and install
  from your local copy.

## What an AI agent can still get wrong

Desk's rules are instructions, not a sandbox. An agent can misread them. The protections that do
not depend on the agent behaving are Claude Code's own permission prompts, the refusals inside the
two scripts, and git history. Keep the permission prompts on for anything that sends, pays or
deletes.

## Reporting a problem

Open an issue with the label `security` for anything that is not sensitive. For anything that
is, use GitHub's private vulnerability reporting on this repository.
