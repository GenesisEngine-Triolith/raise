---
name: validate
description: Use before an investor is added to the pipeline or drafted to, to verify what the entity is, its stage and geography as stated, and whether a named contact is currently there; stores findings as raise evidence.
---

# Validate

Source first, then entity identity, then contact. Run this on every new investor or list before ranking or outreach, and whenever a deal, role or "now invests" claim looks doubtful. Missing information is `unknown`, never a failure.

## Step 1: Source first

If an investor entered the list because of a claimed deal, verify the deal before the investor:

1. Find the primary announcement (the company's own press page, the firm's portfolio page, a regulator or registry filing). Secondary coverage and aggregators only point you to the primary.
2. Check what the deal really was: the company, the round, the date, and whether the investor was in the round as claimed.
3. A company that merely mentions a theme does not make an investor a specialist in it. Record what the portfolio actually shows, not the headline.
4. If you cannot reach a primary source after genuine effort, mark the claim `UNVERIFIED` and do not feed it to outreach.

## Step 2: Entity identity

For each investor, answer: what IS this entity?

- fund (venture, micro, growth)
- angel (individual)
- angel group or network
- family office
- corporate arm (strategic or corporate venture)
- accelerator or studio
- foundation or ecosystem programme

Verify on the entity's own official site only. If the site does not say, the type is `UNVERIFIED`.

Pitfalls:

1. Strategic or corporate arms are not cheque-writing funds. They may invest in kind, in equity rights, or for partnership reasons. Do not route them to normal outreach; record the instrument and ask before classifying.
2. Classify the instrument before the verdict. Check the direction of money on the entity's own site: cash into a round (a cheque writer), the company's shares into a pooled vehicle (an equity swap, not a round investor), or the entity selling a service or introductions (not an investor). Record the thresholds (valuation floors, eligibility) as stated; a threshold that disqualifies today is a revisit condition, not a rejection.
3. An absent cheque size is `unknown`, not "does not invest". A page describing a stake-taking model without a fund size proves only the model.
4. Sibling funds under one brand can be separate vehicles with separate mandates and shared partners. Verify each fund's own site and team page and record the link on both records. A pass or deal at one is evidence about the other, not a verdict on it. A stated criterion checked against one vehicle means "not for this vehicle", and the sibling is the route; never record "the firm is closed".
5. Quote a stated criterion verbatim with its qualifiers ("X or a clear path to X" fails only when the path is also absent).
6. Mixed round participants are not all equity: verify each participant's instrument.

## Step 3: Stage and geography

- Stage: take the published mandate as stated. Unpublished means `unknown`. Never exclude on a stage assumption.
- Geography: take the published mandate as stated, then offices, LP base and past portfolio as supporting signals. No signal is `unknown`, not a fail; it may only change the contact route (warm intro preferred).
- Sector and geography fit are judged against the company profile (`raise_profile_get`), never against assumptions.

## Step 4: Contact

The contact must be a named person currently at the firm.

- Use only contact details from the official site (team, contact, press pages), an official announcement, or a filing. A professional network profile is a secondary fallback.
- Never guess or pattern-build addresses (first.last@domain). Never reuse a stale CRM address without re-checking.
- Departures, role changes and "now invests" claims need a dated source (the firm's team or news page, a dated press item) and the date the claim was true. A role from memory, from the founder or from one search hit is unverified until confirmed. If sources conflict, report both and ask; do not adopt the newest silently.
- Namesakes: a name match is not an entity match. Accept a person's deal, cheque or profile only if the source ties to their firm, city or profile and the search was anchored by one of those. Otherwise the record is `UNVERIFIED` for that person.
- No public contact after a primary-source search: use the firm's inquiry form as the route, or mark `UNVERIFIED`.

## Store the results

For each finding call `raise_evidence_add` with the investor and a `source_url`, one fact per record, using these kinds:

| Kind | What it records |
|---|---|
| `deal` | A verified investment: company, round, date, investor's role |
| `fund` | Entity type, instrument, fund or vehicle facts, sibling links |
| `thesis` | Stated focus, quoted from the firm's own page or post, with date |
| `cheque` | Cheque or round-size range; self-reported ranges are evidence, not facts |
| `exclusion` | A stated criterion that rules the company out, quoted verbatim, and which vehicle it applies to |
| `geography` | Stated mandate, offices, LP base signals |
| `profile` | The named person: role, firm, date the role was confirmed, official-site source |

Records without a `source_url` are not evidence. Anything unconfirmed is stored as `UNVERIFIED` with what is missing.

## Output

For a batch, give a table: investor, entity type, stage, geography, contact, verdict (`valid`, `valid with caution`, `unverified`, `do not add`) and the reason. Stop after genuine effort; do not speculate beyond verifiable sources.
