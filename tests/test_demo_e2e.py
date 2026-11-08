import json
import re
from types import SimpleNamespace

import yaml
from conftest import ROOT, fresh
from fake_ctx import FakeCtx

import raiseplug
from raiseplug import gates, lint, store, tools

EMAIL_TOOL = re.compile(r"gmail|mail|draft", re.I)


def boot(tmp_path, llm=None):
    ctx = FakeCtx(llm=llm)
    raiseplug.register(ctx)
    db = fresh()
    tools.configure(ctx=ctx, db=db, data_dir=tmp_path)
    tools._rt["cfg"].clear()

    def call(name, **args):
        return json.loads(ctx.tools[name](args))
    return ctx, db, call


def test_manifest_matches_registered_tools(tmp_path):
    ctx, _, _ = boot(tmp_path)
    manifest = yaml.safe_load(open(f"{ROOT}/plugin.yaml", encoding="utf-8"))
    assert set(manifest["provides_tools"]) == set(ctx.tools)
    assert len(ctx.tools) == 20 and len(ctx.skills) == 8 and len(ctx.blueprints) == 3
    assert set(ctx.hooks) == {"pre_tool_call", "post_tool_call", "pre_llm_call"} == set(manifest["provides_hooks"])
    assert "raise" in ctx.commands and "raise" in ctx.cli


def test_demo_end_to_end(tmp_path):
    ctx, db, call = boot(tmp_path)
    assert call("raise_demo", action="load")["ok"]
    assert call("raise_rank", all_demo=True)["ranked"] == 40
    focus = call("raise_focus", n=10)["focus"]
    assert len(focus) == 10

    out = call("raise_draft", top=10)
    drafts, refused = out["drafts"], out["refused"]
    print(f"\nDRAFTED {len(drafts)} (blocked {out['counts']['blocked']}), REFUSED {len(refused)}")
    for r in refused:
        print("  refused:", r["who"], "|", r["reasons"][0][:90])
    for x in drafts:
        print("  drafted:", x["who"], x["channel"], x["status"])
    reasons = {r["who"]: " ".join(r["reasons"]) for r in refused}
    assert "pending" in reasons["Maja Sterner"]
    assert "passed" in reasons["Clara Mattson"]
    assert len(drafts) + len(refused) == 10 and drafts

    assert all(x["status"] in ("approved", "placed") for x in drafts)
    for x in drafts:  # email drafts are placed as files in demo; LinkedIn/intro stay approved, to paste
        assert x["status"] == ("placed" if x["channel"] in ("email", "firm_inbox") else "approved"), x
    for x in drafts:  # re-lint every draft against its own evidence
        if x["channel"] == "connect":  # connect requests carry no note
            assert x["writer"] == "none" and "no note" in x["body"]
            continue
        t = store.target_full(db, x["target_id"])
        facts = [e["claim"] for e in tools.ev_list(db, t["id"], t["firm_id"])]
        verified = [v for c in store.verified_claims(db) for v in (c["text"], c["value"]) if v]
        assert lint.lint(x["body"], channel=x["channel"], verified=verified, facts=facts,
                         round_amount=1500000)["ok"], x["body"]
        assert "410" not in x["body"] and "[" not in x["body"], x["body"]  # no placeholder names

    r = call("raise_replies_check")
    print("REPLIES:", [(x["who"], x["verdict"], x["applied"]) for x in r["replies"]])
    assert r["replies"][0]["who"] == "Matthias Eberle" and r["replies"][0]["verdict"] == "interest"
    assert {x["verdict"] for x in r["replies"]} == {"interest", "soft_pass", "out_of_office", "question"}
    assert call("raise_replies_check")["new"] == 0  # idempotent

    brief = call("raise_brief")
    print("BRIEF:", [(a["type"], a["who"]) for a in brief["actions"]])
    assert brief["actions"][0]["who"] == "Matthias Eberle" and len(brief["actions"]) <= 5

    before = db.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
    ctx.dispatched.clear()
    f = call("raise_find", firm="Northwind Ventures", urls=["demo:injection"])
    assert f["ok"] and "untrusted_data" in f["pages"][0]["untrusted_page"]
    assert db.execute("SELECT COUNT(*) FROM drafts").fetchone()[0] == before
    assert not [n for n, _ in ctx.dispatched if EMAIL_TOOL.search(n)]
    assert not [n for n, _ in ctx.dispatched if EMAIL_TOOL.search(n) and n != "skill_view"]  # no mailbox call in demo, ever


