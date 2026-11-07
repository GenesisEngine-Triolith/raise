# Raise

A fundraising desk for Hermes Agent: it learns your company, ranks investors on cited evidence, drafts outreach into your mailbox, and refuses what it shouldn't do. It never sends.

## A skill can suggest. A plugin can refuse.

A prompt can tell a model to be careful. Raise puts the rules in code, in hooks and tool handlers the model cannot talk its way past.

- **Draft gate.** `raise_can_draft` runs before any draft is written. It refuses when:
  - the target is archived, excluded, passed or committed, or marked do-not-contact;
  - there is no named person (Raise drafts to a person, never to a firm), or the "name" looks like a firm or like several people;
  - a colleague at the same firm passed (a pass applies to the whole firm), is in talks, or was contacted in the last 14 days (one conversation per firm);
  - the last touch is less than 3 working days old, or the target is parked until a later date;
  - an earlier draft for this person is still unsent;
  - the firm failed a firm gate (stage, cheque size, geography, an exclusion, no recent activity);
  - there is no open contact route left.

  Routes run in a fixed order: warm intro, LinkedIn DM (if connected), connect request, email (confirmed address only), firm inbox. Three touches per channel in 180 days, then it moves on.
- **Evidence-first scoring.** The model proposes a 0 to 10 score per dimension and cites evidence ids. A dimension with no valid citation is set to 0. Code computes the total from fixed weights, and reachability comes from the contact route, not from the model.
- **Claim check.** After the model writes a draft, `lint` compares every number in it against your verified claims and the investor's cited facts. An unverified figure (say, an ARR number from a deck that you never confirmed) blocks the draft. So does a draft with no investor-specific fact. One rewrite pass runs on style warnings (stock phrases, em dashes, "not X but Y", missing closing question, too long) and the draft is checked again.
- **LinkedIn caps and pause.** Profile views, reads and messages have daily caps, jittered per day. Writes are off by default. A login, checkpoint or rate-limit error in a LinkedIn tool result pauses all LinkedIn tools for 72 hours.
- **Email guard.** A `pre_tool_call` hook looks at any mail tool aimed at an address in your pipeline. Sending (send, reply, forward) to an investor is always refused. Creating a draft is allowed only when the body matches a draft Raise already approved (sha256 of the text). Mail to anyone else is not touched.

## Quick start

```
hermes plugins install GenesisEngine-Triolith/raise
hermes plugins enable raise
```

1. `/raise demo` loads a fictional company and 40 invented investors. No accounts, no network. You can rank, draft, check replies and see the daily brief right away.
2. `/raise setup` starts onboarding for your own company.
3. Ask: "draft emails for my top 10".
4. `/raise next` shows today's actions.

## What it does

- **Onboarding and grill.** Asks where your pipeline lives, how email and LinkedIn should work, then reads your deck, URL or notes into a draft profile. The `raise:grill` skill interviews you across 13 branches (problem, customer, traction, round, ideal investor and so on) and saves after every answer. Each gap comes with a plain consequence, for example "Traction 40%: drafts can only cite verified traction facts."
- **Import.** CSV, a LinkedIn `Connections.csv`, or rows your agent reads from Notion, Sheets, Airtable or HubSpot using your own Hermes tools. The built-in SQLite database is the engine. People are deduplicated by person, not by firm domain. A person with no firm is an angel. Connections at a pipeline firm become intro paths.
- **Research.** Uses whatever `web_search` and `web_extract` tools you already have. Facts are stored with a source URL and only kept if that URL was fetched in the same call. Firm gates then mark each check pass, fail or unknown. Missing evidence is unknown, never fail.
- **Rank.** Nine weighted dimensions. `raise_explain` shows the score, the cited evidence and the gate result for any investor. `raise_focus` returns your top N, one person per firm.
- **Draft.** Writes with layered skills: bundled `raise:draft` and `raise:humanizer`, then your own `draft_skills`, then the lint above. Approved drafts go into your mailbox as drafts, however you connect your mail: an MCP server or plugin tool that creates drafts (Gmail, Google Workspace, Outlook/M365, raw-MIME Gmail API tools) is called directly; with only a skill or CLI, Raise saves the checked body to `raise-outbox/<id>.txt` and the agent makes the draft from that file. Send calls to an investor are blocked on every route, including terminal commands. LinkedIn and intro messages stay in Raise for you to paste. Without an LLM, a deterministic template that must also pass lint is used.
- **Replies.** Searches your mailbox for answers from people you contacted and classifies each as pass, soft pass, interest, question, redirect or out of office, with a quote from the message. The quote must exist in the text, or confidence is low and nothing is applied. A pass closes the whole firm, except colleagues already in talks.
- **Daily brief.** At most 5 actions: replies to answer, follow-ups due, drafts waiting, top targets ready for a first draft.
- **Automation blueprints.** `daily-brief`, `reply-check` and `weekly-pipeline-review` for Hermes cron. They draft only and never ask questions in unattended runs.

## Tools

