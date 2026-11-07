"""Rules that decide whether Raise may draft, and which route to use.

Everything here is deterministic code. The model can ask; it cannot argue past a refusal.
All functions take `now` so tests (and replays) are exact.
"""
import json
import re
from datetime import timedelta

from . import store as s

CONVERSATION_CHANNELS = ("linkedin_dm", "email", "firm_inbox", "x")
ROUTE_ORDER = ("intro", "linkedin_dm", "connect", "email", "firm_inbox")
HOLD_WORKDAYS = 3          # a pending touch holds later routes this long
CAP_PER_CHANNEL = 3        # rule of 3: touches per channel, then move on
CAP_WINDOW_DAYS = 180
FIRM_HOLD_DAYS = 14        # one live conversation per firm
DRAFT_OPEN = ("draft", "approved", "placed")

FIRMISH = re.compile(
    r"\b(capital|ventures?|partners|funds?|vc|holdings|investments?|labs|llc|ltd|inc|gmbh)\b", re.I)
SEVERAL = re.compile(r"[;(&/]|\band\b", re.I)


def workdays_back(now, n):
    d = now
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def add_workdays(dt, n):
    d = dt
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _day(dt):
    return dt.strftime("%a %d %b") if dt else "?"


def _touches(db, tid, channel=None, since=None, direction="out"):
    kind = "touch" if direction == "out" else "reply"
    q = "SELECT * FROM events WHERE target_id = ? AND kind = ? AND direction = ?"
    a = [tid, kind, direction]
    if channel:
        q += " AND channel = ?"
        a.append(channel)
    if since:
        q += " AND at >= ?"
        a.append(s.iso(since))
    return [s.row(r) for r in db.execute(q + " ORDER BY at", a)]


def contact_route(db, tid, now=None):
    """Warm intro > LinkedIn DM (if connected) > connect request without note > email > firm inbox/form.

    A pending intro ask or connect request holds every later route for HOLD_WORKDAYS working days.
    After that it goes stale and the route moves on (direct, never to another connector).
    """
    now = now or s.utcnow()
    t = s.target_full(db, tid)
    hold_since = workdays_back(now, HOLD_WORKDAYS)
    cap_since = now - timedelta(days=CAP_WINDOW_DAYS)
    has_paths = db.execute("SELECT 1 FROM intro_paths WHERE target_id = ?", (tid,)).fetchone()

    def last(ch):
        ts = _touches(db, tid, ch)
        return s.parse(ts[-1]["at"]) if ts else None

    def pending(ch):
        lt = last(ch)
        if lt is None:
            return "open", None
        return ("waiting", lt) if lt > hold_since else ("stale", lt)

    steps = []
    for ch in ROUTE_ORDER:
        lt, status, detail = None, "unavailable", ""
        if ch == "intro":
            if has_paths:
                status, lt = pending("intro")
                detail = {"waiting": "intro ask in flight", "stale": "no answer to the intro ask; go direct"}.get(status, "")
            else:
                detail = "no warm path known"
        elif ch == "linkedin_dm":
            status, detail = ("open", "") if t["connected"] else ("unavailable", "not connected")
        elif ch == "connect":
            if t["connected"]:
                detail = "already connected"
            elif t["linkedin"]:
                status, lt = pending("connect")
                detail = {"waiting": "connect request pending", "stale": "connect not accepted yet"}.get(status, "")
            else:
                detail = "no LinkedIn profile"
        elif ch == "email":
            if t["person_email"] and t["email_status"] == "confirmed":
                status = "open"
            else:
                detail = "no confirmed email"
        elif ch == "firm_inbox":
            status, detail = ("open", "") if (t["firm_email"] or t["firm_form"]) else ("unavailable", "no firm inbox or form")
        if status == "open" and len(_touches(db, tid, ch, cap_since)) >= CAP_PER_CHANNEL:
            status, detail = "exhausted", f"{CAP_PER_CHANNEL} touches in {CAP_WINDOW_DAYS} days"
        steps.append({"channel": ch, "status": status, "detail": detail,
                      "since": s.iso(lt) if lt else None,
                      "until": s.iso(add_workdays(lt, HOLD_WORKDAYS)) if status == "waiting" else None})

    nxt = waiting = None
    for st in steps:
        if st["status"] == "waiting":
            waiting = st
            break
        if st["status"] == "open":
            nxt = st["channel"]
            break
    return {"next": nxt, "waiting": waiting, "steps": steps}


