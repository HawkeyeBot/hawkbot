import collections
import logging
from typing import List, Dict

from hawkbot.core.data_classes import ChangeStatistic, FilterResult, ExchangeState
from hawkbot.core.filters.filter import Filter
from hawkbot.core.time_provider import now_timestamp
from hawkbot.exceptions import InvalidConfigurationException

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
        self.top: int = None
        self.init_config(self.filter_config)

        self.first_iteration = now_timestamp()

    def init_config(self, filter_config):
        if 'sort' in filter_config:
            self.sort = filter_config['sort']

        if 'top' in filter_config:
            self.top = filter_config['top']

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
            ordered_pricechangepct[pricechange_pct] = symbol

        if self.sort is not None:
            reverse = True if self.sort == 'desc' else False
            ordered_volume = sorted(ordered_pricechangepct.items(), reverse=reverse)

        selected_list = [row for volume, row in ordered_pricechangepct]
        if self.top:
            selected_list = selected_list[:self.top]

        filtered_list = {}
        for entry in selected_list:
            filtered_list[entry] = {}
        return filtered_list
