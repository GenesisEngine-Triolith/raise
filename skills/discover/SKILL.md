---
name: discover
description: Use when the founder wants to find new investors beyond the current pipeline, building a tiered list from public deal data and named partners without burning professional-network search limits.
---

# Discover

Build a broad, tiered investor list from public data first, and save people-level search for last. Sector and geography come from the company profile (`raise_profile_get`); never hardcode them.

## Why this order

Keyword searches on a professional network burn search limits quickly and return generic, repetitive results. Public deal data shows what firms actually do, not what they say. So: mine deals, then find partners by web search, and only then (optionally) check activity.

## Step 0: Optional public curated lists

If a public curated investor list exists for the founder's sector (an openly browsable directory or list page), read it first. It is quicker than searching and often shows stated cheque ranges.

- Use only lists you can open without logging in.
- Dedupe people across lists by normalised name (lowercase, strip accents, punctuation and titles) before counting. Overlap between lists is a relevance signal, not a duplicate to keep.
- Self-reported cheque ranges are evidence, not facts. Store them as sourced `cheque` evidence.

## Step 1: Mine deal sources

Use public round trackers, funding announcements and portfolio pages for the founder's sector and stage.

1. Fetch the page with the available web reader. Extract investor names per deal.
2. Count appearances per firm. Activity frequency beats stated thesis.
3. Skip generic "top investors" listicles. Prefer sources that list real deals with dates.
4. Output: firms sorted by recent deal count, with the deal source URLs.

## Step 2: Find named partners

For each of the top firms, search the web for `"<firm> partner <sector keyword>"` and read the firm's own team and portfolio pages.

- Collect `{name, role, firm, source_url}`. Confirm at least two signals match (name plus firm, name plus role, or firm plus role) before keeping a person.
- Check the firm's team page for current employment; partners move. Unverified roles are marked `UNVERIFIED`, not dropped silently.
- Check the portfolio page, not just the headline thesis, before excluding a firm: a generalist fund may hold companies in the founder's space.
- Run the `validate` skill on promising entries.

## Step 3: Organise by tier

Group the 20 to 40 names by what hook will resonate:

- Tier A, sector specialists: the founder's sector is a headline thesis, or the firm has a dedicated fund or partner for it. Warmest first contacts.
- Tier B, adjacent or infrastructure investors: portfolio shows companies solving a neighbouring problem, or a stated thesis on the infrastructure the company builds on.
- Tier C, angle-specific: a regulatory, geographic or customer-segment angle that matches the company profile (for example investors based in the founder's home region, or with expertise in the rules the company works under).

Tier A gets sector-specific hooks, B gets thesis or infrastructure hooks, C gets the angle hook.

## Optional activity check

Before outreach, optionally keep only people with recent public activity (posts or deals in roughly the last 90 days). Respect rate limits of whatever network you use; read one profile at a time, never in bulk, and stop when the limit is near. Skip this step if it risks the founder's account.

## Import

Return results as rows for `raise_import`, one per person:

`name, role, firm, tier, firm_url, source_url, cheque_range (if self-reported, label it), notes`

Dedupe by person (normalised name plus firm), never by firm domain. Add `raise_evidence_add` records for each deal and thesis found, with `source_url`. Report counts per tier and what was left unverified.