def test_pass_spares_colleagues_and_log(tmp_path):
    ctx, db, call = boot(tmp_path)
    call("raise_demo", action="load")
    ada = tools._find_target(db, "Northwind Ventures", "Ada Lindqvist")
    jonas = tools._find_target(db, "Northwind Ventures", "Jonas Brandt")
    r = call("raise_log", target_id=jonas, kind="pass", summary="no")
    assert r["ok"] and r["passed"] == "Jonas Brandt"
    assert store.target_full(db, ada)["stage"] == "in_talks"
    r = call("raise_log", target_id=ada, kind="soft_pass")
    assert r["revisit_at"]


def test_llm_draft_with_unverified_number_is_rewritten(tmp_path):
    calls = []

    class FakeLlm:
        def complete(self, messages, *, purpose=None, max_tokens=None):
            calls.append(messages)
            t = store.target_full(db, tid)
            hook = tools.hook_fact(db, t)["claim"].rstrip(".")
            first = t["person_name"].split()[0]
            if len(calls) == 1:
                body = (f"Subject: Tidewell\nHi {first},\n\n{hook}. Tidewell has EUR 410k ARR in 38 clinics.\n\n"
                        "Would you be open to a short call next week?\n\nBest,\nAnna")
            else:
                body = (f"Subject: Tidewell and {t['firm_name']}\nHi {first},\n\n{hook}. Tidewell is live in 38 independent "
                        "clinics across Sweden and Denmark.\n\nWould you be open to a short call next week?\n\nBest,\nAnna")
            return SimpleNamespace(text=body)

    ctx, db, call = boot(tmp_path, llm=FakeLlm())
    call("raise_demo", action="load")
    call("raise_rank", all_demo=True)
    tid = next(f["target_id"] for f in call("raise_focus", n=10)["focus"] if call("raise_can_draft", target_id=f["target_id"])["ok"])
    out = call("raise_draft", target_ids=[tid])
    d = out["drafts"][0]
    print("\nCAUGHT:", d["caught_by_lint"])
    assert d["writer"] == "llm" and d["rewritten"] and len(calls) == 2
    assert any("unverified_number" in c and "410" in c for c in d["caught_by_lint"])
    assert "410" not in d["body"] and d["status"] in ("approved", "placed")
    assert db.execute("SELECT body FROM drafts WHERE target_id = ?", (tid,)).fetchone()["body"] == d["body"]


def test_draft_keeps_one_message_and_redo_replaces_it(tmp_path):
    class FakeLlm:  # copies another investor's email out of the instructions, as a live model did
        def complete(self, messages, *, purpose=None, max_tokens=None):
            t = store.target_full(db, tid)
            hook = tools.hook_fact(db, t)["claim"].rstrip(".")
            return SimpleNamespace(text=f"Subject: Hi\nHi {t['person_name'].split()[0]},\n\n{hook}.\n\nOpen to a call?"
                                        "\n\nSubject: Other\n\nHi Bob,\n\nSomething for Bob.\n\nOpen to a call?")

    ctx, db, call = boot(tmp_path, llm=FakeLlm())
    call("raise_demo", action="load")
    call("raise_rank", all_demo=True)
    tid = next(f["target_id"] for f in call("raise_focus", n=10)["focus"] if call("raise_can_draft", target_id=f["target_id"])["ok"])
    d = call("raise_draft", target_ids=[tid])["drafts"][0]
    assert "Bob" not in d["body"] and "Subject" not in d["body"]
    db.execute("UPDATE drafts SET status = 'approved'")  # not yet in the mailbox
    refused = call("raise_draft", target_ids=[tid])["refused"][0]["reasons"][0]
    assert "redo=true" in refused
    assert call("raise_draft", target_ids=[tid], redo=True)["drafts"]
    assert [r[0] for r in db.execute("SELECT status FROM drafts ORDER BY id")] == ["discarded", "approved"]


