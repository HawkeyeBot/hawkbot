import logging
import threading

from redis import Redis

from hawkbot.core.data_classes import ExchangeState
from hawkbot.core.model import BotStatus, Income
from hawkbot.core.time_provider import TimeProvider
from hawkbot.exchange.exchange import Exchange
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.utils import readable, fill_required_parameters, fill_optional_parameters, period_as_ms

logger = logging.getLogger(__name__)


class IncomeTriggerPlugin(Plugin):
    INCOME_SYMBOL = 'income_'

    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange: Exchange = None  # Injected by plugin loader
        self.exchange_state: ExchangeState = None  # Injected by plugin loader
        self.time_provider: TimeProvider = None  # Injected by plugin loader
        self.status: BotStatus = BotStatus.NEW
        self.trigger_event: threading.Event = threading.Event()
        self.enabled: bool = True
        self.check_interval: str = None
        self._check_interval_s: int = None
        self.expiry_threshold: str = None
        self._expiry_threshold_ms: int = None
        self.initial_lookback: str = None

        self.redis = Redis(host="127.0.0.1", port=redis_port, decode_responses=True)
        self.last_processed_income_timestamp: Income = None

        self.init(plugin_config)

    def init(self, plugin_config):
        required_parameters = ['check_interval', 'expiry_threshold', 'initial_lookback']
        optional_parameters = ['enabled']

        fill_required_parameters(target=self, config=plugin_config, required_parameters=required_parameters)
        fill_optional_parameters(target=self, config=plugin_config, optional_parameters=optional_parameters)

        self._check_interval_s = period_as_ms(self.check_interval) / 1000
        self._expiry_threshold_ms = period_as_ms(self.expiry_threshold)

    def start(self):
        self.status = BotStatus.STARTING
        transfer_thread = threading.Thread(name=f'income_trigger_plugin',
                                           target=self.process_schedule,
                                           daemon=True)
        transfer_thread.start()

    def process_schedule(self):
        self.status = BotStatus.RUNNING
        while self.status == BotStatus.RUNNING:
            if self.enabled:
                try:
                    self.update_income_triggers()
                    self.purge_expired_incomes()
                except:
                    logger.exception('Failed to check incomes')

            self.trigger_event.wait(self._check_interval_s)
        self.status = BotStatus.STOPPED

    def purge_expired_incomes(self):
        purge_before_timestamp = self.time_provider.get_utc_now_timestamp() - self._expiry_threshold_ms
        symbol_keys = self.redis.scan(match=self.INCOME_SYMBOL + '*', count=1000000)[1]
        for symbol_key in symbol_keys:
            nr_removed = self.redis.zremrangebyscore(symbol_key, 0, purge_before_timestamp)
            if nr_removed > 0:
                logger.info(f'{symbol_key}: Removed {nr_removed} entries from income before timestamp {readable(purge_before_timestamp)}')

    def update_income_triggers(self):
        now = self.time_provider.get_utc_now_timestamp()
        if self.last_processed_income_timestamp is None:
            self.last_processed_income_timestamp = self.time_provider.get_utc_now_timestamp() - period_as_ms(self.initial_lookback)

        new_incomes = self.exchange.fetch_incomes(start_time=self.last_processed_income_timestamp + 1, end_time=now)
        if len(new_incomes) > 0:
            unique_symbols = set([income.symbol for income in new_incomes])
            for symbol in unique_symbols:
                symbol_incomes = [income for income in new_incomes if income.symbol == symbol]
                last_symbol_timestamp = max([income.timestamp for income in symbol_incomes])
                total_new_profit = sum([income.income for income in symbol_incomes])

                logger.info(f'{symbol}: Persisting total profit of {total_new_profit} from {len(symbol_incomes)} incomes between {readable(self.last_processed_income_timestamp)} and '
                            f'{readable(last_symbol_timestamp)}')
                [self.redis.zadd(self.INCOME_SYMBOL + symbol, {income.income: income.timestamp}) for income in symbol_incomes]

            self.last_processed_income_timestamp = max([income.timestamp for income in new_incomes])
        else:
            logger.info(f'No new incomes to store since {readable(self.last_processed_income_timestamp)}')
            self.last_processed_income_timestamp = now

    def stop(self):
        self.status = BotStatus.STOPPING
        self.trigger_event.set()
