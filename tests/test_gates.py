from datetime import datetime, timedelta

from conftest import fresh
from raiseplug import gates
from raiseplug import store as s

NOW = datetime(2026, 11, 11, 12, 0)  # a Wednesday
PROFILE = {"round_amount": 1_000_000, "stage": "pre-seed", "geo": ["sweden", "nordics", "europe"]}


def ago(days):
    return NOW - timedelta(days=days)


def touch(db, tid, channel, days, direction="out"):
    kind = "touch" if direction == "out" else "reply"
    s.log_event(db, kind, tid, channel=channel, direction=direction, at=ago(days), ref=f"{tid}-{channel}-{days}-{direction}")


def person_target(db, firm="North Fund", person="Ada Lund", kind="vc", **pf):
    fid = s.upsert_firm(db, firm, kind=kind)
    pid = s.upsert_person(db, person, fid, **pf)
    return s.upsert_target(db, fid, pid, stage="ready")


def check(db, tid):
    return gates.can_draft(db, tid, now=NOW)


def test_workdays_back_skips_weekend():
    assert gates.workdays_back(NOW, 3) == datetime(2026, 11, 6, 12, 0)  # Wed -> Fri
    assert gates.add_workdays(datetime(2026, 11, 6, 9), 1) == datetime(2026, 11, 9, 9)  # Fri -> Mon


def test_gate_walkthrough_single_target():
    db = fresh()
    tid = person_target(db, email="ada@north.example")
    r = check(db, tid)
    assert not r["ok"] and any("route" in x for x in r["reasons"])  # unconfirmed email, no LinkedIn

    db.execute("UPDATE people SET email_status = 'confirmed'")
    r = check(db, tid)
    assert r["ok"] and r["mode"] == "cold" and r["channel"] == "email", r

    touch(db, tid, "email", 1)
    r = check(db, tid)
    assert not r["ok"] and any("working days" in x for x in r["reasons"]), r

    db.execute("DELETE FROM events")
    touch(db, tid, "email", 8)
    r = check(db, tid)
    assert r["ok"] and r["mode"] == "follow_up" and r["channel"] == "email", r

    touch(db, tid, "email", 30)
    touch(db, tid, "email", 60)
    r = check(db, tid)
    assert not r["ok"] and any("3 touches" in x for x in r["reasons"]), r

    touch(db, tid, "email", 2, direction="in")  # they replied
    r = check(db, tid)
    assert r["ok"] and r["mode"] == "reply", r  # reply mode is exempt from caps and cool-down

    db.execute("UPDATE people SET do_not_contact = 1")
    r = check(db, tid)
    assert not r["ok"] and any("do-not-contact" in x for x in r["reasons"])


def test_rule_of_three_moves_to_next_channel():
    db = fresh()
    fid = s.upsert_firm(db, "North Fund", kind="vc", email="hello@north.example")
    pid = s.upsert_person(db, "Ada Lund", fid, email="ada@north.example", email_status="confirmed")
    tid = s.upsert_target(db, fid, pid, stage="contacted")
    for d in (10, 30, 60):
        touch(db, tid, "email", d)
    r = check(db, tid)
    assert r["ok"] and r["channel"] == "firm_inbox", r


def test_named_person_required():
    db = fresh()
    fid = s.upsert_firm(db, "North Fund", kind="vc", email="hello@north.example")
    tid = s.upsert_target(db, fid, None, stage="ready")
    r = check(db, tid)
    assert not r["ok"] and any("named person" in x for x in r["reasons"])

    for bad in ("North Fund", "Ada Lund; Bo Berg", "Ada Lund (and team)"):
        pid = s.upsert_person(db, bad, fid, email="x@north.example", email_status="confirmed")
        t2 = s.upsert_target(db, fid, pid, stage="ready")
        assert not check(db, t2)["ok"], bad


def test_firm_pass_is_firm_wide_but_spares_talks():
    db = fresh()
    a = person_target(db, person="Ada Lund", email="a@n.example", email_status="confirmed")
    b = person_target(db, person="Bo Berg", email="b@n.example", email_status="confirmed")
    c = person_target(db, person="Cy Dahl", email="c@n.example", email_status="confirmed")
    db.execute("UPDATE targets SET stage = 'passed' WHERE id = ?", (a,))
    db.execute("UPDATE targets SET stage = 'in_talks' WHERE id = ?", (c,))
    touch(db, c, "email", 10, direction="in")
    r = check(db, b)
    assert not r["ok"] and any("passed" in x for x in r["reasons"]), r
    assert check(db, c)["ok"]  # colleague in live talks is kept


def test_angel_group_pass_is_not_firm_wide():
    db = fresh()
    a = person_target(db, firm="Angel Circle", person="Ada Lund", kind="angel_group", email="a@x.example", email_status="confirmed")
    b = person_target(db, firm="Angel Circle", person="Bo Berg", kind="angel_group", email="b@x.example", email_status="confirmed")
    db.execute("UPDATE targets SET stage = 'passed' WHERE id = ?", (a,))
    assert check(db, b)["ok"]


def test_firm_hold_when_colleague_touched_recently():
    db = fresh()
    a = person_target(db, person="Ada Lund", email="a@n.example", email_status="confirmed")
    b = person_target(db, person="Bo Berg", email="b@n.example", email_status="confirmed")
    touch(db, a, "email", 5)
    r = check(db, b)
    assert not r["ok"] and any("colleague" in x for x in r["reasons"]), r
    db.execute("DELETE FROM events")
    touch(db, a, "email", 20)
    assert check(db, b)["ok"]


