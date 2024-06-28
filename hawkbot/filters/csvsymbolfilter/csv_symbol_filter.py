import logging
import os
from typing import List, Dict

from hawkbot.core.data_classes import ExchangeState, FilterResult
from hawkbot.core.filters.filter import Filter
from hawkbot.utils import fill_required_parameters

logger = logging.getLogger(__name__)

'''
        "CsvSymbolFilter": {
          "csvfullpath": "/data/hawkbot/symbols.csv"
        },
'''


class CsvSymbolFilter(Filter):
    def __init__(self, bot, name: str, filter_config, redis_host: str, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange_state: ExchangeState = None  # injected by framework
        self.csvfullpath: str = None
        self.init_config(filter_config)

    @classmethod
    def filter_name(cls):
        return cls.__name__

    def init_config(self, filter_config):
        fill_required_parameters(target=self, config=filter_config, required_parameters=['csvfullpath'])

    def filter_symbols(self,
                       starting_list: List[str],
                       first_filter: bool,
                       previous_filter_results: List[FilterResult]) -> Dict[str, Dict]:
        if not os.path.exists(self.csvfullpath):
            logger.debug(f'Symbol CSV {self.csvfullpath} does not exist, returning empty dict')
            return {}

        result = {}
        with open(self.csvfullpath) as file:
            allowed_symbols = [i.strip() for i in file]
        if first_filter:
            for allowed_symbol in allowed_symbols:
                result[allowed_symbol] = {}
        else:
            for starting_symbol in starting_list:
                if starting_symbol in allowed_symbols:
                    result[starting_symbol] = {}

        symbols_on_exchange = self.exchange_state.get_all_symbol_informations_by_symbol()
        filtered_result = {}
        for symbol in result.keys():
            if symbol in symbols_on_exchange.keys():
                filtered_result[symbol] = result[symbol]
            else:
                logger.info(f"{symbol}: Not allowing specified symbol because it's not a known symbol on the exchange")

        return filtered_result
