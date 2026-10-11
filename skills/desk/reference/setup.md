# Setup, one question at a time

Desk configures itself with the user as the work goes. Ask each question **the first time it
matters**, never all at the start, unless they typed `desk setup`. Each question comes with a
recommended default and one line on what it buys. Record every answer with
`desk.py set "<Key>" "<value>"`, which writes the line in the Desk block of the main folder's
`CLAUDE.md` and saves it by itself, so no session asks twice and a later close is not blocked. Start with `python3 <skill folder>/scripts/desk.py status`
and `scripts/review.py --check`: do not ask what you can detect.

| When it first matters | Question | Recommended default | Line recorded |
|---|---|---|---|
| First Desk in a folder with no git | Keep a history of this folder, so every Desk can be undone and several can run at once? | Yes (§ Starting a history) | `- Git: on` or `- Git: off` |
| First close at the `git` level | When a Desk closes, fold it into the main folder directly, or keep it for you to look at first? | Fold it in directly (`--merge`) for solo work | `- Close: merge` or `- Close: review` |
| The folder has no GitHub remote and the user wants a backup or to work from two machines | Create a **private** GitHub repository for this folder? | Yes, private (`[needs you: outside]`: it creates something on their account) | `- GitHub: on` |
| First advice-level answer with no review key | Add a free review key so other vendors check my answers? Three minutes. | Yes (§ Review key) | (detected, not recorded) |
| First topic about the user, their voice or their people | Build a short profile so I stop asking who is who? | Yes, five minutes (`reference/profile.md`) | `- Profile: <path>` |
| The folder already has rules, agents or project folders | Fit around what is here? | Yes (`reference/adopt.md`) | `- Setup: …` lines |
| The user mentions their phone | Continue sessions from the phone? | Their switch to turn (§ Phone) | none |

A repository that is **public** is never pushed to unless the user says so in words; then record
`- Public pushes: yes`. Everything in a Desk folder would become public with it.

## Starting a history

Only when `desk.py status` says the folder is **not** a repository. A folder that already has one
is left exactly as it is: never run `git init` there, never touch its branches.

1. Write a `.gitignore` first (or add to the one that exists, showing the lines): secrets
   (`.env*`, `*.key`, `*.pem`, `credentials*`, `secrets*`), system files (`.DS_Store`), and
   anything large that is not text (video, disk images, archives).
2. Show the user the list of what would go into the first save, with sizes, and anything that
   looks like a secret or is over a few megabytes called out. Wait for their yes.
3. `git init`, add the listed files by path, one commit. Nothing is sent anywhere: a history on
   this machine is not a backup and not public.

Undoing it is deleting the hidden `.git` folder; say so.

## Review key (free, about three minutes)

This turns `same-vendor` into `cross-vendor`.

1. The user creates an account at openrouter.ai and creates a key. Creating an account is theirs to
   do (`[needs you: outside]`): give them the steps, do not do it for them.
2. **The key never goes into the chat.** With the key copied to the clipboard, the user runs one
   command in a terminal:
   - macOS: `mkdir -p ~/.config/desk && pbpaste > ~/.config/desk/openrouter.key && chmod 600 ~/.config/desk/openrouter.key`
   - Windows (PowerShell): `New-Item -Force -ItemType Directory $HOME\.config\desk; Get-Clipboard | Set-Content $HOME\.config\desk\openrouter.key`
   - Linux: the same as macOS with their clipboard tool in place of `pbpaste`.
3. Run `--check` again, then one review on a harmless packet so they see it work.

Tell them plainly:

- The script only ever asks models whose price is zero, and refuses any other.
- With no credit on the account the limit is 50 requests a day, about eight reviews. Buying 10 USD
  of credit once raises it to 1000 a day, and free models do not consume that credit. **This is
  the recommended setup**, and it is their money and their call (`[needs you: money]`).
- What leaves the machine: only the packet file, with identifying details removed. Free models may
  keep or train on what they receive: OpenRouter's privacy settings have a switch for providers
  that train on inputs, and most free models are only reachable with it on. Have them look at
  that page so the choice is theirs. Nothing else from the folder is sent.
- The first time, **show them the packet before it goes**. If they want that every time, record
  `- Review: ask first`.

## Private terms

Ask for the words that must never leave the machine: family names, a client, a street, a company.
Write them one per line to `~/.config/desk/private-terms.txt`. The review script refuses any
packet that contains one. Ask this right after the review key, and again when a profile is built.

## A private lane (Mac with Apple Intelligence, optional)

For material you would not send to a free model. In the Shortcuts app the user creates a Shortcut
with three actions:

1. *Receive* **Text** input.
2. *Use Model*, model set to **Private Cloud Compute**, with the Shortcut input as the request.
3. *Stop and Output* the model's response.

They name it (for example `Desk Review`), and you write that name to
`~/.config/desk/apple-shortcut`. Run a review to confirm that the answer repeats both codes. If
the result says `canary-missing`, the Shortcut is using the small on-device model: check step 2.

## Phone

A session started on the computer can be continued from the Claude phone app once Remote Control is
on for that session. It is the user's switch to turn, because it makes the session reachable, and
approvable, from the phone. Tell them where it is; do not change settings for them. Links to
files do not open on a phone: send the file itself when the surface can.
