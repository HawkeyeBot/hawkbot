import logging
from typing import List, Dict

from hawkbot.core.data_classes import SymbolPositionSide, ExchangeState, FilterResult
from hawkbot.core.model import PositionSide
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.exchange.exchange import Exchange
from hawkbot.core.filters.filter import Filter

logger = logging.getLogger(__name__)


class MinNotionalFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def __init__(self, bot, name: str, filter_config, redis_host: str, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange_state: ExchangeState = None  # injected by framework
        self.exchange: Exchange = None  # injected by framework
        self.less_than: float = None
        self.more_than: float = None
        self.init_config(filter_config)

    def init_config(self, filter_config):
        if 'less_than' in filter_config:
            self.less_than = filter_config['less_than']

        if 'more_than' in filter_config:
            self.more_than = filter_config['more_than']

        if self.less_than is None and self.more_than is None:
            raise InvalidConfigurationException("There is no configuration value supplied for either 'less_than' or "
                                                "'more_than'. Either or both of these should be set when using the "
                                                "MinNotionalFilter")

        if self.less_than is not None and self.more_than is not None and self.less_than <= self.more_than:
            raise InvalidConfigurationException(f"The configured 'less_than' value of {self.less_than} needs to be "
                                                f"greater than the configured 'more_than' value of {self.more_than}")

    def filter_symbols(self,
                       starting_list: List[str],
                       first_filter: bool,
                       previous_filter_results: List[FilterResult]) -> Dict[str, Dict]:
        if first_filter:
            starting_list = self.exchange_state.get_all_symbol_informations_by_symbol().keys()

        current_prices = self.exchange.fetch_all_current_prices()

        filtered_symbols = {}
        for symbol in starting_list:
            symbol_information = self.exchange_state.get_symbol_information(symbol)
            current_price = current_prices[symbol].price
            minimum_quantity_notional = current_price * symbol_information.minimum_quantity
            symbol_min_notional = max(symbol_information.minimal_buy_cost, minimum_quantity_notional)

            if self.less_than is not None and symbol_min_notional > self.less_than:
                logger.debug(f"{symbol}: Not adding to the filtered symbol list because the "
                             f"minimum notional of {symbol_min_notional} is more than the specified 'less_than' value "
                             f"of {self.less_than}.")
                continue

            if self.more_than is not None and symbol_min_notional < self.more_than:
                logger.debug(f"{symbol}: Not adding to the filtered symbol list because the "
                             f"minimum notional of {symbol_min_notional} is less than the specified 'more_than' value "
                             f"of {self.more_than}.")
                continue

            logger.debug(f"{symbol}: Added to the filtered symbol list because the minimum notional "
                         f"of {symbol_min_notional} is more than the 'more_than' value of {self.more_than} and less "
                         f"than the 'less_than' value of {self.less_than}")
            filtered_symbols[symbol] = {}

        return filtered_symbols
