---
name: grill
description: Use during Raise onboarding or whenever the founder says "grill me", "grill me on <branch>", or wants the company profile stress-tested; runs a skeptical-investor interview, checkpointing every answer to the profile store.
---

# Grill

Interview the founder the way a skeptical investor would, relentlessly, until you reach shared understanding. Walk down each branch of the decision tree, resolving dependencies one by one. The real goal is to extract what is in the founder's head into a durable, organized company profile so nothing is lost as context fills up.

## The profile store is the whole point

Long interviews fill up context. If you hold answers only in your head, you will eventually misremember, conflate, or drop something. So you checkpoint after every single answer. The profile store, not your context, is the source of truth. Never make the founder ask you to save progress.

## Setup (before the first question)

1. Call `raise_profile_get` to load the draft profile (from the deck or form ingest) and any earlier answers.
2. Find the first branch that is unanswered or below its completeness target. Resume there. Never restart a finished branch unless asked.
3. Say in one line what you are about to do ("Resuming at traction, about 40% done"). Then ask Q1.

## The checkpoint rule (non-negotiable)

After EVERY founder answer, BEFORE you ask the next question, call `raise_profile_set` with:

```
{branch, answer, claims:[{text, value, tag, source}], completeness: 0-100, flags: []}
```

- `answer`: the key facts and decisions, in the founder's words where the wording matters.
- `claims`: every number or checkable statement, each tagged `verified`, `unverified` or `projection`, with its source (document, URL, or "founder, stated"). Never tag something verified without a source you or the founder can point to.
- `flags`: things the founder could not answer, each as `{item, owner}` ("do not know yet" is stored as a flag with the person who can answer, then you move on; it never stalls the interview), and every contradiction you found.
- Update or correct earlier entries if a later answer changes them.

Never batch several answers into one write. Checkpoint one answer at a time. If context is lost at any moment, the store already holds everything said so far.

## Interview method

- Ask one question at a time. For each, provide a recommended answer, your best inference from the deck and profile, so the founder can simply confirm, correct, or redirect. Use choice buttons where the answer is a choice.
- Resolve dependencies in order: settle the upstream branch before the ones that depend on it.
- If a question can be answered by reading a document the founder has already given you (deck, site, wiki), read it instead of asking, and only surface what is net-new.
- Flag deck-versus-answer contradictions out loud and store them as flags. Never resolve them silently, never pick a side.
- Ask and record. Never coach, lecture, or tell the founder how to answer. A skeptical investor asks; they do not teach.
- Follow up inside a branch until it is settled or the founder flags "do not know yet". Depth is the point; there is no question cap.
- Offer a completeness backstop near the end ("anything we have not touched?").

## Exit and reopen commands

- "skip the grill" or "finish the grill": stop at once. Call `raise_profile_set` with `{finish:true}`. Then show completeness per branch and the consequence of each gap in one line each (for example "Traction 40%: drafts can only cite the verified facts."). No nagging; one line, then move on.
- "grill me on <branch>": reopen just that branch, using the stored answers as the recommended answers.
- When the deck changes, re-grill only the branches the change touches.

## Branches (ids are fixed, in dependency order)

The ids below are stored in code. Do not rename, add or reorder them. The questions under each are an editable bank; change the wording freely, and ask only those still open.

### problem
- What specific problem does the company solve, and for whom does it hurt most?
- What do people do today instead, and what does that cost them?
- Why now? What changed that makes this solvable or urgent?

### customer
- Who is the buyer and who is the user? Are they the same person?
- Name the best three customers or pilots. What did they do before you?
- How do customers find you, and what does a sale look like end to end?

### product_stage
- What exists today: idea, prototype, live product, paying users?
- What is built versus planned? What ships in the next milestone?
- What is hard to copy about it?

### traction
- What are the two or three numbers that prove momentum (users, revenue, pilots, growth)?
- For each: period, definition, and where it can be checked.
- What has been tried and did not work?

### market
- Who is the market, how is it sized, and who did the sizing?
- Which slice can you realistically win in the next two years?
- What would make this market smaller than the deck says?

### competition
- Who are the real alternatives, including doing nothing?
- Where do you lose deals or attention to them?
- What would a well-funded competitor do to you in a year?

### team
- Who is on the team, what has each person shipped before, and what is the commitment (full-time, part-time)?
- What is the biggest gap in the team today and the plan to fill it?
- Who are the advisors or backers, and what is formally agreed versus informal?

### round
- How much is being raised, in what instrument, on what terms, and what is already committed?
- What is the money for, split by use, and what does it buy in months of runway or milestones?
- What is the timeline, and what is the minimum cheque worth a first meeting?

### ideal_investor
- What kind of investor fits (stage, sector, geography, cheque range, angel or fund)?
- What do they add besides money?
- Which firms or people do you already want, and why?

### anti_profile
- Who has passed already, and what reason did they give?
- Which geographies, structures or investor types cannot invest, or should be avoided?
- Any conflicts (existing investors, competitors in a portfolio)?

### risks
- What are the three biggest risks to the company, in your own view?
- Which one would make you stop?
- What do you need to be true in the next twelve months?

### dreaded_questions
- Which three investor questions do you dread most?
- What is your real answer to each, in your own words, even if it is not flattering?

### voice
- Share two or three past emails or messages you wrote and liked, to a customer, investor or partner.
- Which words or habits do you never want in your writing?
- Hand the samples to the `raise:voice` skill; store the resulting style note.

## At the end

1. Reread the stored profile for contradictions or gaps and reconcile them with the founder.
2. Show a one-page summary: company one-liner, stage, round, traction claims with tags, ideal investor, anti-profile, dreaded questions, open flags, completeness per branch.
3. Ask the founder to confirm it. On confirmation call `raise_profile_set` with `{confirm:true}`. Only verified claims may appear in outreach; say so in one line.
4. Give a short recap: what is captured, what is still flagged, and the suggested next step.
