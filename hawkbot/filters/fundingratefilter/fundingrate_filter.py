import collections
import logging
from typing import List, Dict

from hawkbot.core.data_classes import ChangeStatistic, FilterResult, ExchangeState
from hawkbot.core.filters.filter import Filter
from hawkbot.core.time_provider import now_timestamp
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.utils import fill_optional_parameters

logger = logging.getLogger(__name__)


class FundingRateFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def __init__(self, bot, name: str, filter_config, redis_host: str, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange = None  # Injected by framework
        self.exchange_state: ExchangeState = None  # Injected by framework
        self.sort: str = None
        self.sort_absolute: bool = False
        self.select_above: float = None
        self.select_below: float = None
        self.top: int = None
        self.init_config(self.filter_config)

        self.first_iteration = now_timestamp()

    def init_config(self, filter_config):
        fill_optional_parameters(target=self,
                                 config=filter_config,
                                 optional_parameters=['sort',
                                                      'top',
                                                      'sort_absolute',
                                                      'select_above',
                                                      'select_below'])

        if self.top is None and self.sort is None:
            raise InvalidConfigurationException("Either the parameter 'sort' and/or 'top' needs to be specified for "
                                                "the FundingRateFilter")

        if self.sort and self.sort != 'desc' and self.sort != 'asc':
            raise InvalidConfigurationException(f"The value '{self.sort}' is not allowed for the parameter 'sort'; "
                                                f"only the values 'asc' and 'desc' are allowed")

        if self.select_above is not None and self.select_below is not None:
            raise InvalidConfigurationException("Only one of the parameters 'select_above' or 'select_below' can be specified for "
                                                "the FundingRateFilter")

    def filter_symbols(self,
                       starting_list: List[str],
                       first_filter: bool,
                       previous_filter_results: List[FilterResult]) -> Dict[str, Dict]:
        if first_filter:
            starting_list = self.exchange_state.get_all_symbol_informations_by_symbol().keys()

        ordered_funding_rates = collections.OrderedDict()
        funding_rates: Dict[str, float] = self.exchange.fetch_funding_rates()
        for symbol in starting_list:
            if symbol not in funding_rates:
                logger.info(f'No funding rate was found for {symbol:8f}')
                continue
            funding_rate = funding_rates[symbol]
            if self.select_below is not None and funding_rate > self.select_below:
                continue
            if self.select_above is not None and funding_rate < self.select_above:
                continue

            if self.sort_absolute is True:
                funding_rate = abs(funding_rate)
            if funding_rate not in ordered_funding_rates:
                ordered_funding_rates[funding_rate] = set()
            ordered_funding_rates[funding_rate].add(symbol)

        if self.sort is not None:
            reverse = True if self.sort == 'desc' else False
            ordered_funding_rates = sorted(ordered_funding_rates.items(), reverse=reverse)

        selected_list = []
        for funding_rate, symbols in ordered_funding_rates:
            selected_list.extend(symbols)
        if self.top:
            selected_list = selected_list[:self.top]

        filtered_list = {}
        for entry in selected_list:
            filtered_list[entry] = {}
        return filtered_list
