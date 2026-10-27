---
description: The Desk providers dashboard - which review providers answer here, which review lanes this environment has, and the exact step for anything missing. Never shows a key.
---

Show the Desk providers dashboard. It is one script, `scripts/providers.py` in the `desk` skill's
folder (`.claude/skills/desk/`, `~/.claude/skills/desk/`, or `skills/desk/` inside the plugin).
Do not rebuild its content by hand.

1. Run `python3 <that folder>/scripts/providers.py html <a temporary folder>/desk-dashboard.html`.
   It writes the page and prints the same dashboard as text. It makes one cheap call per provider
   (no tokens where the API allows it).
2. Where this surface can show a page or a file (sending a file, a private artifact, a browser
   pane), show the page. Otherwise, or as well, reply with the text: each provider and its state,
   the review lanes here, and each missing item with its steps exactly as printed.
3. Never read, print or ask for a key value, and never ask the user to paste one into the chat.
   To change where a key comes from: on the user's own machine, `providers.py serve` prints a
   page address for them to open; in a cloud session, the steps the dashboard printed (the cloud
   environment's settings). `providers.py export` lists the keys a machine already has, by name
   and origin, for loading into a cloud environment.
4. Inside a Desk this is talk: no review, nothing written in the topic.
