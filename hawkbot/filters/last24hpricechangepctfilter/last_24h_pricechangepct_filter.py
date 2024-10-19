import collections
import logging
from typing import List, Dict

from hawkbot.core.data_classes import ChangeStatistic, FilterResult, ExchangeState
from hawkbot.core.filters.filter import Filter
from hawkbot.core.time_provider import now_timestamp
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.utils import fill_optional_parameters

logger = logging.getLogger(__name__)


class Last24hPriceChangePctFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def __init__(self, bot, name: str, filter_config, redis_host: str, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange = None  # Injected by framework
        self.exchange_state: ExchangeState = None  # Injected by framework
        self.sort: str = None
        self.sort_absolute: bool = False
        self.top: int = None
        self.max_price_change_pct: float = None
        self.min_price_change_pct: float = None
        self.init_config(self.filter_config)

        self.first_iteration = now_timestamp()

    def init_config(self, filter_config):
        fill_optional_parameters(target=self,
                                 config=filter_config,
                                 optional_parameters=['sort',
                                                      'top',
                                                      'sort_absolute',
                                                      'max_price_change_pct',
                                                      'min_price_change_pct'])

        if self.top is None and self.sort is None:
            raise InvalidConfigurationException("Either the parameter 'sort' and/or 'top' needs to be specified for "
                                                "the Last24hPriceChangePctFilter")

        if self.sort and self.sort != 'desc' and self.sort != 'asc':
            raise InvalidConfigurationException(f"The value '{self.sort}' is not allowed for the parameter 'sort'; "
                                                f"only the values 'asc' and 'desc' are allowed")

    def filter_symbols(self,
                       starting_list: List[str],
                       first_filter: bool,
                       previous_filter_results: List[FilterResult]) -> Dict[str, Dict]:
        if first_filter:
            starting_list = self.exchange_state.get_all_symbol_informations_by_symbol().keys()

        ordered_pricechangepct = collections.OrderedDict()
        changes: Dict[str, ChangeStatistic] = self.exchange.fetch_last_24h_changes()
        for symbol in starting_list:
            pricechange_pct = changes[symbol].priceChangePct
            if self.sort_absolute is True:
                pricechange_pct = abs(pricechange_pct)
            if self.max_price_change_pct is not None:
                if pricechange_pct > self.max_price_change_pct:
                    logger.info(f'Skipping symbol {symbol} because the price change pct {pricechange_pct} is more than the maximum allowed price change pct {self.max_price_change_pct}')
                    continue
            if self.min_price_change_pct is not None:
                if pricechange_pct < self.min_price_change_pct:
                    logger.info(f'Skipping symbol {symbol} because the price change pct {pricechange_pct} is less than the minimum allowed price change pct {self.min_price_change_pct}')
                    continue
            ordered_pricechangepct[pricechange_pct] = symbol

        if self.sort is not None:
            reverse = True if self.sort == 'desc' else False
            ordered_pricechangepct = sorted(ordered_pricechangepct.items(), reverse=reverse)

        selected_list = [row for price_changepct, row in ordered_pricechangepct]
        if self.top:
            selected_list = selected_list[:self.top]

        filtered_list = {}
        for entry in selected_list:
            filtered_list[entry] = {}
        return filtered_list
