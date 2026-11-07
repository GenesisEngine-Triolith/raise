"""A stand-in for Hermes' plugin context: records registrations, keeps config, logs dispatched tools."""


class FakeCtx:
    def __init__(self, llm=None, config=None):
        self.llm = llm
        self.config = dict(config or {})
        self.tools, self.commands, self.cli, self.skills, self.hooks, self.blueprints = {}, {}, {}, {}, {}, {}
        self.dispatched = []  # (tool_name, args)
        self.cron = None

    def register_tool(self, name, toolset, schema, handler, check_fn=None, requires_env=None, is_async=False,
                      description="", emoji="", override=False):
        assert toolset == "raise" and schema["name"] == name and schema["parameters"]["type"] == "object"
        self.tools[name] = handler

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands[name] = handler

    def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
        self.cli[name] = (setup_fn, handler_fn)

    def register_skill(self, name, path, description=""):
        self.skills[name] = path

    def register_hook(self, name, cb):
        self.hooks[name] = cb

    def register_automation_blueprint(self, key, *, title, description, schedule_template, prompt_template,
                                      category="general", slots=(), deliver_default="origin", skills=(), tags=()):
        self.blueprints[key] = dict(title=title, prompt=prompt_template, schedule=schedule_template, slots=list(slots))

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def set_config(self, key, value):
        self.config[key] = value

    def dispatch_tool(self, tool_name, args):
        self.dispatched.append((tool_name, args))
        return "{}"

    def current_cron_execution(self):
        return self.cron