def can_draft(db, tid, now=None):
    """The draft gate. Returns {ok, mode, channel, reasons[], warnings[], route}. Any reason blocks."""
    now = now or s.utcnow()
    t = s.target_full(db, tid)
    if not t:
        return {"ok": False, "mode": None, "channel": None, "reasons": [f"Target {tid} not found."],
                "warnings": [], "route": None}
    reasons, warnings = [], []
    firm = t["firm_name"] or "this firm"
    name = t["person_name"]
    who = name or firm
    kind = s.target_kind(t)
    individual = kind in s.INDIVIDUAL_KINDS

    if t["archived"] or t["bucket"] == "exclude":
        reasons.append(f"{who} is archived or excluded.")
    if t["stage"] in ("committed", "passed"):
        reasons.append(f"{who} is marked {t['stage']}.")
    if not t["person_id"]:
        reasons.append(f"No named person at {firm}; Raise only drafts to a person, never to a firm.")
    elif t["firm_name"] and (FIRMISH.search(name) or s.name_key(name) == s.name_key(t["firm_name"])):
        reasons.append(f"'{name}' looks like a firm, not a person.")
    elif SEVERAL.search(name):
        reasons.append(f"'{name}' looks like several people in one record; split it first.")
    if t["do_not_contact"]:
        reasons.append(f"{who} is marked do-not-contact.")

    ins = _touches(db, tid, direction="in")
    outs = [e for e in _touches(db, tid) if e["channel"] in CONVERSATION_CHANNELS]
    last_in = ins[-1] if ins else None
    last_out = outs[-1] if outs else None
    if last_in and (not last_out or last_in["at"] >= last_out["at"]):
        mode = "reply"
    elif last_out:
        mode = "follow_up"
    else:
        mode = "cold"

    colleagues = []
    if t["firm_id"] and not individual:
        colleagues = [s.row(r) for r in db.execute(
            "SELECT t.*, p.name AS person_name FROM targets t LEFT JOIN people p ON p.id = t.person_id "
            "WHERE t.firm_id = ? AND t.id != ?", (t["firm_id"], tid))]
        passed = [c for c in colleagues if c["stage"] == "passed"]
        if passed and t["stage"] != "in_talks" and mode != "reply":
            reasons.append(f"{firm} passed (via {passed[0]['person_name'] or 'the firm'}); a pass applies to the whole firm.")

    route = contact_route(db, tid, now)
    channel = None
    cap_since = now - timedelta(days=CAP_WINDOW_DAYS)
    if mode == "reply":
        channel = last_in["channel"]
    elif mode == "follow_up":
        ch = last_out["channel"]
        at = s.parse(last_out["at"])
        if at > workdays_back(now, HOLD_WORKDAYS):
            reasons.append(f"Last touch ({ch}, {_day(at)}) is still pending; follow up after "
                           f"{_day(add_workdays(at, HOLD_WORKDAYS))} ({HOLD_WORKDAYS} working days).")
        if len(_touches(db, tid, ch, cap_since)) >= CAP_PER_CHANNEL:
            if route["next"]:
                channel = route["next"]
                warnings.append(f"{CAP_PER_CHANNEL} touches on {ch} already; moving to {channel}.")
            else:
                reasons.append(f"{CAP_PER_CHANNEL} touches on {ch} in the last {CAP_WINDOW_DAYS} days "
                               "and no other open route; move on.")
        else:
            channel = ch
    else:
        if route["waiting"]:
            w = route["waiting"]
            reasons.append(f"{w['channel'].replace('_', ' ')} is in flight since {_day(s.parse(w['since']))}; "
                           f"later routes wait until {_day(s.parse(w['until']))} ({HOLD_WORKDAYS} working days).")
        elif route["next"]:
            channel = route["next"]
        else:
            why = "; ".join(f"{st['channel']}: {st['detail']}" for st in route["steps"] if st["detail"])
            reasons.append(f"No open contact route for {who} ({why}).")
        if t["gate_status"] == "fail":
            reasons.append(f"{firm} failed the firm gates: {t['gate_reasons'] or 'see raise_explain'}.")

    open_since = last_out["at"] if last_out else ""
    d = db.execute(
        f"SELECT created_at FROM drafts WHERE target_id = ? AND status IN ({','.join('?' * len(DRAFT_OPEN))}) "
        "AND created_at > ? ORDER BY created_at DESC LIMIT 1", (tid, *DRAFT_OPEN, open_since)).fetchone()
    if d:
        reasons.append(f"There is an unsent draft for {who} from {_day(s.parse(d['created_at']))}; send it, or run raise_draft with redo=true to replace it.")

    if mode == "cold" and colleagues:
        recent = s.iso(now - timedelta(days=FIRM_HOLD_DAYS))
        for c in colleagues:
            cname = c["person_name"] or "a colleague"
            if c["stage"] == "in_talks":
                reasons.append(f"A colleague at {firm} ({cname}) is in talks; go through them.")
                break
            hit = db.execute("SELECT at FROM events WHERE target_id = ? AND kind = 'touch' AND at >= ? "
                             "ORDER BY at DESC LIMIT 1", (c["id"], recent)).fetchone()
            if hit:
                reasons.append(f"A colleague at {firm} ({cname}) was contacted {_day(s.parse(hit['at']))}; "
                               f"one conversation per firm ({FIRM_HOLD_DAYS} days).")
                break

    if mode != "reply" and t["next_action_at"] and s.parse(t["next_action_at"]) > now:
        reasons.append(f"{who} is parked until {_day(s.parse(t['next_action_at']))}.")

    return {"ok": not reasons, "mode": mode, "channel": channel if not reasons else None,
            "reasons": reasons, "warnings": warnings, "route": route, "target": who, "firm": t["firm_name"]}


