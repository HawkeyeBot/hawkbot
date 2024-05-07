import logging

from hawkbot.core.plugins.plugin import Plugin

logger = logging.getLogger(__name__)


class TemplatePlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)

    def start(self):
        pass

    def stop(self):
        pass

    def something(self, x: int):
        pass  # Do stuff here
