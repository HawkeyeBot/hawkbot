import logging
import threading
from typing import Dict

from flask_cors import CORS

from hawkbot.core.mode_processor import ModeProcessor
from hawkbot.core.model import BotStatus
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.plugins.rest_server.rest_flask_app import RestFlaskApp

logger = logging.getLogger(__name__)

"""
    "plugins": {
        "RestServer": {
            "host": "127.0.0.1",
            "port": 9696
        }
    }
"""


class RestServer(Plugin):
    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.mode_processor: ModeProcessor = None  # Set by pluginloader
        self.host: str = None
        self.port: int = 6969
        self.status: BotStatus = BotStatus.NEW

        if 'port' in self.plugin_config:
            self.port = self.plugin_config['port']
        if 'host' in self.plugin_config:
            self.host = self.plugin_config['host']

    def start_server(self):
        logger.info('Starting REST server')
        app = RestFlaskApp(redis_host=self.redis_host, redis_port=self.redis_port, mode_processor=self.mode_processor)
        CORS(app)
        app.run(host=self.host, port=self.port)
        logger.info('Started REST server')

    def start(self):
        if self.status == BotStatus.NEW:
            self.status = BotStatus.STARTING
            server_thread = threading.Thread(name='bot_rest_server', target=self.start_server, daemon=True)
            server_thread.start()
            self.status = BotStatus.RUNNING

    def stop(self):
        pass
