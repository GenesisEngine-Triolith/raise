"""SQLite store for Raise. One local database per Hermes profile.

Under Hermes the connection comes from plugins.plugin_storage.plugin_db("raise").
Tests pass a path (or ":memory:").
"""
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone

SCHEMA = [
    # v1
    """
    CREATE TABLE profile (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL DEFAULT '{}',
        confirmed_at TEXT);
    CREATE TABLE branches (branch TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'open',
        completeness INTEGER NOT NULL DEFAULT 0, answers TEXT NOT NULL DEFAULT '[]',
        flags TEXT NOT NULL DEFAULT '[]', updated_at TEXT);
    CREATE TABLE claims (id INTEGER PRIMARY KEY, text TEXT NOT NULL, value TEXT,
        tag TEXT NOT NULL CHECK (tag IN ('verified','unverified','projection')),
        source TEXT, branch TEXT, created_at TEXT);
    CREATE TABLE firms (id INTEGER PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE,
        domain TEXT, kind TEXT NOT NULL DEFAULT 'vc', geo TEXT, stages TEXT, sectors TEXT,
        check_min REAL, check_max REAL, website TEXT, email TEXT, form_url TEXT,
        created_at TEXT);
    CREATE TABLE people (id INTEGER PRIMARY KEY, firm_id INTEGER REFERENCES firms(id),
        name TEXT NOT NULL, name_key TEXT NOT NULL, title TEXT, kind TEXT,
        email TEXT, email_status TEXT NOT NULL DEFAULT 'unknown', linkedin TEXT,
        connected INTEGER NOT NULL DEFAULT 0, do_not_contact INTEGER NOT NULL DEFAULT 0,
        created_at TEXT);
    CREATE UNIQUE INDEX people_key ON people(name_key, IFNULL(firm_id, 0));
    CREATE TABLE targets (id INTEGER PRIMARY KEY, firm_id INTEGER REFERENCES firms(id),
        person_id INTEGER REFERENCES people(id),
        stage TEXT NOT NULL DEFAULT 'new', bucket TEXT, score REAL, ranking TEXT,
        gate_status TEXT, gate_reasons TEXT, gate_override TEXT,
        next_action_at TEXT, revisit_at TEXT, archived INTEGER NOT NULL DEFAULT 0,
        source TEXT, created_at TEXT);
    CREATE UNIQUE INDEX targets_key ON targets(IFNULL(firm_id, 0), IFNULL(person_id, 0));
    CREATE TABLE evidence (id INTEGER PRIMARY KEY, target_id INTEGER REFERENCES targets(id),
        firm_id INTEGER REFERENCES firms(id), kind TEXT NOT NULL, claim TEXT NOT NULL,
        source_url TEXT, date TEXT, stage TEXT, amount REAL, amount_max REAL,
        relevant INTEGER, country TEXT, exclusive INTEGER NOT NULL DEFAULT 0,
        fetched INTEGER NOT NULL DEFAULT 0, created_at TEXT);
    CREATE TABLE events (id INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL,
        channel TEXT, direction TEXT, target_id INTEGER, person_id INTEGER, firm_id INTEGER,
        summary TEXT, ref TEXT, payload TEXT, UNIQUE (kind, ref));
    CREATE TABLE drafts (id INTEGER PRIMARY KEY, target_id INTEGER NOT NULL, channel TEXT NOT NULL,
        subject TEXT, body TEXT NOT NULL, body_sha256 TEXT NOT NULL, lint TEXT,
        status TEXT NOT NULL DEFAULT 'draft', created_at TEXT);
    CREATE TABLE intro_paths (id INTEGER PRIMARY KEY, target_id INTEGER NOT NULL,
        via_name TEXT NOT NULL, via_linkedin TEXT, relation TEXT, strength INTEGER);
    CREATE TABLE usage (day TEXT NOT NULL, action TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (day, action));
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    """,
]

OPEN_STAGES = ("new", "researching", "ready", "contacted", "in_talks")
INDIVIDUAL_KINDS = ("angel", "angel_group")


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def iso(dt):
    return dt.replace(microsecond=0).isoformat() if dt else None


def parse(ts):
    return datetime.fromisoformat(ts) if ts else None


