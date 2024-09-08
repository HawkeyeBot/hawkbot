import asyncio
import logging
import threading
import time
from multiprocessing import Queue

from cryptofeed import FeedHandler
from cryptofeed.defines import TRADES, PERPETUAL
from cryptofeed.exchanges import BinanceFutures
from cryptofeed.exchanges import Bybit
from cryptofeed.symbols import Symbol
from cryptofeed.types import Trade
from redis import Redis
from setproctitle import setproctitle

from hawkbot.core.config.active_config_manager import ActiveConfigManager
from hawkbot.core.data_classes import ExchangeState
from hawkbot.core.time_provider import TimeProvider
from hawkbot.exceptions import InvalidArgumentException
from hawkbot.redis_utils import handle_redis_exception
from hawkbot.utils import period_as_ms, init_logging, readable, period_as_s


class Cryptofeed:
    LISTENTO_SYMBOL = 'cryptofeed_listento_'
    TRADEPRICE_SYMBOL = 'trade_price_'

    def __init__(self, redis_host: str, redis_port: int, command_queue: Queue, logging_queue: Queue, plugin_config):
        global logger
        init_logging(logging_queue)
        logger = logging.getLogger(__name__)
        self.config = ActiveConfigManager(redis_host=redis_host, redis_port=redis_port)
        self.command_queue = command_queue
        self.logging_queue = logging_queue
        self.plugin_config = plugin_config
        self.time_provider = TimeProvider()
        self.exchange_state: ExchangeState = ExchangeState(redis_host=redis_host, redis_port=redis_port)
        self.redis = Redis(host="127.0.0.1", port=redis_port, decode_responses=True)
        self.pubsub = self.redis.pubsub()

        self.clean_retention_period = period_as_ms(self.plugin_config['clean_retention_period'])
        self.clean_check_interval = period_as_ms('30s')
        self.clean_sleep = period_as_s('5s')
        self.exchange_feed = None
        self.type = None
        self.loop = None
        self.feed_handler = FeedHandler(config={'log': {'filename': 'logs/feedhandler.log', 'level': 'WARNING'}, 'backend_multiprocessing': True})
        self.registered_symbols = []

        self.init_config()

    def init_config(self):
        if 'clean_check_interval' in self.plugin_config:
            self.clean_check_interval = period_as_ms(self.plugin_config['clean_check_interval'])
        if 'clean_sleep' in self.plugin_config:
            self.clean_sleep = period_as_s(self.plugin_config['clean_sleep'])

        if self.config.exchange == 'binance':
            self.exchange_feed = BinanceFutures
            self.type = PERPETUAL
        elif self.config.exchange == 'bybit':
            self.exchange_feed = Bybit
            self.type = PERPETUAL
        else:
            raise InvalidArgumentException(f'Exchange {self.config.exchange} is not implemented yet in the CryptofeedPlugin, please contact Hawkeye')

    async def aio_task(self):
        while True:
            await asyncio.sleep(1)

    def run(self):
        self.pubsub.psubscribe(**{Cryptofeed.LISTENTO_SYMBOL: self._add_symbol})
        self.pubsub.run_in_thread(sleep_time=0.01, daemon=True, exception_handler=handle_redis_exception)

        periodic_clean_thread = threading.Thread(name="cryptofeed_periodic_clean", target=self._periodic_clean, daemon=True)
        periodic_clean_thread.start()

        if 'symbols' in self.plugin_config:
            self.registered_symbols.extend(self.plugin_config['symbols'])
            self.feed_handler.add_feed(self.exchange_feed(channels=[TRADES], symbols=self.plugin_config['symbols'], callbacks={TRADES: self._handle_trade}))
        self.loop = asyncio.get_event_loop()
        self.feed_handler.run(start_loop=False)
        loop = asyncio.get_event_loop()
        loop.create_task(self.aio_task())
        loop.run_forever()

    def _add_symbol(self, msg):
        try:
            symbol = msg['data']
            if symbol in self.registered_symbols:
                logger.debug(f"{symbol}: Ignoring already registered symbol")
                return

            symbol_information = self.exchange_state.get_symbol_information(symbol)
            normalized_symbol = Symbol(base=symbol_information.base_asset, quote=symbol_information.asset, type=self.type).normalized
            self.feed_handler.add_feed(feed=self.exchange_feed(channels=[TRADES], symbols=[normalized_symbol], callbacks={TRADES: self._handle_trade}), loop=self.loop)
            self.registered_symbols.append(symbol)
            logger.info(f'{symbol}: Added normalized symbol {normalized_symbol} to cryptofeed')
        except:
            logger.exception(f"Failed to process symbol subscription message for message {msg}")

    def _periodic_clean(self):
        last_clean = self.time_provider.get_utc_now_timestamp()
        while True:
            if last_clean + self.clean_check_interval < self.time_provider.get_utc_now_timestamp():
                key_names = [i for i in self.redis.scan(match=f'{self.TRADEPRICE_SYMBOL}*', count=1000000)[1]]
                for key_name in key_names:
                    remove_before_timestamp = self.time_provider.get_utc_now_timestamp() - self.clean_retention_period
                    nr_elements_removed = self.redis.zremrangebyscore(name=key_name, min=0, max=remove_before_timestamp)
                    total_records_after_purge = self.redis.zcount(name=key_name, min=0, max=self.time_provider.get_utc_now_timestamp())
                    logger.debug(f'{key_name}: Removed {nr_elements_removed} trades from redis before {readable(remove_before_timestamp)}, '
                                 f'nr of remaining records = {total_records_after_purge}')
                last_clean = self.time_provider.get_utc_now_timestamp()

            time.sleep(self.clean_sleep)

    async def _handle_trade(self, trade: Trade, receipt_timestamp: float):
        self.redis.zadd(name=Cryptofeed.TRADEPRICE_SYMBOL + trade.raw['s'], mapping={trade.raw['p']: trade.raw['T']})

    @staticmethod
    def start_process(redis_host: str,
                      redis_port: int,
                      command_queue: Queue,
                      logging_queue: Queue,
                      plugin_config):
        setproctitle('HB_Cryptofeed_Plugin')
        cryptofeed_instance = Cryptofeed(redis_host=redis_host,
                                         redis_port=redis_port,
                                         command_queue=command_queue,
                                         logging_queue=logging_queue,
                                         plugin_config=plugin_config)
        cryptofeed_instance.run()
