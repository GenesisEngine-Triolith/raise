# Raise demo dataset (all fictional)
Company: Tidewell, booking and billing software for independent clinics. 40 invented investors, every domain ends in .example.
company.json: profile, 8 claims (one unverified ARR of EUR 410k, one projection), branch completeness, deck text containing the ARR number.
investors.json: 40 rows for raise_import; 3 firms with 2 partners, 6 angels, mixed routes (connected, email only, firm inbox only, none), 3 intro paths.
evidence.json: dated facts per investor. Gate fails: Prairie Gate Capital (US-only), Monolith Growth Partners (cheque above round), Orchard Lane Ventures (excludes healthcare software). Four firms have thin evidence and stay unknown.
rankings.json: canned scores for all 40, no LLM needed. Lotte Hendriks and Pieter Vandermeer cite no evidence for "lead", so the code zeroes it.
history.json scenario A: Maja Sterner was emailed 1 day ago, so a new draft is refused as "still pending".
history.json scenario B: Oskar Fenwick (Ravenhill Partners) passed, so Clara Mattson is refused as "firm passed".
history.json scenario C: Ada Lindqvist is in_talks with an inbound reply 10 days ago; her colleague Jonas Brandt is told to go through her.
replies.json: four inbox messages (interest, soft pass, out-of-office, question), each from someone with an earlier outbound touch.
tests/fixtures/pages/injection.html has a hidden prompt-injection block; pages/linkedin_session_error.json simulates an expired LinkedIn session.
