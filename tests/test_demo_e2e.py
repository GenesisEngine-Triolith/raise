import json
import re
from types import SimpleNamespace

import yaml
from conftest import ROOT, fresh
from fake_ctx import FakeCtx

import raiseplug
from raiseplug import lint, store, tools

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
