"""Code checks on a draft after the model writes it.

Hard failures block the draft (it never becomes an email draft):
  - a number that is not in the verified claims or the investor's cited facts
  - no investor-specific cited fact in the text
  - the raise amount in a public-channel draft
Warnings trigger one automatic rewrite, then are shown to the founder.
The style rules follow the structural tells in the bundled humanizer skill (blader/humanizer).
"""
import re

PUBLIC_CHANNELS = ("x", "x_reply", "linkedin_post", "public")
MAX_WORDS = {"email": 150, "firm_inbox": 150, "linkedin_dm": 70, "connect": 50, "intro": 120, "x": 50}

STOCK_WORDS = [
    "delve", "tapestry", "testament", "pivotal", "seamless", "seamlessly", "leverage", "robust", "landscape",
    "realm", "foster", "unlock", "game-changer", "game changer", "cutting-edge", "elevate", "empower",
    "synergy", "holistic", "navigate the", "in today's", "ever-evolving", "groundbreaking", "transformative",
    "i hope this email finds you well", "i hope this message finds you well", "i wanted to reach out",
    "thrilled to", "excited to share", "at the intersection of", "paradigm",
]
INFLATED = ["revolutionary", "world-class", "best-in-class", "unprecedented", "the leading", "first-ever",
            "industry-leading", "disrupt", "massive", "unparalleled"]
STAGED_OPENERS = re.compile(
    r"^\s*(quick question|here'?s the thing|let me be direct|i'?ll keep this short|short version|"
    r"the short answer|imagine|picture this|let'?s be honest|i'?ll cut to the chase)\b", re.I)
NOT_X_BUT_Y = re.compile(
    r"\b(not (just|only|merely) [^.?!]{1,60}?\bbut\b|(isn'?t|is not|it'?s not|not about) [^.?!]{1,60}?[,;]\s*(it'?s|it is|but)\b)",
    re.I)
TRIAD = re.compile(r"\b([A-Za-z-]{3,}), ([A-Za-z-]{3,}),? and ([A-Za-z-]{3,})[.!]")
EM_DASH = re.compile(r"—|–| -- ")
BOLD_LABEL = re.compile(r"\*\*[^*\n]{1,40}:?\*\*:?")
NAME_LINE = re.compile(r"^\s*[-–—]?\s*[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,2}\s*$")
SIGNOFF = re.compile(r"^\s*(best|cheers|thanks|thank you|regards|kind regards|warm regards|all the best|br)\b[,!.]?",
                     re.I)
NUM = re.compile(r"(?<![\w.])([$€£]\s?)?(\d+(?:[.,]\d+)*)(\s?(?:k|m|mn|bn|b|%|x|million|billion|thousand)\b|%)?",
                 re.I)
TIME_UNIT = re.compile(r"\s*-?\s*(minutes?|mins?|hours?|hrs?|am|pm|days?|weeks?|months?|years?)\b", re.I)
MONTHS = "january february march april may june july august september october november december".split()
MONTH_AFTER = re.compile(r"(?:st|nd|rd|th)?\s+(?:of\s+)?(%s)\b" % "|".join(MONTHS), re.I)
MONTH_BEFORE = re.compile(r"\b(%s)\s+$" % "|".join(MONTHS), re.I)
MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9}
STOP = {"their", "there", "about", "which", "would", "could", "should", "these", "those", "other", "after",
        "before", "invest", "invests", "invested", "investing", "investor", "investors", "company", "companies",
        "round", "fund", "funds", "stage", "recent", "recently", "founder", "founders"}


def _hit(rule, msg, m=None, text=""):
    h = {"rule": rule, "message": msg}
    if m is not None:
        h.update(start=m.start(), end=m.end(), excerpt=text[max(0, m.start() - 20):m.end() + 20])
    return h


def numbers(text):
    """[(value, is_pct, match)] for every number in text, normalised (410k -> 410000)."""
    out = []
    for m in NUM.finditer(text or ""):
        raw, suf = m.group(2), (m.group(3) or "").strip().lower()
        # 1,500,000 or 1.500.000 -> thousands separators; 1.5 / 1,5 -> decimal
        if re.fullmatch(r"\d{1,3}([.,]\d{3})+", raw):
            val = float(re.sub(r"[.,]", "", raw))
        else:
            val = float(raw.replace(",", "."))
        val *= MULT.get(suf, 1)
        out.append((val, suf == "%", m))
    return out


def _is_year(v, pct, m):
    return not pct and float(v).is_integer() and 1990 <= v <= 2100 and len(m.group(2)) == 4


def _logged_date(text, m, dates):
    """The number is the day of a date with a logged message to or from this investor ("I wrote you on 27 October"):
    a reference to the thread, not a claim. A date with no logged message stays a hard fail."""
    mo = MONTH_AFTER.match(text, m.end()) or MONTH_BEFORE.search(text[:m.start()])
    if not (mo and m.group(2).isdigit()):
        return False
    return "%02d-%02d" % (MONTHS.index(mo.group(1).lower()) + 1, int(m.group(2))) in {str(d)[5:10] for d in dates}


