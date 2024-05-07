import logging
import threading

from hawkbot.core.config.active_config_manager import ActiveConfigManager
from hawkbot.core.data_classes import ExchangeState
from hawkbot.core.model import BotStatus
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.utils import period_as_s

logger = logging.getLogger(__name__)


class LogReporterPlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.status = BotStatus.NEW
        self.exchange_state = ExchangeState(redis_host=redis_host, redis_port=redis_port)
        self.config = ActiveConfigManager(redis_host=redis_host, redis_port=redis_port)
        self.report_interval = period_as_s("15s")
        self.event = threading.Event()

        if 'interval' in plugin_config:
            self.report_interval = period_as_s(plugin_config['interval'])

    def start(self):
        self.status = BotStatus.STARTING
        square_off_thread = threading.Thread(name='bot_square_off',
                                             target=self.report_loop,
                                             args=(),
                                             daemon=True)
        square_off_thread.start()

    def report_loop(self):
        self.status = BotStatus.RUNNING
        while self.status == BotStatus.RUNNING:
            try:
                self._log_status()
            except:
                logger.exception("An error occurred while printing the current status")
            self.event.wait(self.report_interval)

        self.exchange_state.close()
        self.config.shutdown()
        self.status = BotStatus.STOPPED

    def stop(self):
        self.status = BotStatus.STOPPING

    def _log_status(self):
        information = {}
        position_side_configs = self.config.get_active_position_configs()
        for position_side_config in position_side_configs:
            symbol = position_side_config.symbol
            position_side = position_side_config.position_side
            information.setdefault(symbol, {}).setdefault(position_side, {})
            position = self.exchange_state.position(symbol=symbol, position_side=position_side)
            information[symbol][position_side]['size'] = position.position_size
            information[symbol][position_side]['entry_price'] = position.entry_price
            information[symbol][position_side]['cost'] = position.cost
            information[symbol][position_side]['upnl'] = position.calculate_pnl(price=self.exchange_state.last_tick_price(symbol))

        logger.info("============= POSITION OVERVIEW =============")
        for symbol in information:
            for position_side in information[symbol]:
                data = information[symbol][position_side]
                logger.info(f"{symbol} {position_side.name} Size  : {data['size']}")
                logger.info(f"{symbol} {position_side.name} Price : {data['entry_price']}")
                logger.info(f"{symbol} {position_side.name} Cost  : {data['cost']}")
                logger.info(f"{symbol} {position_side.name} UPNL  : {data['upnl']}")

