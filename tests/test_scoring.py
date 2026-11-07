import pytest

from conftest import fresh
from raiseplug import scoring
from raiseplug import store as s


def setup(kind="vc", person="Ada Lund", firm="North Fund"):
    db = fresh()
    fid = s.upsert_firm(db, firm, kind=kind)
    pid = s.upsert_person(db, person, fid)
    tid = s.upsert_target(db, fid, pid, stage="ready")
    return db, fid, tid


def add_ev(db, fid, kind="deal"):
    return db.execute("INSERT INTO evidence (firm_id, kind, claim, source_url, fetched) VALUES (?,?,?,?,1)",
                      (fid, kind, "fact", "https://e.example")).lastrowid


def full(eid):
    return {d: {"score": 10, "evidence_ids": [eid]} for d in scoring.WEIGHTS}


def test_all_cited_tens_score_100():
    db, fid, tid = setup()
    e = add_ev(db, fid)
    assert scoring.score(db, tid, full(e))["total"] == 100.0


def test_uncited_dimension_is_zeroed():
    db, fid, tid = setup()
    e = add_ev(db, fid)
    dims = full(e)
    dims["thesis"] = {"score": 10, "evidence_ids": []}
    r = scoring.score(db, tid, dims)
    assert r["dims"]["thesis"]["score"] == 0 and "zeroed" in r["dims"]["thesis"]["note"]
    assert r["total"] == 78.0


def test_reachability_needs_no_evidence():
    db, fid, tid = setup()
    r = scoring.score(db, tid, {"reachability": {"score": 10}})
    assert r["dims"]["reachability"]["score"] == 10 and r["total"] == 8.0


def test_evidence_from_another_investor_is_ignored():
    db, fid, tid = setup()
    other = s.upsert_firm(db, "Other Fund", kind="vc")
    e_other = add_ev(db, other)
    r = scoring.score(db, tid, {"thesis": {"score": 9, "evidence_ids": [e_other]}})
    assert r["dims"]["thesis"]["score"] == 0 and "ignored" in r["dims"]["thesis"]["note"]


def test_unknown_dimension_refused():
    db, fid, tid = setup()
    with pytest.raises(ValueError, match="Unknown ranking dimension"):
        scoring.score(db, tid, {"vibes": {"score": 10}})


def test_angel_without_deals_drops_deal_dims_and_renormalises():
    db = fresh()
    pid = s.upsert_person(db, "Ola Angel", None, kind="angel")
    tid = s.upsert_target(db, None, pid, stage="ready")
    e = db.execute("INSERT INTO evidence (target_id, kind, claim, source_url, fetched) VALUES (?,?,?,?,1)",
                   (tid, "thesis", "backs founders in our space", "https://e.example")).lastrowid
    r = scoring.score(db, tid, full(e))
    assert r["dims"]["recency"]["score"] is None and r["dims"]["fund_cycle"]["score"] is None
    assert r["total"] == 100.0  # renormalised over the 78 points kept


def test_focus_one_per_firm_and_skips_failed_and_passed():
    db = fresh()
    f1 = s.upsert_firm(db, "North Fund", kind="vc")
    f2 = s.upsert_firm(db, "South Fund", kind="vc")
    f3 = s.upsert_firm(db, "Angel Circle", kind="angel_group")
    t = {}
    for name, fid, sc, extra in [("A", f1, 90, {}), ("B", f1, 80, {}), ("C", f2, 85, {"gate_status": "fail"}),
                                 ("D", f3, 70, {}), ("E", f3, 60, {}), ("F", f2, 95, {"stage": "passed"})]:
        pid = s.upsert_person(db, name, fid)
        t[name] = s.upsert_target(db, fid, pid, stage=extra.get("stage", "ready"), score=sc,
                                  gate_status=extra.get("gate_status"))
    who = [x["who"] for x in scoring.focus(db, 10)]
    assert who == ["A", "D", "E"]


def test_explain_returns_cited_evidence():
    db, fid, tid = setup()
    e = add_ev(db, fid)
    scoring.set_ranking(db, tid, {"thesis": {"score": 8, "evidence_ids": [f"E{e}"], "why": "matches"}})
    x = scoring.explain(db, tid)
    assert x["rank"] == 1 and x["evidence"][0]["id"] == e and x["dims"]["thesis"]["why"] == "matches"


def test_focus_prefers_colleague_in_talks():
    db = fresh()
    fid = s.upsert_firm(db, "North Fund", kind="vc")
    a = s.upsert_target(db, fid, s.upsert_person(db, "Jo Brandt", fid), stage="ready", score=90)
    b = s.upsert_target(db, fid, s.upsert_person(db, "Ada Lind", fid), stage="in_talks", score=70)
    assert [x["target_id"] for x in scoring.focus(db, 10)] == [b]
