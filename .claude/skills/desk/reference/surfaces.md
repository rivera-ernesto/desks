# Surfaces: browsers, screens, simulators, connected tools

A surface is anything you act through other than files. Use whichever the session has. If one is
missing, say so and continue with what is there.

## Which one

1. **A connected tool for that service** (mail, calendar, drive, tracker), when there is one. It is
   faster and more exact than clicking.
2. **The user's own browser** (the Claude extension in Chrome), for sites where they are logged in.
3. **The built-in browser pane**, for reading the open web, checking a published page, and anything
   that should stay apart from their own browser.
4. **Computer use**, for desktop apps that have nothing better.
5. **A phone simulator**, when a site or app only behaves properly on a phone.

Read pages as text where the tool allows it. Take a screenshot only to judge how something looks.

## Rules that cost something to learn

- **Read-only on logged-in accounts** unless the user asked, in this session, for that kind of
  action. Reading pages and statistics is fine.
- **Opening a message can mark it read.** Read conversation lists, not conversations, unless asked.
  If you did open one, mark it unread again, then say so.
- **No likes, follows or reactions**, ever, unless asked for that exact kind of action. If you left
  one by mistake, remove it and say so.
- **Never type or click blind.** Before any input, confirm the right tab or window is visible and
  focused. Find elements by their text, not by where they were on the screen a moment ago.
- **Do not send keystrokes into a desktop app** to drive it when the page data or a connected tool
  can do the same thing. Stray keystrokes land in whatever window has focus.
- **Autocomplete fields** (a city, a category): pick the entry from the list that appears, then
  check the value on the saved page. Typed text that was never picked is often discarded silently.
- **One, verify, then many.** Do the action once, confirm the result where the user would see it,
  and only then repeat it.
- **The step that commits stays with you.** Posting, sending, publishing and paying are never
  delegated to a worker.
- **Passwords, codes and payment details are the user's to type.** Stop and ask them to do it.
- **A shared simulator or browser** may be in use by another session. Reuse what is running; do not
  start, restart or shut down devices you did not start.

## Extraction goes to the screen worker

"Go to X and pull out Y" (numbers from a dashboard, whether a post is live, the state of twenty
listings) goes to `desk-screen`. It returns the quotes and numbers and discards its screenshots,
so they never enter this conversation. Keep here: judging how something looks, anything that
changes state, logins.