def _body_without_signoff(text):
    paras = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    while paras:
        if SIGNOFF.match(paras[-1]):
            paras.pop()
        elif len(paras) > 1 and len(paras[-1].split()) <= 2 and SIGNOFF.match(paras[-2]):
            paras.pop()  # bare name line after a sign-off
        else:
            lines = paras[-1].splitlines()
            if NAME_LINE.match(lines[-1]):  # a bare signature name ("Anna Holm", "- Anna") is not the close
                lines.pop()
                if lines:
                    paras[-1] = "\n".join(lines)
                else:
                    paras.pop()
                continue
            break
    return "\n\n".join(paras)


def _keywords(fact):
    caps = {w for w in re.findall(r"\b[A-Z][a-zA-Z0-9&-]{2,}\b", fact)} - {"The", "They", "This", "Their", "With"}
    longs = {w.lower() for w in re.findall(r"\b[a-zA-Z]{6,}\b", fact)} - STOP
    return caps, longs


def personalised(text, facts):
    low = text.lower()
    for f in facts:
        caps, longs = _keywords(f)
        if any(c.lower() in low for c in caps if c.lower() not in STOP):
            return True
        if sum(1 for w in longs if w in low) >= 2:
            return True
    return False


def lint(text, *, channel="email", verified=(), facts=(), round_amount=None, max_words=None, dates=()):
    """verified: texts/values of verified claims. facts: claims of the investor's cited evidence.
    dates: ISO dates of the logged messages with this investor."""
    text = text or ""
    hard, warn = [], []

    allowed = []
    for src in list(verified) + list(facts):
        allowed += [(v, p) for v, p, _ in numbers(str(src))]
    for v, pct, m in numbers(text):
        if _is_year(v, pct, m) or (not pct and v <= 10 and float(v).is_integer() and not m.group(1) and not m.group(3)):
            continue  # years and small counts are not claims
        if TIME_UNIT.match(text, m.end()):
            continue  # "a 20 minute call", "next 2 weeks"
        if _logged_date(text, m, dates):
            continue  # ponytail: English month names only; add other languages when the plugin drafts in them
        if not any(abs(v - a) <= max(0.01 * a, 0.5) and pct == ap for a, ap in allowed):
            hard.append(_hit("unverified_number",
                             f"'{m.group(0).strip()}' is not in your verified claims or the investor's cited facts.",
                             m, text))
    if not facts:
        hard.append(_hit("no_personalisation", "No investor-specific cited fact was supplied for this draft."))
    elif not personalised(text, facts):
        hard.append(_hit("no_personalisation", "The draft does not mention the cited investor-specific fact."))
    if channel in PUBLIC_CHANNELS and round_amount:
        for v, pct, m in numbers(text):
            if not pct and abs(v - round_amount) <= 0.01 * round_amount:
                hard.append(_hit("public_raise_amount", "The raise amount must not appear in a public post.", m, text))

    for m in EM_DASH.finditer(text):
        warn.append(_hit("em_dash", "Em/en dash; use a comma, full stop or parentheses.", m, text))
    for m in NOT_X_BUT_Y.finditer(text):
        warn.append(_hit("not_x_but_y", "'Not X but Y' contrast; say the point directly.", m, text))
    for m in TRIAD.finditer(text):
        warn.append(_hit("forced_triad", "Three-item list; keep the one that matters.", m, text))
    for m in BOLD_LABEL.finditer(text):
        warn.append(_hit("bold_label", "Bold label; write it as a sentence.", m, text))
    m = STAGED_OPENERS.search(text)
    if m:
        warn.append(_hit("staged_opener", "Staged opener; start with the point.", m, text))
    low = text.lower()
    for w in STOCK_WORDS:
        for m in re.finditer(r"\b" + re.escape(w) + r"\b", low):
            warn.append(_hit("stock_phrase", f"Stock AI phrase '{w}'.", m, text))
    for w in INFLATED:
        for m in re.finditer(r"\b" + re.escape(w), low):
            warn.append(_hit("inflated_claim", f"Inflated claim '{w}'.", m, text))

    body = _body_without_signoff(text)
    if channel not in PUBLIC_CHANNELS and channel != "connect":
        last = re.split(r"(?<=[.!?])\s+", body.strip())[-1] if body.strip() else ""
        if not last.rstrip().endswith("?"):
            warn.append(_hit("close_not_question", f"End with a plain question, not '{last[-60:]}'."))
    paras = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    if len(paras) > 1 and len(paras[-1].split()) <= 6 and not paras[-1].rstrip().endswith("?"):
        warn.append(_hit("one_line_closer", f"One-line punchline closer: '{paras[-1].strip()}'."))
    cap = max_words or MAX_WORDS.get(channel, 150)
    n = len(body.split())
    if n > cap:
        warn.append(_hit("too_long", f"{n} words; keep it under {cap} for {channel}."))

    return {"ok": not hard, "hard": hard, "warnings": warn}