def test_unsent_draft_blocks_and_next_action_date_blocks():
    db = fresh()
    tid = person_target(db, email="a@n.example", email_status="confirmed")
    db.execute("INSERT INTO drafts (target_id, channel, body, body_sha256, status, created_at) VALUES (?,?,?,?,?,?)",
               (tid, "email", "hi", "x", "draft", s.iso(ago(1))))
    assert any("unsent draft" in x for x in check(db, tid)["reasons"])
    db.execute("DELETE FROM drafts")
    db.execute("UPDATE targets SET next_action_at = ? WHERE id = ?", (s.iso(NOW + timedelta(days=5)), tid))
    assert any("parked" in x for x in check(db, tid)["reasons"])


def test_contact_route_order_and_holds():
    db = fresh()
    tid = person_target(db, email="a@n.example", email_status="confirmed", linkedin="https://linkedin.example/in/ada")
    assert gates.contact_route(db, tid, now=NOW)["next"] == "connect"
    db.execute("UPDATE people SET connected = 1")
    assert gates.contact_route(db, tid, now=NOW)["next"] == "linkedin_dm"
    db.execute("INSERT INTO intro_paths (target_id, via_name, relation) VALUES (?, 'Eva Holm', 'former colleague')", (tid,))
    assert gates.contact_route(db, tid, now=NOW)["next"] == "intro"

    touch(db, tid, "intro", 1)  # intro asked yesterday: everything later waits
    r = check(db, tid)
    assert not r["ok"] and any("intro" in x for x in r["reasons"]), r

    db.execute("DELETE FROM events")
    touch(db, tid, "intro", 6)  # 3+ working days of silence: go direct, not another connector
    assert gates.contact_route(db, tid, now=NOW)["next"] == "linkedin_dm"


def test_pending_connect_waits_then_email():
    db = fresh()
    tid = person_target(db, email="a@n.example", email_status="confirmed", linkedin="https://linkedin.example/in/ada")
    touch(db, tid, "connect", 1)
    assert not check(db, tid)["ok"]
    db.execute("DELETE FROM events")
    touch(db, tid, "connect", 6)
    r = check(db, tid)
    assert r["ok"] and r["channel"] == "email", r


# ---------- firm gates ----------

def ev(db, fid, kind, claim="x", **f):
    cols = {"firm_id": fid, "kind": kind, "claim": claim, "source_url": "https://e.example", "fetched": 1, **f}
    db.execute(f"INSERT INTO evidence ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", tuple(cols.values()))


def test_missing_evidence_is_unknown_never_fail():
    db = fresh()
    fid = s.upsert_firm(db, "North Fund", kind="vc")
    g = gates.evaluate_gates(db, fid, PROFILE, now=NOW)
    assert g["overall"] == "unknown"
    assert all(c["status"] == "unknown" for c in g["checks"].values()), g


def test_gates_pass_and_fail_on_clear_evidence():
    db = fresh()
    fid = s.upsert_firm(db, "North Fund", kind="vc")
    ev(db, fid, "deal", date=s.iso(ago(60)), stage="seed", relevant=1, country="sweden")
    g = gates.evaluate_gates(db, fid, PROFILE, now=NOW)
    assert g["overall"] == "pass", g
    for c in ("active", "stage", "fit", "geography"):
        assert g["checks"][c]["status"] == "pass", (c, g)

    ev(db, fid, "cheque", amount=2_000_000)
    assert gates.evaluate_gates(db, fid, PROFILE, now=NOW)["checks"]["size"]["status"] == "fail"


def test_active_fails_only_with_two_old_deals_and_never_for_angels():
    db = fresh()
    fid = s.upsert_firm(db, "Old Fund", kind="vc")
    ev(db, fid, "deal", date=s.iso(ago(700)))
    assert gates.evaluate_gates(db, fid, PROFILE, now=NOW)["checks"]["active"]["status"] == "unknown"
    ev(db, fid, "deal", date=s.iso(ago(800)))
    assert gates.evaluate_gates(db, fid, PROFILE, now=NOW)["checks"]["active"]["status"] == "fail"

    aid = s.upsert_firm(db, "Solo Angel", kind="angel")
    ev(db, aid, "deal", date=s.iso(ago(700)))
    ev(db, aid, "deal", date=s.iso(ago(800)))
    assert gates.evaluate_gates(db, aid, PROFILE, now=NOW)["checks"]["active"]["status"] == "unknown"


def test_geography_exclusive_and_exclusion_and_override():
    db = fresh()
    fid = s.upsert_firm(db, "US Only", kind="vc")
    ev(db, fid, "geography", country="united states", exclusive=1)
    assert gates.evaluate_gates(db, fid, PROFILE, now=NOW)["checks"]["geography"]["status"] == "fail"

    xid = s.upsert_firm(db, "No Consumer", kind="vc")
    ev(db, xid, "exclusion", claim="does not invest in our sector", relevant=1)
    assert gates.evaluate_gates(db, xid, PROFILE, now=NOW)["overall"] == "fail"
    db.execute("UPDATE evidence SET relevant = 0 WHERE firm_id = ?", (xid,))
    assert gates.evaluate_gates(db, xid, PROFILE, now=NOW)["overall"] != "fail"


def test_stage_fails_only_with_three_staged_deals_none_near():
    db = fresh()
    fid = s.upsert_firm(db, "Growth Co", kind="vc")
    for d in (30, 60):
        ev(db, fid, "deal", date=s.iso(ago(d)), stage="series-c")
    assert gates.evaluate_gates(db, fid, PROFILE, now=NOW)["checks"]["stage"]["status"] == "unknown"
    ev(db, fid, "deal", date=s.iso(ago(90)), stage="growth")
    assert gates.evaluate_gates(db, fid, PROFILE, now=NOW)["checks"]["stage"]["status"] == "fail"
