import collections
import logging
from typing import List, Dict

from redis import Redis

from hawkbot.core.data_classes import ChangeStatistic, FilterResult, ExchangeState
from hawkbot.core.filters.filter import Filter
from hawkbot.core.time_provider import now_timestamp
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.utils import fill_optional_parameters

logger = logging.getLogger(__name__)


class DynamicPriceChangePctFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def __init__(self, bot, name: str, filter_config, redis_host: str, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange = None  # Injected by framework
        self.exchange_state: ExchangeState = None  # Injected by framework
        self.min_absolute_price_change_pct_threshold: float = None
        self.use_sorted_symbols_mean_average_pricechangepct: bool = None  # New boolean param
        self.redis = Redis(host=redis_host, port=redis_port, decode_responses=True)
        self.init_config(self.filter_config)

        self.first_iteration = now_timestamp()

    def init_config(self, filter_config):
        fill_optional_parameters(target=self,
                                 config=filter_config,
                                 optional_parameters=['min_absolute_price_change_pct_threshold',
                                                      'use_sorted_symbols_mean_average_pricechangepct'])

        if self.min_absolute_price_change_pct_threshold is None:
            raise InvalidConfigurationException("The parameter 'min_absolute_price_change_pct_threshold' needs to be specified.")
        if self.use_sorted_symbols_mean_average_pricechangepct is None:
            raise InvalidConfigurationException("The parameter 'use_sorted_symbols_mean_average_pricechangepct' needs to be specified.")

    def filter_symbols(self,
                       starting_list: List[str],
                       first_filter: bool,
                       previous_filter_results: List[FilterResult]) -> Dict[str, Dict]:
        if first_filter:
            starting_list = self.exchange_state.get_all_symbol_informations_by_symbol().keys()

        ordered_pricechangepct = collections.OrderedDict()
        changes: Dict[str, ChangeStatistic] = self.exchange.fetch_last_24h_changes()
        total_price_change_pct = 0
        count = 0

        # filter based on the absolute pricechangepct threshold
        for symbol in starting_list:
            pricechange_pct = changes[symbol].priceChangePct

            if abs(pricechange_pct) < self.min_absolute_price_change_pct_threshold:
                continue  # skip if pricechangepct is below the threshold

            ordered_pricechangepct[pricechange_pct] = symbol
            total_price_change_pct += pricechange_pct
            count += 1

        # always sort desc
        ordered_pricechangepct = sorted(ordered_pricechangepct.items(), reverse=True)

        # calculate mean average pricechangepct
        mean_average_price_change_pct = total_price_change_pct / count if count > 0 else 0

        filtered_list = {}
        redis_prefix = 'DynamicPriceChangePctFilter'
        for price_changepct, symbol in ordered_pricechangepct:
            long = price_changepct < 0  # true if negative
            short = price_changepct > 0  # true if is positive
            symbol_data = {
                'priceChangePct': price_changepct,
                'sorted_symbols_mean_average_pricechangepct': mean_average_price_change_pct,
                'long': int(long),
                'short': int(short),
                'use_sorted_symbols_mean_average_pricechangepct': int(self.use_sorted_symbols_mean_average_pricechangepct)
            }
            filtered_list[symbol] = symbol_data
            # store in redis
            self.redis.hmset(f'{redis_prefix}_filtered_symbol_{symbol}', symbol_data)

        logger.info(f'selected list: {filtered_list}')
        return filtered_list
