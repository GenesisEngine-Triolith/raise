"""Sanity checks for the demo dataset. Run: python validate.py"""
import json, re, pathlib
D = pathlib.Path(__file__).parent
L = lambda n: json.loads((D / n).read_text(encoding="utf-8"))
inv, ev, rk, hist, rep, co = (L(n) for n in ("investors.json", "evidence.json", "rankings.json", "history.json", "replies.json", "company.json"))
ok = True
def check(name, cond, extra=""):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""))

people = {(i["firm"], i["person"]) for i in inv}
key = lambda i: f"{i['firm'] or ''}|{i['person']}"
check("40 investors", len(inv) == 40 and len(people) == 40)
check("evidence firm+person exist", all(e["firm"] in {i["firm"] for i in inv} and (e["person"] is None or (e["firm"], e["person"]) in people) for e in ev))
check("evidence keys unique", len({e["key"] for e in ev}) == len(ev), f"{len(ev)} facts")
per = {key(i): [e for e in ev if e["firm"] == i["firm"] and e["person"] in (None, i["person"])] for i in inv}
check("2-5 facts per investor", all(2 <= len(v) <= 5 for v in per.values()), f"min {min(map(len, per.values()))} max {max(map(len, per.values()))}")
check("rankings cover all 40", set(rk) == {key(i) for i in inv})
bad = [(k, x) for k, r in rk.items() for d in r.values() for x in d["evidence"] if x not in {e["key"] for e in per[k]}]
check("ranking evidence exists and belongs to investor", not bad, str(bad[:3]))
noev = [(k, d) for k, r in rk.items() for d, v in r.items() if d != "reachability" and not v["evidence"]]
check("exactly 2 dims cite no evidence", len(noev) == 2, str(noev))
check("history firm+person exist", all((h["firm"], h["person"]) in people for h in hist))
check("replies firm+person exist", all((r["firm"], r["person"]) in people for r in rep) and len(rep) == 4)
check("each reply has an earlier outbound touch", all(any(h["person"] == r["person"] and h["kind"] == "touch" and h["direction"] == "out" and h["days_ago"] > r["days_ago"] for h in hist) for r in rep))

text = "".join((D / n).read_text(encoding="utf-8") for n in ("investors.json", "evidence.json", "replies.json", "history.json", "../tests/fixtures/pages/injection.html"))
hosts = re.findall(r"https?://([^/\"'\s<>]+)", text) + re.findall(r"[\w.+-]+@([\w.-]+\.\w+)", text)
check(".example only for URLs and emails", all(h.endswith(".example") for h in hosts), f"{len(hosts)} checked")

tot = lambda k: sum(v["score"] for v in rk[k].values())
top10 = sorted(rk, key=tot, reverse=True)[:10]
byp = {i["person"]: i for i in inv}
a = [h for h in hist if h["kind"] == "touch" and h["channel"] == "email" and h["days_ago"] == 1 and key(byp[h["person"]]) in top10]
check("scenario A (emailed 1 day ago, top 10)", len(a) == 1, a[0]["person"] if a else "")
bs = [(p, q) for p in inv for q in inv if p["firm"] and p["firm"] == q["firm"] and p["stage"] == "passed" and q["stage"] != "passed" and key(p) in top10 and key(q) in top10]
check("scenario B (firm passed, both top 10)", bool(bs), f"{bs[0][0]['person']} passed -> {bs[0][1]['person']}" if bs else "")
c = [i["person"] for i in inv if i["stage"] == "in_talks" and any(h["person"] == i["person"] and h["kind"] == "reply" and h["days_ago"] == 10 for h in hist)]
check("in_talks + inbound reply 10 days ago", len(c) == 1, str(c))

# gate simulation (mirrors gates.py: cheque vs round, exclusive geography, relevant exclusion)
rnd, geo = co["profile"]["round_amount"], co["profile"]["geo"]
fails = set()
for e in ev:
    if e["kind"] == "cheque" and e["amount"] and e["amount"] > rnd: fails.add((e["firm"], "size"))
    if e["kind"] == "geography" and e["exclusive"] and not any(g in (e["country"] or "").lower() for g in geo): fails.add((e["firm"], "geography"))
    if e["kind"] == "exclusion" and e["relevant"] in (None, 1): fails.add((e["firm"], "exclusion"))
check("exactly 3 firms fail a gate", len(fails) == 3, str(sorted(fails)))
check("one unverified ARR claim in deck", sum(c["tag"] == "unverified" for c in co["claims"]) == 1 and "EUR 410k" in co["deck_text"], f"deck {len(co['deck_text'].split())} words")
routes = {"connected": sum(i["connected"] for i in inv), "confirmed email": sum(i["email_status"] == "confirmed" for i in inv),
          "no route": sum(not (i["linkedin"] or i["email_status"] == "confirmed" or i["firm_email"] or i["form_url"]) for i in inv),
          "intro_via": sum("intro_via" in i for i in inv)}
print("routes:", routes)
print("top 10:", [k for k in top10])
print("ALL OK" if ok else "SOME CHECKS FAILED")