def test_unattended_setup_and_import_mapping(tmp_path):
    ctx, db, call = boot(tmp_path)
    ctx.cron = object()
    assert "needs_human" in call("raise_setup")
    ctx.cron = None
    q = call("raise_setup")
    assert q["question_id"] == "backend" and q["options"][0]["value"] == "sqlite" or q["options"]
    r = call("raise_setup", question_id="backend", answer="notion")
    assert "Notion MCP" in r["note"] and ctx.config["backend"] == "sqlite"
    csv_path = tmp_path / "x.csv"
    csv_path.write_text("Foo,Bar\n1,2\n", encoding="utf-8")
    assert "needs_mapping" in call("raise_import", csv_path=str(csv_path))
    ok = tmp_path / "ok.csv"
    ok.write_text("Company,Name,Email Address\nAcme Ventures,Jo Smith,jo@acme.example\n,Solo Angel,\n", encoding="utf-8")
    r = call("raise_import", csv_path=str(ok))
    assert r["created"] == 2 and call("raise_import", csv_path=str(ok))["updated"] == 2


def test_model_alone_cannot_apply_a_firm_wide_pass():
    from raiseplug import replies

    class Llm:
        def __init__(self, verdict):
            self.v = verdict

        def complete_structured(self, **kw):
            return SimpleNamespace(parsed={"verdict": self.v, "quote": "", "confidence": "high"})

    soft = "Thanks Anna. It is too early for us; come back when you have 12 months of revenue."
    r = replies.classify(soft, SimpleNamespace(llm=Llm("pass")))
    assert r["verdict"] == "soft_pass" and "too early" in r["quote"]
    r = replies.classify("Thanks, we will look at the deck next week.", SimpleNamespace(llm=Llm("pass")))
    assert r["verdict"] == "pass" and r["confidence"] == "low"  # reported, not applied
    r = replies.classify("We will pass, not a fit for the fund.", SimpleNamespace(llm=Llm("pass")))
    assert r["verdict"] == "pass"


def test_export_carries_drafts_for_chosen_investors(tmp_path):
    ctx, db, call = boot(tmp_path)
    call("raise_demo", action="load")
    call("raise_rank", all_demo=True)
    out = call("raise_draft", top=3)
    ids = [x["target_id"] for x in out["drafts"]][:2]
    rows = call("raise_export", target_ids=ids)["rows"]
    assert len(rows) == 2 and all(r["draft_body"] and r["draft_status"] for r in rows)


def test_demo_and_real_data_never_mix(tmp_path):
    ctx, db, call = boot(tmp_path)
    call("raise_demo", action="load")
    blocked = call("raise_profile_set", fields={"name": "Real Co"})
    assert not blocked["ok"] and "demo clear" in blocked["error"]
    assert "demo clear" in call("raise_import", rows=[{"firm": "Real Fund", "person": "Real Person"}])["error"]
    q = call("raise_setup")
    assert q["question_id"] == "clear_demo"
    assert call("raise_setup", question_id="clear_demo", answer="no")["done"]
    assert store.meta_get(db, "demo_loaded")  # kept
    q = call("raise_setup", question_id="clear_demo", answer=1)
    assert q["note"] == "Demo cleared." and q["question_id"] == "backend"
    assert db.execute("SELECT COUNT(*) FROM targets").fetchone()[0] == 0
    assert call("raise_import", rows=[{"firm": "Real Fund", "person": "Real Person"}])["ok"]
    assert not call("raise_demo", action="load")["ok"]  # never loads over real data
    assert not call("raise_demo", action="clear")["ok"]  # never deletes real data
    assert db.execute("SELECT COUNT(*) FROM targets").fetchone()[0] == 1


def test_setup_command_uses_picker_then_hands_over(tmp_path):
    from raiseplug import cli
    ctx, db, call = boot(tmp_path)
    asked, injected = [], []
    ctx.ask_choice = lambda q, choices: asked.append(q) or choices[0]["value"]
    ctx.inject_message = lambda msg, session_key=None: injected.append((msg, session_key)) or True
    out = cli.command("setup", session_key="s1")
    assert len(asked) == 3 and "Handing over" in out  # backend, email, linkedin picked
    assert injected == [(cli.HANDOVER, "s1")]
    assert call("raise_setup")["question_id"] == "profile_ingest"


def test_setup_command_text_fallback(tmp_path):
    from raiseplug import cli
    ctx, db, call = boot(tmp_path)
    ctx.ask_choice = lambda q, choices: None  # no picker on this surface
    assert "/raise setup <number>" in cli.command("setup")
    cli.command("setup 1")
    assert call("raise_setup")["question_id"] == "email"


