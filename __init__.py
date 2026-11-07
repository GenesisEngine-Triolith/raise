"""Raise: a draft-only fundraising desk for Hermes Agent."""
import logging
import os
import re

log = logging.getLogger(__name__)
HERE = os.path.dirname(os.path.abspath(__file__))

BLUEPRINTS = [
    dict(key="daily-brief", title="Raise daily brief", category="fundraising",
         description="Weekday morning: the 5 fundraising actions that matter today.",
         schedule_template="{minute} {hour} * * 1-5",
         prompt_template=("Run the raise_brief tool and give the founder the actions it returns, replies first. Draft only: "
                          "never send anything and never ask questions in this unattended run. If raise_brief reports "
                          "nothing, say so in one line."),
         slots=[dict(name="time", type="time", label="What time?", default="08:00")],
         skills=("raise:draft",), tags=("fundraising", "daily")),
    dict(key="reply-check", title="Raise reply check", category="fundraising",
         description="Weekdays every 2 hours: read investor replies and update the pipeline.",
         schedule_template="0 8-18/2 * * 1-5",
         prompt_template=("Run the raise_replies_check tool. Report only new replies, interest and questions first. Draft "
                          "only: never send anything and never ask questions in this unattended run."),
         slots=[], skills=("raise:reply-triage",), tags=("fundraising", "email")),
    dict(key="weekly-pipeline-review", title="Raise weekly pipeline review", category="fundraising",
         description="Monday: pipeline numbers, stalled conversations and the week's priorities.",
         schedule_template="{minute} {hour} * * 1",
         prompt_template=("Run raise_stats and raise_brief, then summarise the pipeline: stages, what stalled, and the three "
                          "priorities for this week. Draft only: never send anything and never ask questions in this "
                          "unattended run."),
         slots=[dict(name="time", type="time", label="What time?", default="09:00")],
         skills=("raise:reply-triage",), tags=("fundraising", "weekly")),
]


def _description(path):
    try:
        text = open(path, encoding="utf-8").read(2000)
        m = re.search(r"^description:\s*(.+)$", text, re.M)
        return m.group(1).strip() if m and m.group(1).strip() not in ("|", ">") else ""
    except Exception:
        return ""


def register(ctx):
    try:
        from . import cli, safety, tools
        from .schemas import SCHEMAS
    except Exception:
        log.exception("raise: import failed; plugin disabled")
        return
    tools.configure(ctx=ctx)

    def tools_():
        for s in SCHEMAS:
            ctx.register_tool(name=s["name"], toolset="raise", schema=s, handler=tools.HANDLERS[s["name"]],
                              description=s["description"], emoji="💶")

    def commands_():
        ctx.register_command("raise", cli.command, description="Raise fundraising desk: status, setup, next, drafts, "
                             "replies, demo, export, delete", args_hint="status|setup|next|drafts|replies|demo|export|delete")
        ctx.register_cli_command("raise", "Raise fundraising desk", cli.setup_parser, cli.run,
                                 description="Raise: setup, doctor, export, demo, delete")

    def skills_():
        root = os.path.join(HERE, "skills")
        for name in sorted(os.listdir(root)):
            p = os.path.join(root, name, "SKILL.md")
            if os.path.isfile(p):
                ctx.register_skill(name, p, _description(p))

    def blueprints_():
        for b in BLUEPRINTS:
            ctx.register_automation_blueprint(**b)

    def hooks_():
        sf = safety.Safety(db_fn=tools.db, cfg_fn=lambda: {k: tools.cfg(k) for k in safety.DEFAULTS}, next_fn=tools.next_step)
        ctx.register_hook("pre_tool_call", sf.pre_tool_call)
        ctx.register_hook("post_tool_call", sf.post_tool_call)
        ctx.register_hook("pre_llm_call", sf.pre_llm_call)

    for fn in (tools_, commands_, skills_, blueprints_, hooks_):
        try:
            fn()
        except Exception:
            log.exception("raise: %s registration failed", fn.__name__)