def name_key(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def migrate(db):
    v = db.execute("PRAGMA user_version").fetchone()[0]
    for i, script in enumerate(SCHEMA[v:], start=v + 1):
        db.executescript(script)
        db.execute(f"PRAGMA user_version = {i}")
    db.commit()


def connect(path=None):
    if path is None:
        from plugins.plugin_storage import plugin_db
        db = plugin_db("raise")
    else:
        db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    migrate(db)
    return db


def row(r):
    return dict(r) if r is not None else None


# ---------- profile ----------

def profile_get(db):
    r = db.execute("SELECT data, confirmed_at FROM profile WHERE id = 1").fetchone()
    data = json.loads(r["data"]) if r else {}
    data["_confirmed_at"] = r["confirmed_at"] if r else None
    return data


def profile_set(db, fields, confirm=False):
    cur = profile_get(db)
    cur.pop("_confirmed_at", None)
    cur.update(fields or {})
    db.execute(
        "INSERT INTO profile (id, data, confirmed_at) VALUES (1, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET data = excluded.data, "
        "confirmed_at = COALESCE(excluded.confirmed_at, profile.confirmed_at)",
        (json.dumps(cur), iso(utcnow()) if confirm else None),
    )
    db.commit()
    return profile_get(db)


def verified_claims(db):
    return [row(r) for r in db.execute("SELECT * FROM claims WHERE tag = 'verified'")]


def add_claim(db, text, tag, value=None, source=None, branch=None):
    cur = db.execute(
        "INSERT INTO claims (text, value, tag, source, branch, created_at) VALUES (?,?,?,?,?,?)",
        (text, value, tag, source, branch, iso(utcnow())),
    )
    db.commit()
    return cur.lastrowid


# ---------- firms, people, targets ----------

def upsert_firm(db, name, **f):
    key = name_key(name)
    r = db.execute("SELECT id FROM firms WHERE name_key = ?", (key,)).fetchone()
    cols = {k: v for k, v in f.items() if v is not None}
    if r:
        if cols:
            db.execute(
                f"UPDATE firms SET {', '.join(k + ' = ?' for k in cols)} WHERE id = ?",
                (*cols.values(), r["id"]),
            )
        return r["id"]
    cols.update(name=name, name_key=key, created_at=iso(utcnow()))
    cur = db.execute(
        f"INSERT INTO firms ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        tuple(cols.values()),
    )
    return cur.lastrowid


def upsert_person(db, name, firm_id=None, **f):
    """Dedupe by person (name within firm), never by firm domain."""
    key = name_key(name)
    r = db.execute(
        "SELECT id FROM people WHERE name_key = ? AND IFNULL(firm_id, 0) = IFNULL(?, 0)",
        (key, firm_id),
    ).fetchone()
    cols = {k: v for k, v in f.items() if v is not None}
    if r:
        if cols:
            db.execute(
                f"UPDATE people SET {', '.join(k + ' = ?' for k in cols)} WHERE id = ?",
                (*cols.values(), r["id"]),
            )
        return r["id"]
    cols.update(name=name, name_key=key, firm_id=firm_id, created_at=iso(utcnow()))
    cur = db.execute(
        f"INSERT INTO people ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        tuple(cols.values()),
    )
    return cur.lastrowid


def upsert_target(db, firm_id=None, person_id=None, **f):
    r = db.execute(
        "SELECT id FROM targets WHERE IFNULL(firm_id, 0) = IFNULL(?, 0) AND IFNULL(person_id, 0) = IFNULL(?, 0)",
        (firm_id, person_id),
    ).fetchone()
    cols = {k: v for k, v in f.items() if v is not None}
    if r:
        if cols:
            db.execute(
                f"UPDATE targets SET {', '.join(k + ' = ?' for k in cols)} WHERE id = ?",
                (*cols.values(), r["id"]),
            )
        return r["id"]
    cols.update(firm_id=firm_id, person_id=person_id, created_at=iso(utcnow()))
    cur = db.execute(
        f"INSERT INTO targets ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        tuple(cols.values()),
    )
    return cur.lastrowid


def target_full(db, target_id):
    """Target joined with its firm and person, as one dict."""
    r = db.execute(
        """SELECT t.*, f.name AS firm_name, f.kind AS firm_kind, f.email AS firm_email,
                  f.form_url AS firm_form, f.geo AS firm_geo,
                  p.name AS person_name, p.title AS person_title, p.kind AS person_kind,
                  p.email AS person_email, p.email_status, p.linkedin, p.connected,
                  p.do_not_contact
           FROM targets t LEFT JOIN firms f ON f.id = t.firm_id
           LEFT JOIN people p ON p.id = t.person_id WHERE t.id = ?""",
        (target_id,),
    ).fetchone()
    return row(r)


def target_kind(t):
    """Firm kind wins at a firm (firms are go/no-go); otherwise the person's kind."""
    fk = t.get("firm_kind")
    if fk and fk not in INDIVIDUAL_KINDS:
        return fk
    return t.get("person_kind") or fk or "angel"


# ---------- events ----------

def log_event(db, kind, target_id=None, channel=None, direction=None, summary=None,
              ref=None, payload=None, at=None):
    """Idempotent on (kind, ref). Returns the event id, or None if it was a duplicate."""
    t = target_full(db, target_id) if target_id else None
    try:
        cur = db.execute(
            "INSERT INTO events (at, kind, channel, direction, target_id, person_id, firm_id, summary, ref, payload) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (iso(at or utcnow()), kind, channel, direction, target_id,
             t and t["person_id"], t and t["firm_id"], summary, ref,
             json.dumps(payload) if payload is not None else None),
        )
    except sqlite3.IntegrityError:
        return None
    db.commit()
    return cur.lastrowid


def meta_get(db, key, default=None):
    r = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return r["value"] if r else default


def meta_set(db, key, value):
    db.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
               (key, value))
    db.commit()
