"""Evidence-first ranking. The model proposes 0-10 per dimension and cites evidence ids;
code checks the citations and computes the total. An uncited dimension scores 0."""
import json
import re

from . import store as s

WEIGHTS = {"thesis": 22, "similar_companies": 18, "recency": 14, "stage_fit": 10, "lead": 8,
           "fund_cycle": 8, "value_add": 7, "content": 5, "reachability": 8}
NO_EVIDENCE_NEEDED = {"reachability"}   # computed from the contact route, not a claim
DEAL_DIMS = ("recency", "fund_cycle")   # meaningless for angels with no deal record


def _ids(v):
    return [int(x) for x in re.findall(r"\d+", json.dumps(v or []))]


def _valid_ids(db, t):
    return {r["id"] for r in db.execute(
        "SELECT id FROM evidence WHERE target_id = ? OR (firm_id IS NOT NULL AND firm_id = ?)",
        (t["id"], t["firm_id"]))}


def score(db, tid, dims, weights=None):
    w = weights or WEIGHTS
    unknown = sorted(set(dims) - set(w))
    if unknown:
        raise ValueError(f"Unknown ranking dimension(s): {', '.join(unknown)}. Valid: {', '.join(w)}.")
    t = s.target_full(db, tid)
    if not t:
        raise ValueError(f"Target {tid} not found.")
    valid = _valid_ids(db, t)
    individual = s.target_kind(t) in s.INDIVIDUAL_KINDS
    has_deal = bool(valid) and db.execute(
        f"SELECT 1 FROM evidence WHERE kind = 'deal' AND id IN ({','.join('?' * len(valid))})",
        tuple(valid)).fetchone() is not None

    out, kept, total = {}, 0, 0.0
    for name, wt in w.items():
        d = dims.get(name) or {}
        if individual and not has_deal and name in DEAL_DIMS:
            out[name] = {"score": None, "weight": wt, "note": "dropped: individual investor with no deal evidence"}
            continue
        sc = max(0.0, min(10.0, float(d.get("score") or 0)))
        cited = _ids(d.get("evidence_ids", d.get("evidence")))
        ids = [i for i in cited if i in valid]
        notes = []
        if len(ids) < len(cited):
            notes.append(f"ignored evidence ids not on this investor: {sorted(set(cited) - valid)}")
        if sc > 0 and name not in NO_EVIDENCE_NEEDED and not ids:
            sc = 0.0
            notes.append("zeroed: no cited evidence")
        kept += wt
        total += wt * sc / 10
        out[name] = {"score": sc, "weight": wt, "evidence_ids": ids, "why": d.get("why", ""),
                     "note": "; ".join(notes)}
    return {"total": round(100 * total / kept, 1) if kept else 0.0, "dims": out}


def set_ranking(db, tid, dims, weights=None):
    r = score(db, tid, dims, weights)
    db.execute("UPDATE targets SET score = ?, ranking = ? WHERE id = ?", (r["total"], json.dumps(r), tid))
    db.commit()
    return r


def explain(db, tid):
    t = s.target_full(db, tid)
    if not t or not t["ranking"]:
        return {"target_id": tid, "ranked": False}
    r = json.loads(t["ranking"])
    ids = sorted({i for d in r["dims"].values() for i in d.get("evidence_ids") or []})
    ev = [s.row(x) for x in db.execute(
        f"SELECT id, kind, claim, source_url, date FROM evidence WHERE id IN ({','.join('?' * len(ids))})", ids)] if ids else []
    rank = db.execute("SELECT COUNT(*) + 1 FROM targets WHERE score > ? AND archived = 0", (t["score"],)).fetchone()[0]
    return {"target_id": tid, "who": t["person_name"] or t["firm_name"], "firm": t["firm_name"],
            "score": t["score"], "rank": rank, "gate_status": t["gate_status"], "dims": r["dims"], "evidence": ev}


def focus(db, n=10, min_score=None):
    """Top N open, ranked targets that did not fail the firm gates. One person per firm (angels exempt)."""
    rows = db.execute(
        f"""SELECT t.id, t.score, t.stage, t.gate_status, t.firm_id, f.name AS firm, f.kind AS firm_kind,
                   p.name AS person FROM targets t LEFT JOIN firms f ON f.id = t.firm_id
            LEFT JOIN people p ON p.id = t.person_id
            WHERE t.archived = 0 AND t.score IS NOT NULL AND IFNULL(t.gate_status, '') != 'fail'
              AND t.stage IN ({','.join('?' * len(s.OPEN_STAGES))})
            ORDER BY t.score DESC, t.id""", s.OPEN_STAGES).fetchall()
    # the firm is represented by the person in a live conversation, else its highest-ranked person
    rep = {}
    for r in rows:
        if r["firm_id"] and r["firm_kind"] not in s.INDIVIDUAL_KINDS:
            cur = rep.get(r["firm_id"])
            if cur is None or (r["stage"] == "in_talks" and cur["stage"] != "in_talks"):
                rep[r["firm_id"]] = r
    rows = [r for r in rows if not (r["firm_id"] and r["firm_kind"] not in s.INDIVIDUAL_KINDS)
            or rep[r["firm_id"]]["id"] == r["id"]]
    seen, out = set(), []
    for r in rows:
        if min_score is not None and r["score"] < min_score:
            break
        if r["firm_id"] and r["firm_kind"] not in s.INDIVIDUAL_KINDS:
            if r["firm_id"] in seen:
                continue
            seen.add(r["firm_id"])
        out.append({"target_id": r["id"], "who": r["person"] or r["firm"], "firm": r["firm"],
                    "score": r["score"], "stage": r["stage"], "gate_status": r["gate_status"]})
        if len(out) >= n:
            break
    return out