# ---------- firm gates: active, stage, fit, size, geography, exclusion ----------

STAGES = ["pre-seed", "seed", "series-a", "series-b", "series-c", "growth"]


def norm_stage(x):
    x = re.sub(r"[\s_]+", "-", (x or "").strip().lower())
    x = {"preseed": "pre-seed", "angel": "pre-seed", "a": "series-a", "b": "series-b",
         "c": "series-c", "series-d": "growth", "late": "growth"}.get(x, x)
    return x if x in STAGES else None


def _check(status, reason, ids=()):
    return {"status": status, "reason": reason, "evidence_ids": list(ids)}


def evaluate_gates(db, firm_id, profile, now=None, override=None):
    """Each check is pass / fail / unknown. Missing evidence is unknown, never fail.
    Overall: fail if any check fails; pass if nothing fails and `active` passes; else unknown."""
    now = now or s.utcnow()
    firm = s.row(db.execute("SELECT * FROM firms WHERE id = ?", (firm_id,)).fetchone()) or {}
    individual = firm.get("kind") in s.INDIVIDUAL_KINDS
    evs = [s.row(r) for r in db.execute(
        "SELECT * FROM evidence WHERE firm_id = ? OR target_id IN (SELECT id FROM targets WHERE firm_id = ?)",
        (firm_id, firm_id))]
    by = lambda k: [e for e in evs if e["kind"] == k]  # noqa: E731
    deals, theses = by("deal"), by("thesis")
    checks = {}

    dated = sorted((e for e in deals if e["date"]), key=lambda e: e["date"])
    age = (now - s.parse(dated[-1]["date"])).days if dated else None
    funds = [e for e in by("fund") if e["date"] and (now - s.parse(e["date"])).days <= 365]
    if age is not None and age <= 274:
        checks["active"] = _check("pass", f"last deal {dated[-1]['date'][:10]}", [dated[-1]["id"]])
    elif funds:
        checks["active"] = _check("pass", f"fund closed {funds[-1]['date'][:10]}", [funds[-1]["id"]])
    elif len(dated) >= 2 and age > 548 and not individual:
        checks["active"] = _check("fail", f"no deal since {dated[-1]['date'][:10]}", [e["id"] for e in dated[-2:]])
    else:
        checks["active"] = _check("unknown", "no recent dated deal or fund close found")

    ours = norm_stage(profile.get("stage"))
    staged = [e for e in deals + theses if norm_stage(e["stage"])]
    if ours is None or not staged:
        checks["stage"] = _check("unknown", "no stage evidence" if ours else "round stage not set in profile")
    else:
        near = [e for e in staged if abs(STAGES.index(norm_stage(e["stage"])) - STAGES.index(ours)) <= 1]
        staged_deals = [e for e in deals if norm_stage(e["stage"])]
        if near:
            checks["stage"] = _check("pass", f"invests at {near[0]['stage']}", [near[0]["id"]])
        elif len(staged_deals) >= 3:
            checks["stage"] = _check("fail", f"{len(staged_deals)} deals, none near {ours}", [e["id"] for e in staged_deals])
        else:
            checks["stage"] = _check("unknown", "too few staged deals to judge")

    rel = [e for e in deals + theses if e["relevant"] == 1]
    if rel:
        checks["fit"] = _check("pass", rel[0]["claim"][:120], [rel[0]["id"]])
    elif theses and all(e["relevant"] == 0 for e in theses):
        checks["fit"] = _check("fail", "every stated thesis is outside our space", [e["id"] for e in theses])
    else:
        checks["fit"] = _check("unknown", "no relevant deal or thesis found")

    rnd = profile.get("round_amount")
    cheques = [e for e in by("cheque") if e["amount"] is not None]
    if firm.get("check_min") is not None:
        cheques.append({"id": None, "amount": firm["check_min"]})
    if rnd and cheques:
        low = min(cheques, key=lambda e: e["amount"])
        ids = [low["id"]] if low["id"] else []
        if low["amount"] > rnd:
            checks["size"] = _check("fail", f"smallest cheque {low['amount']:,.0f} is above the round {rnd:,.0f}", ids)
        else:
            checks["size"] = _check("pass", f"cheque from {low['amount']:,.0f}", ids)
    else:
        checks["size"] = _check("unknown", "no cheque size found" if rnd else "round size not set in profile")

    geo = [g.lower() for g in profile.get("geo") or []]
    match = lambda c: bool(c) and any(g == c.lower() or g in c.lower() for g in geo)  # noqa: E731
    excl = [e for e in by("geography") if e["exclusive"]]
    hits = [e for e in by("geography") + deals if match(e["country"])]
    if excl and not any(match(e["country"]) for e in excl):
        checks["geography"] = _check("fail", f"invests only in {excl[0]['country']}", [e["id"] for e in excl])
    elif hits:
        checks["geography"] = _check("pass", f"active in {hits[0]['country']}", [hits[0]["id"]])
    else:
        checks["geography"] = _check("unknown", "no geography evidence" if geo else "profile geography not set")

    exc = by("exclusion")
    bad = [e for e in exc if e["relevant"] is None or e["relevant"] == 1]
    if bad:
        checks["exclusion"] = _check("fail", bad[0]["claim"][:120], [e["id"] for e in bad])
    elif exc:
        checks["exclusion"] = _check("pass", "stated exclusions do not apply", [e["id"] for e in exc])
    else:
        checks["exclusion"] = _check("unknown", "no exclusions found")

    statuses = [c["status"] for c in checks.values()]
    if override and override.split(":", 1)[0].strip() in ("pass", "fail"):
        overall = override.split(":", 1)[0].strip()
    elif "fail" in statuses:
        overall = "fail"
    elif checks["active"]["status"] == "pass":
        overall = "pass"
    else:
        overall = "unknown"
    return {"overall": overall, "checks": checks}


def apply_gates(db, firm_id, profile, now=None):
    """Evaluate a firm and store the result on all its targets. Firms are go/no-go."""
    ov = db.execute("SELECT gate_override FROM targets WHERE firm_id = ? AND gate_override IS NOT NULL LIMIT 1",
                    (firm_id,)).fetchone()
    g = evaluate_gates(db, firm_id, profile, now, ov["gate_override"] if ov else None)
    fails = "; ".join(f"{k}: {c['reason']}" for k, c in g["checks"].items() if c["status"] == "fail")
    db.execute("UPDATE targets SET gate_status = ?, gate_reasons = ? WHERE firm_id = ?",
               (g["overall"], fails or None, firm_id))
    db.commit()
    return g


__all__ = ["can_draft", "contact_route", "evaluate_gates", "apply_gates", "workdays_back", "add_workdays", "json"]