def test_bare_url_after_setup_question_reaches_the_model_as_an_answer(tmp_path):
    from raiseplug import cli
    ctx, db, call = boot(tmp_path)
    ctx.ask_choice = lambda q, choices: choices[0]["value"]
    ctx.inject_message = lambda msg, session_key=None: False  # gateway injection not allowed (the default)
    assert "Reply here in chat" in cli.command("setup")
    hook = ctx.hooks["pre_llm_call"]
    hook = hook[0] if isinstance(hook, list) else hook
    out = hook(user_message="https://example.com")
    assert "Paste your deck text" in out["context"] and "question_id='profile_ingest'" in out["context"]
    call("raise_setup", question_id="profile_ingest", answer="done")  # next step: the interview, still free text
    assert "skeptical-investor interview" in hook(user_message="ok")["context"]
    call("raise_setup", question_id="grill", answer="skip")
    q = call("raise_setup")
    assert q["question_id"] == "writing_skills" and hook(user_message="what's the weather") is None
    n = next(o["n"] for o in q["options"] if o["value"] == "none")
    assert call("raise_setup", question_id="writing_skills", answer=n).get("done")  # an int, as models send it


def test_voice_skill_match_ignores_unrelated_names():
    names = ["songwriting-and-ai-music", "writing-voice", "brand_tone", "humanizer", "raise:voice"]
    assert [n for n in names if tools.VOICE_RE.search(n)] == ["writing-voice", "brand_tone", "raise:voice"]


def test_next_step_walks_find_research_rank(tmp_path):
    from raiseplug import cli
    ctx, db, call = boot(tmp_path)
    steps = lambda: [a["type"] for a in call("raise_brief")["actions"]]  # noqa: E731
    assert steps() == ["find"] and "raise:discover" in cli.command("next")
    r = call("raise_import", rows=[{"firm": "Alpha Fund", "person": "Ann One"}, {"firm": "Beta Fund", "person": "Bo Two"}])
    assert "2 investors: not researched" in r["next"] and "Ann One (Alpha Fund)" in r["next"] and steps() == ["research"]
    tid = db.execute("SELECT t.id FROM targets t JOIN people p ON p.id = t.person_id WHERE p.name = 'Ann One'").fetchone()[0]
    call("raise_evidence_add", target_id=tid, kind="thesis", claim="Backs fintech", source_url="https://a.example")
    assert steps() == ["research"]  # a typed-in search snippet is not research
    eid = tools.add_evidence(db, tid, None, 1, kind="thesis", claim="Backs fintech", source_url="https://a.example/about")
    assert steps() == ["research", "rank"]  # Bo still unresearched, Ann read and ready to rank
    r = call("raise_rank", target_id=tid, dims={"thesis": {"score": 8, "evidence_ids": [eid], "why": "fintech"}})
    assert "1 investor: not researched" in r["next"] and steps() == ["research", "contact"]  # Ann ranked, unreachable
    call("raise_import", rows=[{"firm": "Alpha Fund", "person": "Ann One", "email": "ann@alpha.example",
                                "email_status": "confirmed"}])
    assert steps() == ["research", "new_outreach"]
    hook = ctx.hooks["pre_llm_call"]
    hook = hook[0] if isinstance(hook, list) else hook
    assert "Next step: 1 investor: not researched" in hook(user_message="do my next Raise steps")["context"]


def test_research_that_extracts_nothing_says_so_and_stays_unresearched(tmp_path, monkeypatch):
    from raiseplug import connectors

    class TimesOut:
        def complete_structured(self, **kw):
            assert kw["timeout"] >= 120
            raise TimeoutError("Request timed out.")
    ctx, db, call = boot(tmp_path, llm=TimesOut())
    real = connectors.detect()
    monkeypatch.setattr(connectors, "detect", lambda names=None: {**real, "web_extract": ["web_extract"]})
    ctx.dispatch_tool = lambda name, args: json.dumps({"content": "Alpha Fund backs fintech seed rounds."})
    call("raise_import", rows=[{"firm": "Alpha Fund", "person": "Ann One"}])
    r = call("raise_find", firm="Alpha Fund", urls=["https://alpha.example"])
    assert not r["ok"] and "TimeoutError" in r["error"] and "does not count" in r["error"]
    assert [a["type"] for a in call("raise_brief")["actions"]] == ["research"]


