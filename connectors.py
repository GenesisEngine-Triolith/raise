"""Find the user's own tools (Notion, Gmail, LinkedIn, web) by name. Raise never ships connectors;
it uses whatever is installed. All Hermes imports are lazy so tests run without Hermes."""
import re

BACKENDS = {"notion": r"notion", "sheets": r"sheets?\b|spreadsheet", "airtable": r"airtable", "hubspot": r"hubspot"}
# a mail tool by name; MCP servers named e.g. google-workspace or m365 give tools without "mail" in the name
MAILISH = re.compile(r"gmail|e?mail|outlook|google_?workspace|gws|m365|o365|office_?365|exchange|imap|smtp|proton", re.I)
RECIPIENT = ("to", "recipient", "recipients", "to_email", "email", "toRecipients", "to_recipients")
NOT_RAISE = re.compile(r"^raise_")


def tool_names():
    try:
        try:
            from tools.registry import discover_builtin_tools
            discover_builtin_tools()
        except Exception:
            pass
        from tools.registry import registry
        return [n for n in registry.get_all_tool_names() if not NOT_RAISE.match(n)]
    except Exception:
        return []


def detect(names=None):
    names = tool_names() if names is None else [n for n in names if not NOT_RAISE.match(n)]
    pick = lambda pat, bad="": [n for n in names if re.search(pat, n, re.I) and not (bad and re.search(bad, n, re.I))]  # noqa: E731
    mail = [n for n in names if MAILISH.search(n) or (re.search("draft", n, re.I) and _is_mail_schema(n))]
    return {
        "backend": {k: pick(p) for k, p in BACKENDS.items()},
        "email_draft": [n for n in mail if re.search("draft", n, re.I) and not re.search("delete|list|get|update|send", n, re.I)],
        "email_search": [n for n in mail if re.search("search|list_threads|list_messages|read", n, re.I)
                         and not re.search("draft|send|delete|label|trash", n, re.I)],
        "linkedin": pick("linkedin"),
        "web_search": sorted(pick(r"web_search|search_web|brave|serper|tavily|exa_search|\bsearch\b", "mail|linkedin|session|skill|file|notion|drive|calendar|slack|issue|repo"),
                             key=lambda n: n != "web_search"),
        "web_extract": sorted(pick(r"web_extract|extract|read_url|fetch_url|scrape|jina|firecrawl", "mail|linkedin|notion|drive"),
                              key=lambda n: n != "web_extract"),
        "skills": "skills_list" in names and "skill_view" in names,
    }


def first(found, key, configured="auto"):
    """The tool to use: the configured name, else the first detected one, else None."""
    if configured and configured != "auto":
        return configured
    lst = found.get(key) or []
    return lst[0] if lst else None


def _props(tool):
    try:
        from tools.registry import registry
        sch = registry.get_schema(tool) or {}
        p = sch.get("parameters") or sch.get("input_schema") or {}
        return p.get("properties") or {}
    except Exception:
        return {}


def _key(props, options, default):
    return next((k for k in options if k in props), default)


def _is_mail_schema(tool):
    p = _props(tool)
    return any(k in p for k in RECIPIENT) and any(k in p for k in ("subject", "title"))


BODY = ("body", "text", "content", "message", "plain", "html")


def email_args(tool, to, subject, body, props=None):
    """Fit the user's draft tool: field names vary, recipients may be a list, Gmail-API-style tools take raw MIME."""
    props = _props(tool) if props is None else props
    inner = props.get("message") if isinstance(props.get("message"), dict) else {}
    if inner.get("type") == "object" and inner.get("properties"):  # Graph-style {"message": {...}} wrapper
        return {"message": email_args(tool, to, subject, body, props=inner["properties"])}
    if "raw" in props and not any(k in props for k in BODY):
        import base64
        from email.message import EmailMessage
        m = EmailMessage()
        m["To"], m["Subject"] = to, subject
        m.set_content(body)
        return {"raw": base64.urlsafe_b64encode(m.as_bytes()).decode("ascii")}
    tk = _key(props, RECIPIENT, "to")
    tp = props.get(tk, {})
    if tp.get("type") == "array":  # Graph/Outlook recipients are objects, others plain strings
        to_val = [{"emailAddress": {"address": to}}] if (tp.get("items") or {}).get("type") == "object" else [to]
    else:
        to_val = to
    bk = _key(props, BODY, "body")
    body_val = {"contentType": "Text", "content": body} if props.get(bk, {}).get("type") == "object" else body
    return {tk: to_val, _key(props, ("subject", "title"), "subject"): subject, bk: body_val}


def search_args(tool, query):
    return {_key(_props(tool), ("query", "q", "search", "search_query"), "query"): query}


def fetch_args(tool, url):
    props = _props(tool)
    return {"urls": [url]} if "urls" in props else {"url": url}