| Tool | Use it to |
|---|---|
| `raise_setup` | Step through onboarding (one question per call) |
| `raise_setup_status` | See config, detected tools, counts, profile completeness, LinkedIn pause |
| `raise_profile_get` | Read the profile, claims and branch completeness |
| `raise_profile_set` | Save profile fields, branch answers and tagged claims (verified, unverified, projection) |
| `raise_import` | Import rows, a CSV or a LinkedIn Connections.csv |
| `raise_find` | Research one investor and store cited facts |
| `raise_evidence_add` | Add a fact by hand (source URL required) |
| `raise_evidence_list` | List stored facts for an investor |
| `raise_rank` | Score an investor from model-proposed, evidence-cited dimensions |
| `raise_focus` | Top N open targets that passed the firm gates |
| `raise_explain` | Show why an investor scored what it did |
| `raise_can_draft` | Ask the draft gate before writing anything |
| `raise_draft` | Write, check and place drafts; lists refusals with reasons |
| `raise_log` | Record a touch, reply, pass, soft pass, in talks, committed or note |
| `raise_replies_check` | Fetch and classify replies |
| `raise_brief` | Today's actions |
| `raise_stats` | Counts by stage, gate, draft status, channel and reply |
| `raise_export` | Rows or CSV of the pipeline, each with its latest draft; `target_ids` for just some. Ask "draft two investors and put them in my CRM" and the agent writes the rows with your HubSpot/Pipedrive/Notion/Sheets tool |
| `raise_sync` | Rows changed since the last export, to write to your own tracker |
| `raise_demo` | Load or reset the demo data |

## Commands

| Command | Does |
|---|---|
| `/raise status` | Setup and pipeline status |
| `/raise setup` | Start or resume onboarding |
| `/raise next` | The daily brief as text |
| `/raise drafts` | Drafts waiting for you |
| `/raise replies` | Check replies |
| `/raise demo` | Load the demo |
| `/raise export` | Export the pipeline |
| `/raise delete confirm` | Wipe all Raise data (without `confirm` it only explains) |

CLI: `hermes raise setup`, `doctor`, `export`, `demo`, `delete`. `doctor` checks the database, detected tools, profile completeness, LinkedIn pause state, bundled skills and config.

Bundled skills: `raise:draft`, `raise:humanizer`, `raise:grill`, `raise:voice`, `raise:fact-check`, `raise:validate`, `raise:discover`, `raise:reply-triage`.

## Configuration

Set under `plugins.entries.raise.settings`.

| Key | Default | Meaning |
|---|---|---|
| `backend` | `sqlite` | `sqlite`, `notion`, `sheets`, `airtable`, `hubspot` or `csv`. SQLite is always the engine; others are read and written through your own tools |
| `email_mode` | `none` | `gmail` or `other`: Raise calls your draft tool. `none`: checked drafts go to `raise-outbox/` for your mail skill or for copying |
| `email_draft_tool` | `auto` | Name of your draft-creating email tool, or `auto` to detect |
| `email_search_tool` | `auto` | Name of your mailbox search tool, or `auto` |
| `linkedin_mode` | `off` | `off`, `read_only` or `draft_dms` |
| `linkedin_profile_views_per_day` | `20` | Cap on profile views |
| `linkedin_reads_per_day` | `40` | Cap on other reads |
| `linkedin_messages_per_day` | `0` | Cap on LinkedIn writes (0 means none) |
| `draft_skills` | `[]` | Your own voice or style skills, applied after the bundled ones |
| `founder_name` | `""` | Name used to sign drafts |
| `focus_size` | `10` | Size of the focus list |
| `demo_mode` | `false` | Set by `/raise demo`; places drafts in a local folder instead of a mailbox |

## Safety and disclosures

- **Draft-only.** No send tool exists in Raise. The email guard refuses sends to investors even if another tool or a prompt asks for one.
- **Network.** Raise opens no connections itself. Anything that reaches the network (web search, page fetches, email, Notion, LinkedIn) goes through tools you already have in Hermes, called with `dispatch_tool`, and the LinkedIn and email hooks apply to them.
- **Model calls.** Raise uses your configured Hermes model through `ctx.llm`. Deck text, your profile and the investor facts it works on are sent to that model, so check your provider's terms for confidential material.
- **Local data.** Everything is stored in `<HERMES_HOME>/plugin-data/raise/data.db`. Demo drafts go to `<HERMES_HOME>/plugin-data/raise/demo-drafts/`.
- **No telemetry.** Nothing is reported anywhere.
- **No credentials.** Raise stores no keys or passwords and does not read `.env` files.
- **Untrusted content.** Web pages and email bodies are wrapped as untrusted data, and extraction runs in a model call with no tools. The demo includes a page with a hidden injection to show it being ignored.
- **Unattended runs.** Cron runs never ask questions and never send. When a step needs you, the result says so and waits.
- **Your data, your call.** `/raise export` or `hermes raise export` writes your pipeline out. `/raise delete confirm` or `hermes raise delete` removes it.

## Credits

- `humanizer`: blader/humanizer v3.1.0, MIT licence, Copyright (c) 2025 Siqi Chen. https://github.com/blader/humanizer (bundled unchanged, with its LICENSE file in `humanizer/`).
- Bundled skills grill, voice and fact-check are adapted from community skills of the same names; if you authored one of them, open an issue and we will add your credit and link.
- `validate`, `discover`, `draft` and `reply-triage` are original to Raise.

## License

MIT. Copyright (c) 2026 Triolith. See `LICENSE`.
