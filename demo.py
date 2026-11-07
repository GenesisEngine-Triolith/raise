"""Load or wipe the fictional Tidewell demo set (company, 40 investors, evidence, history, rankings)."""
import json
from datetime import timedelta

from . import gates, store, tools

DEMO = tools.HERE / "demo"


def _load_json(name):
    return json.loads((DEMO / name).read_text(encoding="utf-8"))


def _key(firm, person):
    return f"{firm or ''}|{person}"


def load(d):
    if d.execute("SELECT COUNT(*) FROM targets").fetchone()[0] and not store.meta_get(d, "demo_loaded"):
        return {"ok": False, "error": "This database already holds real investors. Demo load would wipe them; "
                "run 'hermes raise delete' first if you really want a clean start."}
    tools.wipe(d)
    co, inv = _load_json("company.json"), _load_json("investors.json")
    store.profile_set(d, co["profile"])
    for c in co["claims"]:
        store.add_claim(d, c["text"], c["tag"], c.get("value"), c.get("source"))
    now = store.iso(store.utcnow())
    for b, c in co["branches"].items():
        d.execute("INSERT INTO branches (branch, status, completeness, updated_at) VALUES (?,?,?,?)",
                  (b, "done" if c >= 80 else "open", c, now))
    d.commit()
    res = tools.import_rows(d, inv, source="demo")
    tkeys = {_key(i["firm"], i["person"]): tools._find_target(d, i["firm"], i["person"]) for i in inv}
    ekeys = {}
    for e in _load_json("evidence.json"):
        fid = None
        if e["firm"]:
            fid = d.execute("SELECT id FROM firms WHERE name_key = ?", (store.name_key(e["firm"]),)).fetchone()["id"]
        tid = tkeys[_key(e["firm"], e["person"])] if e["person"] else None
        ekeys[e["key"]] = tools.add_evidence(d, tid, None if tid else fid, 1, **{k: e.get(k) for k in tools.EV_FIELDS})
    for h in _load_json("history.json"):
        store.log_event(d, h["kind"], tkeys[_key(h["firm"], h["person"])], h["channel"], h["direction"], h["summary"],
                        at=store.utcnow() - timedelta(days=h["days_ago"]))
    store.meta_set(d, "demo_evidence_keys", json.dumps(ekeys))
    store.meta_set(d, "demo_target_keys", json.dumps(tkeys))
    store.meta_set(d, "demo_loaded", "1")
    tools.set_cfg("demo_mode", True)
    ranked = json.loads(tools.t_rank({"all_demo": True}))
    prof = tools._profile(d)
    for r in d.execute("SELECT id FROM firms").fetchall():
        gates.apply_gates(d, r["id"], prof)
    return {"ok": True, "demo_mode": True, "company": co["profile"]["name"], "investors": res["created"],
            "evidence": len(ekeys), "ranked": ranked.get("ranked"),
            "next": "Ranking is done. Run raise_focus, then raise_draft with top=10."}


def reset(d):
    tools.wipe(d)
    tools.set_cfg("demo_mode", False)
    return {"demo_mode": False, "message": "All Raise data wiped."}