def test_ranking_from_snippets_is_redone_after_research(tmp_path):
    ctx, db, call = boot(tmp_path)
    call("raise_import", rows=[{"firm": "Alpha Fund", "person": "Ann One", "email": "ann@alpha.example",
                                "email_status": "confirmed"}])
    tid = db.execute("SELECT id FROM targets").fetchone()[0]
    snip = call("raise_evidence_add", target_id=tid, kind="thesis", claim="Backs fintech", source_url="https://s.example")
    call("raise_rank", target_id=tid, dims={"thesis": {"score": 6, "evidence_ids": [snip["evidence_id"]], "why": "snippet"}})
    tools.add_evidence(db, tid, None, 1, kind="thesis", claim="Leads fintech seeds", source_url="https://alpha.example")
    assert [a["type"] for a in call("raise_brief")["actions"]] == ["rank", "new_outreach"]  # re-rank comes first


def test_contact_scan_reads_the_firms_own_site(tmp_path, monkeypatch):
    from raiseplug import connectors, contacts
    contacts._demo()
    ctx, db, call = boot(tmp_path)
    real = connectors.detect()
    monkeypatch.setattr(connectors, "detect", lambda names=None: {**real, "web_extract": ["web_extract"]})
    site = {"https://northfund.com": "We back seed founders. [Contact](https://northfund.com/contact) [Pitch](https://northfund.typeform.com/to/x)",
            "https://northfund.com/contact": "Pitch us at pitch@northfund.com. Ada Lund: ada.lund@northfund.com. ceo@portco.io"}
    url = lambda args: (args.get("urls") or [args.get("url")])[0]  # noqa: E731
    ctx.dispatch_tool = lambda name, args: json.dumps({"content": site.get(url(args), "")})
    call("raise_import", rows=[{"firm": "North Fund", "person": "Ada Lund", "firm_url": "https://northfund.com"}])
    tid = db.execute("SELECT id FROM targets").fetchone()[0]
    assert call("raise_rank", target_id=tid, dims={})["ranking"]["dims"]["reachability"]["score"] == 0
    r = call("raise_find", firm="North Fund", contact_only=True)["contact"]
    assert json.loads(db.execute("SELECT ranking FROM targets").fetchone()[0])["dims"]["reachability"]["score"] > 0
    assert r["inbox"] == "pitch@northfund.com" and r["form"].startswith("https://northfund.typeform.com")
    assert r["person_emails"] == [{"person": "Ada Lund", "email": "ada.lund@northfund.com", "source": "https://northfund.com/contact"}]
    tid = db.execute("SELECT id FROM targets").fetchone()[0]
    assert gates.contact_route(db, tid)["next"] == "email"
    site["https://northfund.com"] = "North Fund Housing: flats to rent. [Contact](https://northfund.com/contact)"
    db.execute("UPDATE firms SET email = NULL, form_url = NULL")
    r = call("raise_find", firm="North Fund", contact_only=True)["contact"]
    assert not r["found"] and "does not read like an investor" in r["why"]
    assert db.execute("SELECT email FROM firms").fetchone()[0] is None


def test_import_by_path_refuses_secrets_but_rows_still_work(tmp_path, monkeypatch):
    ctx, db, call = boot(tmp_path)
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".hermes").mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HERMES_HOME", str(home / ".hermes"))
    secret = home / ".hermes" / ".env"
    secret.write_text("API_KEY=hunter2\n", encoding="utf-8")
    hidden_csv = home / ".ssh" / "list.csv"
    hidden_csv.write_text("Company,Name\nAcme,Jo\n", encoding="utf-8")
    hermes_csv = home / ".hermes" / "list.csv"
    hermes_csv.write_text("Company,Name\nAcme,Jo\n", encoding="utf-8")
    for bad in (secret, hidden_csv, hermes_csv, tmp_path / "missing.csv"):
        r = call("raise_import", csv_path=str(bad))
        assert r["ok"] is False and "hunter2" not in json.dumps(r), bad
    assert call("raise_import", linkedin_connections_csv=str(secret))["ok"] is False
    good = home / "investors.csv"
    good.write_text("Company,Name\nAcme Ventures,Jo Smith\n", encoding="utf-8")
    assert call("raise_import", csv_path=str(good))["created"] == 1
    # Notion / CRM / any tool hands over rows: no file path involved, unchanged
    assert call("raise_import", rows=[{"person": "Ann Lee", "firm": "Beta Capital"}])["ok"] is True
