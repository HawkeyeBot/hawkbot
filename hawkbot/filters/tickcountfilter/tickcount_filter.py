import logging
from typing import List, Dict

from redis import Redis

from hawkbot.core.data_classes import FilterResult
from hawkbot.core.time_provider import now_timestamp
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.core.filters.filter import Filter
from hawkbot.plugins.cryptofeed_plugin.cryptofeed import Cryptofeed
from hawkbot.utils import period_as_ms, readable

logger = logging.getLogger(__name__)


class TickcountFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def __init__(self, bot, name: str, filter_config, redis_host: str, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.redis = Redis(host=self.redis_host, port=self.redis_port, decode_responses=True)
        self.lookback_period = period_as_ms(filter_config['lookback_period'])
        self.minimum_age: int = None
        self._minimum_age_ms: int = None
        self.sort = None

        if 'sort' in filter_config:
            self.sort = filter_config['sort']
            if self.sort not in ['asc', 'desc']:
                raise InvalidConfigurationException("If specified, the parameter 'sort' needs to be specified as either 'asc' or 'desc' for the TickcounterFilter")

        self.top = None
        if 'top' in filter_config:
            self.top = filter_config['top']

        if 'minimum_age' in filter_config:
            self.minimum_age = filter_config['minimum_age']
            self._minimum_age_ms = period_as_ms(self.minimum_age)

    def filter_symbols(self,
                       starting_list: List[str],
                       first_filter: bool,
                       previous_filter_results: List[FilterResult]) -> Dict[str, Dict]:
        self._subscribe_to_symbols(symbols=[symbol for symbol in starting_list])
        symbols_by_tickcount = self.symbols_by_tickcount()
        sort_descending = self.sort is None or self.sort == 'desc'
        sorted_symbols = sorted(symbols_by_tickcount.items(), key=lambda x: x[1], reverse=sort_descending)
        if self.top is not None:
            sorted_symbols = sorted_symbols[:self.top]

        filtered_symbols = {}
        for symbol, _ in sorted_symbols:
            if symbol in starting_list:
                logger.debug(f"{symbol}: Allowing symbol based on tick count {symbols_by_tickcount[symbol]}")
                filtered_symbols[symbol] = {}
            else:
                logger.debug(f"{symbol}: Discarding symbol because it's not in starting list")

        return filtered_symbols

    def _subscribe_to_symbols(self, symbols: List[str]):
        for symbol in symbols:
            logger.debug(f"{symbol}: Sending subscription message to cryptofeed")
            self.redis.publish(channel=Cryptofeed.LISTENTO_SYMBOL, message=symbol)

    def symbols_by_tickcount(self) -> Dict[int, str]:
        result = {}
        trade_key_names = [i for i in self.redis.scan(match=f'{Cryptofeed.TRADEPRICE_SYMBOL}*', count=1000000)[1]]
        now = now_timestamp()
        for key_name in trade_key_names:
            symbol = key_name.replace(Cryptofeed.TRADEPRICE_SYMBOL, "")
            if self._minimum_age_ms is not None:
                earliest_timestamp = int(self.redis.zrange(name=key_name, start=0, end=0, withscores=True)[0][1])
                threshold = now - self._minimum_age_ms
                if earliest_timestamp > threshold:
                    logger.debug(f'{symbol}: Ignoring symbol because the earliest tick is at {readable(earliest_timestamp)}, which is not older than the specified minimum age of '
                                f'{self.minimum_age}, meaning the earliest tick needs to be before {readable(threshold)}')
                    continue
            result[symbol] = self.redis.zcount(name=key_name, min=now - self.lookback_period, max=now)
        return result
