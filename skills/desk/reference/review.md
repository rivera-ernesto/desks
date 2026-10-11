# The review loop, in full

## Why

One model's first draft sounds as confident when it is wrong as when it is right. Models from
other vendors were trained differently and fail differently, so they catch what you cannot see in
your own answer. Free models are weaker than you are. That is fine: you are not asking them to be
right, you are asking them to disagree, and then you judge each objection on its merits.

## The packet

A packet is one self-contained file. The reviewers see nothing else.

- State the question, the context a stranger needs, and your proposed answer.
- **Remove what identifies people**: names, contacts, addresses, account names, exact places.
  Write "a cousin", "a mid-size city", "the buyer".
- End with the specific things you want checked.
- Start from `templates/packet.md`. Save it as `desks/<topic>/reviews/<date>-<slug>.md`.

The script refuses a packet that contains an email address, a phone-like number, something that
looks like a key, or any line of `~/.config/desk/private-terms.txt`. A refusal is not an obstacle
to get around. Rewrite the packet, or use a lane that keeps the material private.

## Running it

```
python3 <skill folder>/scripts/review.py desks/<topic>/reviews/<packet>.md "what to look for"
```

It picks one free model per vendor from the live list, asks them in parallel, retries once, and
tops up with other vendors until three have answered. It writes the answers to
`<packet>-reviews/` with a ledger and a receipt, and prints the label line.

- **Some will fail.** Free endpoints are often busy. The script keeps going; you do not need to.
- **"ACCOUNT CAP"** means the daily limit for free models was reached. Another model will not help.
  The limit is 50 requests a day, or 1000 once the account has bought 10 USD of credit. Free
  models do not spend that credit. This is the user's money and the user's decision
  (`[needs you: money]`); never suggest paid models as the way around it.
- **Check a label** someone doubts: `review.py --verify <receipt> desks/`.

## Reading the answers

1. Read every answer file, not the summary.
2. List the findings. For each one: **adopted** (and what changed), **rejected** (and why, in one
   line), or **left to the user** (a real disagreement about what they want).
3. Write that table to `<packet>-reviews.md`, next to the packet.
4. Reviewers are sometimes plainly wrong about facts or misread the packet. Say so and move on. Do
   not average a disagreement away to look balanced.
5. Rewrite your answer. If it changed in substance after the review, it needs a new review.

## The reply

Lead with the answer. Then, for each point where reviewers disagreed with you or with each other,
say whose reasoning you followed and why. Say what is still unresolved, and which way you lean.
End with the label line.

## A question to the user is reviewed too

Before you ask the user to choose between options, put the choice through the loop and bring a
recommendation. The exceptions are the five kinds in § 4 of the contract.

## Other lanes

- **Tools the user already pays for.** Any command that reads a prompt on standard input and prints
  an answer can be a reviewer. One line each in `~/.config/desk/reviewers.txt`:
  `name | command`. For example a command-line client for another AI subscription. These count as
  vendors. `reference/adopt.md` explains how to find them.
- **A private lane on a Mac.** A macOS Shortcut that sends its input to Apple's Private Cloud
  Compute model can review material you would not send to a free model. Put the Shortcut's name in
  `~/.config/desk/apple-shortcut`. The script proves each call read the whole input (it plants two
  codes and the answer must repeat both). This lane is reported separately and never counted as a
  vendor. Building the Shortcut: `reference/setup.md`.
- **No lanes at all.** Give the packet to a fresh `desk-reader` subagent with "attack this".
  Label `[same-vendor]`.
