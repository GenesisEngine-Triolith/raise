---
name: draft
description: Use when writing one investor email or DM for a pipeline target, or when the founder asks for outreach drafts; gives the structure the message must follow before it goes through raise_draft.
---

# Draft

Structure for ONE investor message. The tool `raise_draft` runs the gate check (can this investor be drafted at all), the lint, one automatic rewrite pass, and creates the Gmail draft. The model never creates email drafts itself. Nothing is ever sent by Raise; the founder reviews and sends.

## Before writing: research

1. Pull the investor's evidence from the raise record. Pick ONE fresh, investor-specific fact: a recent deal, a post, or a thesis line. Note its evidence id (for example `ev_123`) so lint can check it.
2. No fresh, cited fact means no draft. Report it and ask for research instead of inventing a reason.
3. Take claims only from the verified list in the company profile (`raise_profile_get`). Anything tagged unverified or projection stays out.

## Shape of the message

1. One line on why you are writing to THEM: the cited fact, stated plainly and accurately.
2. One or two lines on what the company does and the single verified proof point that matters most to this investor.
3. A plain ask: a short call, or feedback on whether it fits their focus.
4. A casual close that ends in a question ("Worth a quick chat?").

## Rules

- Email: under about 120 words. DM: under about 60 words.
- No attachment and no deck link in the first touch. Offer it if they ask.
- Never state the raise amount, valuation or terms in a public or semi-public channel (DMs, posts, public forms). Keep them for a call.
- No em dashes. No not-X-but-Y contrasts, staged openers, forced triads, bold labels, or inflated words (the humanizer skill lists them).
- Write in the founder's voice: the profile style note plus any voice skill in `draft_skills`.
- Email subject lines: short, specific, low-key, no hype.

## Follow-ups

A follow-up must read as a follow-up:

- Refer to the earlier note in a few words ("Following up on my note from last week").
- Add ONE new thing: a new verified fact, a milestone, or a new investor-specific item with its own evidence id.
- Do not repeat the original pitch and do not guilt-trip. Keep it shorter than the first message and end in a question again.

## Submit

Call `raise_draft` with the investor, channel (email or dm), the message, and the evidence ids used. If it returns lint failures, fix them at the given positions. If it refuses, report the reason; do not work around the gate.
