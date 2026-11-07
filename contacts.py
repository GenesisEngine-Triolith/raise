"""Find how to reach a firm from its own website: role inbox, pitch form, a person's email. Pure functions, no network.

Only addresses on the firm's own domain count (no portfolio companies, no web-builder or tracking addresses), and a
personal address only becomes 'confirmed' when its local part spells the person's name in a common pattern.
ponytail: no JavaScript rendering and no model check that the domain really is the firm's; add both if founders
hit SPA sites or namesake domains.
"""
import re
import unicodedata
from urllib.parse import urlparse

from . import store

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
ROLE_INBOX = re.compile(r"^(info|contact|hello|hi|team|office|admin|invest|investments?|investors?|ir|deals?|pitch|pitches|"
                        r"mail|general|enquiries|inquiries|partners|dealflow|submissions?|ventures|founders|opportunities|"
                        r"startups|apply|funding)@", re.I)
INBOX_ORDER = ("pitch", "deals", "dealflow", "submissions", "invest", "startups", "founders", "apply", "funding",
               "hello", "info", "contact", "team", "office")
FORM_RE = re.compile(r"https?://(?:[\w-]+\.)*(?:typeform\.com|airtable\.com|forms\.gle|docs\.google\.com/forms|tally\.so|"
                     r"jotform\.com|hsforms\.com|forms\.office\.com|fillout\.com|paperform\.co|dealum\.com|"
                     r"dealroom\.co/[\w/-]*pitch)[^\s)\"'<>\]]*", re.I)
CONTACT_LINK = re.compile(r"/(contact|pitch|apply|submit|founders?|for-founders|team|people|about)(-us)?/?$", re.I)
PITCH_PATH = re.compile(r"/(pitch|apply|submit|founders?|for-founders|send-?us)[\w/-]*/?$", re.I)
FORM_TEXT = re.compile(r"fill (out|in) the form|submit(ting)? the form|form below|submit your (deck|pitch)|share your "
                       r"(deck|pitch)|pitch us|apply for funding|upload (your )?deck|funding inquir", re.I)
INVESTOR_SITE = re.compile(r"portfolio|invest|venture|\bfunds?\b|founders|startups|seed|pre-seed|series [ab]|"
                           r"accelerator|angels?\b|capital partners|our companies", re.I)
NOT_FOUND = re.compile(r"page not found|\b404\b", re.I)
IMAGE = (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif")
PATTERNS = ("{f}", "{f}.{l}", "{f}{l}", "{i}{l}", "{i}.{l}", "{f}_{l}", "{f}-{l}", "{l}", "{l}.{f}", "{f}{j}")


def host(url):
    h = urlparse(url if "//" in url else "https://" + url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def on_site(url, dom):
    h = host(url)
    return bool(dom) and (h == dom or h.endswith("." + dom))


def own_domain(url, firm):
    """The page's registered domain spells the firm's name (northfund.com for North Fund), not a directory or mirror."""
    labels = host(url).split(".")
    if len(labels) < 2:
        return False
    sld = labels[-3] if len(labels) > 2 and labels[-2] in ("co", "com", "org", "ac") else labels[-2]
    sld, key = store.name_key(sld).replace(" ", ""), store.name_key(firm or "").replace(" ", "")
    return bool(sld and key and (sld == key or (min(len(sld), len(key)) >= 5 and (sld.startswith(key) or key.startswith(sld)))))


def links(text):
    return re.findall(r"\]\((https?://[^)\s]+)\)", text) + re.findall(r'href="(https?://[^"]+)"', text)


def contact_pages(home_url, home_text, dom):
    """The contact / pitch / team pages the homepage menu links to, else a guessed /contact."""
    menu = [u.split("#")[0].rstrip("/") for u in links(home_text) if on_site(u, dom) and CONTACT_LINK.search(urlparse(u).path)]
    site = f"{urlparse(home_url).scheme or 'https'}://{urlparse(home_url).netloc}"
    return list(dict.fromkeys(menu))[:4] or [site + "/contact"]


def scan(pages, dom):
    """pages: {url: text}. Returns the best role inbox and pitch form on the firm's domain, each with its source page,
    plus personal addresses there."""
    emails, forms = {}, {}
    for url, txt in pages.items():
        if NOT_FOUND.search(txt[:600]):
            continue
        for e in EMAIL_RE.findall(txt):
            e = e.lower().strip(".")
            d = e.split("@")[1]
            if not e.endswith(IMAGE) and (d == dom or d.endswith("." + dom)):
                emails.setdefault(e, url)
        for u in links(txt) + FORM_RE.findall(txt):
            if FORM_RE.match(u) or (on_site(u, dom) and PITCH_PATH.search(urlparse(u).path)):
                forms.setdefault(u.split("#")[0].rstrip("/."), url)
        if on_site(url, dom) and PITCH_PATH.search(urlparse(url).path) and FORM_TEXT.search(txt):
            forms.setdefault(url.rstrip("/"), url)  # the pitch page carries its own form
    rank = lambda e: next((i for i, k in enumerate(INBOX_ORDER) if e.startswith(k)), 99)  # noqa: E731
    inboxes = sorted((e for e in emails if ROLE_INBOX.match(e)), key=rank)
    # a real form host beats a /pitch page on the site
    form = min(forms, key=lambda f: (not FORM_RE.match(f), not PITCH_PATH.search(urlparse(f).path)), default=None)
    return {"inbox": inboxes[0] if inboxes else None, "inbox_src": emails[inboxes[0]] if inboxes else None,
            "form": form, "form_src": forms.get(form), "personal": {e: u for e, u in emails.items() if not ROLE_INBOX.match(e)}}


def name_parts(name):
    a = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    toks = re.findall(r"[a-z]+", re.sub(r"\(.*?\)", "", a))
    return (toks[0], toks[-1]) if len(toks) >= 2 else None


def matches_person(email, name):
    p = name_parts(name)
    return bool(p) and email.split("@")[0].lower() in {x.format(f=p[0], l=p[1], i=p[0][0], j=p[1][0]) for x in PATTERNS}


def _demo():
    pages = {"https://northfund.com": "[Contact](https://northfund.com/contact) [Pitch us](https://northfund.typeform.com/to/x)",
             "https://northfund.com/contact": "Write to info@northfund.com or pitch@northfund.com. Ada: ada.lund@northfund.com. "
                                              "Portfolio: ceo@portco.io logo@2x.png"}
    r = scan(pages, "northfund.com")
    assert r["inbox"] == "pitch@northfund.com" and r["form"] == "https://northfund.typeform.com/to/x"
    assert set(r["personal"]) == {"ada.lund@northfund.com"} and matches_person("ada.lund@northfund.com", "Ada Lund")
    assert own_domain("https://www.northfund.com/team", "North Fund") and not own_domain("https://crunchbase.com/x", "North Fund")
    assert contact_pages("https://northfund.com", pages["https://northfund.com"], "northfund.com") == ["https://northfund.com/contact"]
