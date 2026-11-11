from raiseplug.lint import lint, numbers

VERIFIED = ["Paying clinics: 14", "Monthly revenue EUR 22k (bank statement)"]
FACTS = ["Northwind led the EUR 2M seed round of Clinicly in August 2026"]
GOOD = """Hi Ada,

Saw that Northwind led the Clinicly seed in August. We sell scheduling software to small clinics and 14 of them pay us today.

Would a 20 minute call next week be useful?

Best,
Sam"""


def rules(r, key="warnings"):
    return {h["rule"] for h in r[key]}


def test_clean_draft_passes():
    r = lint(GOOD, verified=VERIFIED, facts=FACTS)
    assert r["ok"], r
    assert not r["warnings"], r["warnings"]


def test_numbers_normalise():
    vals = [v for v, _, _ in numbers("EUR 410k, 1.5M, 1,500,000 and 40%")]
    assert vals == [410000, 1500000, 1500000, 40]


def test_unverified_number_is_hard_fail_with_position():
    text = GOOD.replace("14 of them pay us today", "we have EUR 410k ARR")
    r = lint(text, verified=VERIFIED, facts=FACTS)
    assert not r["ok"] and "unverified_number" in rules(r, "hard")
    h = [x for x in r["hard"] if x["rule"] == "unverified_number"][0]
    assert text[h["start"]:h["end"]].strip().startswith("410")


def test_investor_fact_number_is_allowed():
    text = GOOD.replace("led the Clinicly seed", "led the EUR 2M Clinicly seed")
    assert lint(text, verified=VERIFIED, facts=FACTS)["ok"]


def test_date_of_a_logged_message_is_not_an_unverified_number():
    text = GOOD.replace("Saw that", "I wrote you on 27 October. Saw that")
    assert "unverified_number" in rules(lint(text, verified=VERIFIED, facts=FACTS), "hard")                      # nothing logged
    assert "unverified_number" in rules(lint(text, verified=VERIFIED, facts=FACTS, dates=["2026-10-24T09:00:00"]), "hard")  # other day
    assert lint(text, verified=VERIFIED, facts=FACTS, dates=["2026-10-27T09:00:00+00:00"])["ok"]
    assert lint(text.replace("27 October", "October 27th"), verified=VERIFIED, facts=FACTS, dates=["2026-10-27"])["ok"]
    assert "unverified_number" in rules(lint(text.replace("27 October", "27 clinics"), verified=VERIFIED, facts=FACTS, dates=["2026-10-27"]), "hard")


def test_no_personalisation_is_hard_fail():
    text = GOOD.replace("Saw that Northwind led the Clinicly seed in August. ", "")
    assert "no_personalisation" in rules(lint(text, verified=VERIFIED, facts=FACTS), "hard")
    assert "no_personalisation" in rules(lint(GOOD, verified=VERIFIED, facts=[]), "hard")


def test_raise_amount_in_public_post_is_hard_fail():
    text = "Congrats Northwind on the Clinicly round. We are raising EUR 1.5M for clinic scheduling."
    r = lint(text, channel="x", verified=VERIFIED + ["Round: EUR 1.5M"], facts=FACTS, round_amount=1_500_000)
    assert "public_raise_amount" in rules(r, "hard")


def test_style_tells_are_warnings():
    text = ("I hope this email finds you well. Northwind led the Clinicly seed — impressive.\n\n"
            "We are not just a tool, but a partner. Fast, simple, and reliable.\n\n**Traction:** 14 clinics.\n\nWorth a look.")
    r = lint(text, verified=VERIFIED, facts=FACTS)
    assert r["ok"]  # style alone never blocks
    for rule in ("em_dash", "not_x_but_y", "forced_triad", "bold_label", "stock_phrase", "close_not_question",
                 "one_line_closer"):
        assert rule in rules(r), (rule, rules(r))


def test_length_cap_for_dm():
    text = "Northwind led the Clinicly seed. " + "word " * 80 + "Open to a chat?"
    assert "too_long" in rules(lint(text, channel="linkedin_dm", verified=VERIFIED, facts=FACTS))


def test_bare_signature_name_is_not_the_close():
    from raiseplug import lint as L
    for end in ("\n\nAnna Holm", "\nAnna Holm", "\n\n- Anna"):
        r = L.lint("Hi Ada,\n\nNorthwind led Clinova.\n\nWorth a short call?" + end, channel="linkedin_dm",
                   facts=["Northwind led Clinova"])
        assert not {w["rule"] for w in r["warnings"]} & {"close_not_question", "one_line_closer"}, end
    r = L.lint("Hi Ada,\n\nNorthwind led Clinova.\n\nTalk soon.", channel="linkedin_dm", facts=["Northwind led Clinova"])
    assert "close_not_question" in {w["rule"] for w in r["warnings"]}
