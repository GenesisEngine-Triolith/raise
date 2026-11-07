"""`/raise` in-session command and `hermes raise ...` CLI."""
import json
import os

from . import connectors, store, tools

SKILLS = ("discover", "draft", "factcheck", "grill", "humanizer", "reply-triage", "validate", "voice")


def _j(name, args=None):
    return json.loads(tools.HANDLERS[name](args or {}))


def _drafts_text():
    d = tools.db()
    rows = d.execute("SELECT dr.id, dr.channel, dr.subject, dr.status, t.id AS tid FROM drafts dr "
                     "JOIN targets t ON t.id = dr.target_id WHERE dr.status IN ('approved','placed') "
                     "ORDER BY dr.created_at DESC LIMIT 20").fetchall()
    if not rows:
        return "No drafts waiting."
    return "\n".join(f"#{r['id']} [{r['status']}] {store.target_full(d, r['tid'])['person_name'] or '?'} via {r['channel']}"
                     f"{': ' + r['subject'] if r['subject'] else ''}" for r in rows)


def _status_text():
    s = _j("raise_setup_status")
    c = s["counts"]
    lines = [f"Raise: {c['targets']} investors, {c['evidence']} facts, {c['drafts']} drafts, {c['events']} events.",
             f"Demo mode: {'on' if s['config']['demo_mode'] else 'off'}. Backend: {s['config']['backend']}. "
             f"Email: {s['config']['email_mode']}. LinkedIn: {s['config']['linkedin_mode']}."]
    gaps = [f"{k} {v}%" for k, v in s["profile_completeness"].items() if v < 80]
    lines.append("Profile gaps: " + (", ".join(gaps) if gaps else "none"))
    if s["linkedin_paused_until"]:
        lines.append(f"LinkedIn paused until {s['linkedin_paused_until']} UTC.")
    return "\n".join(lines)


def _brief_text():
    b = _j("raise_brief")
    if not b["actions"]:
        return "Nothing to do right now."
    lines = [f"{i}. [{a['type']}] {a['who']} ({a['firm'] or 'angel'}): {a['reason']}" for i, a in enumerate(b["actions"], 1)]
    return "\n".join(lines + b["notes"])


def _replies_text():
    r = _j("raise_replies_check")
    if not r.get("replies"):
        return r.get("note") or f"No new replies ({r.get('already_logged', 0)} already logged)."
    return "\n".join(f"{x['verdict']:<13} {x['who']} ({x['firm']}): {x['quote'][:90]}"
                     + (f"  -> {x['applied']}" if x["applied"] else "") + ("  [check this one]" if x["needs_review"] else "")
                     for x in r["replies"])


def command(raw=""):
    """/raise status|setup|next|drafts|replies|demo [load|reset]|export|delete confirm"""
    parts = (raw or "").split()
    sub, rest = (parts[0].lower() if parts else "status"), parts[1:]
    try:
        if sub == "status":
            return _status_text()
        if sub == "setup":
            q = _j("raise_setup")
            if q.get("done") or not q.get("ok", True):
                return q.get("message") or q.get("needs_human") or q.get("error", "")
            return "\n".join([q.get("question", ""), *[f"  {o['n']}. {o['label']}" for o in q.get("options", [])]]
                             + ([q["note"]] if q.get("note") else []))
        if sub == "next":
            return _brief_text()
        if sub == "drafts":
            return _drafts_text()
        if sub == "replies":
            return _replies_text()
        if sub == "demo":
            r = _j("raise_demo", {"action": rest[0] if rest else "load"})
            return r.get("error") or r.get("message") or f"Demo loaded: {r.get('investors')} investors, {r.get('ranked')} ranked."
        if sub == "export":
            return f"Exported {_j('raise_export', {'format': 'csv'})['path']}"
        if sub == "delete":
            if rest[:1] != ["confirm"]:
                return "This wipes the profile, investors, evidence, drafts and history. Run '/raise delete confirm' to do it."
            tools.wipe(tools.db())
            tools.set_cfg("demo_mode", False)
            return "All Raise data deleted."
        return "Usage: /raise status | setup | next | drafts | replies | demo [load|reset] | export | delete confirm"
    except Exception as e:
        return f"Raise error: {type(e).__name__}: {e}"


def doctor():
    ok = True
    try:
        d = tools.db()
        print("db: opens, schema v%s, %s targets" % (d.execute("PRAGMA user_version").fetchone()[0],
                                                      d.execute("SELECT COUNT(*) FROM targets").fetchone()[0]))
    except Exception as e:
        print("db: FAILED", e)
        return 1
    for k, v in connectors.detect().items():
        print(f"detected {k}: {v}")
    print("profile completeness:", {x["branch"]: x["completeness"] for x in _j("raise_profile_get")["branches"]})
    print("LinkedIn paused until:", store.meta_get(d, "linkedin_paused_until") or "not paused")
    for s in SKILLS:
        here = os.path.exists(os.path.join(tools.HERE, "skills", s, "SKILL.md"))
        ok &= here
        print(f"skill raise:{s}: {'present' if here else 'MISSING'}")
    print("config:", {k: tools.cfg(k) for k in tools.DEFAULT_CONFIG})
    return 0 if ok else 1


def setup_parser(p):
    sub = p.add_subparsers(dest="raise_cmd")
    sub.add_parser("setup", help="Print the next setup question")
    sub.add_parser("doctor", help="Check the database, detected tools, skills and config")
    sub.add_parser("export", help="Write the pipeline to export.csv")
    dm = sub.add_parser("demo", help="Load or reset the fictional demo data")
    dm.add_argument("action", nargs="?", choices=["load", "reset"], default="load")
    dl = sub.add_parser("delete", help="Delete all Raise data")
    dl.add_argument("--yes", action="store_true", help="Do not ask for confirmation")


def run(args):
    cmd = getattr(args, "raise_cmd", None) or "doctor"
    if cmd == "doctor":
        return doctor()
    if cmd == "delete":
        if not args.yes:
            print("This deletes all Raise data. Re-run with --yes to confirm.")
            return 1
        print(command("delete confirm"))
        return 0
    print(command(f"{cmd} {getattr(args, 'action', '') or ''}".strip()))
    return 0
