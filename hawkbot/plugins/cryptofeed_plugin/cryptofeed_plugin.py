import logging
from multiprocessing import Queue, Process

from hawkbot.core.config.active_config_manager import ActiveConfigManager
from hawkbot.logging.logging_globals import get_logging_queue
from hawkbot.plugins.cryptofeed_plugin.cryptofeed import Cryptofeed
from hawkbot.core.plugins.plugin import Plugin

logger = logging.getLogger(__name__)


class CryptofeedPlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.config = ActiveConfigManager(redis_host=redis_host, redis_port=redis_port)
        self.command_queue = Queue()

    def stop(self):
        self.command_queue.put('SHUTDOWN')

    def start(self):
        cryptofeed_plugin_process = Process(target=Cryptofeed.start_process,
                                            args=(self.config.redis_port,
                                                  self.command_queue,
                                                  get_logging_queue(),
                                                  self.plugin_config),
                                            daemon=True,
                                            name=f"HB_CryptofeedPlugin")
        cryptofeed_plugin_process.start()
