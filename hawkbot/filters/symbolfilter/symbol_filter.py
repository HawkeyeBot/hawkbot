import logging
import re
from re import Pattern
from typing import List, Dict

from hawkbot.core.data_classes import ExchangeState, FilterResult
from hawkbot.core.filters.filter import Filter

logger = logging.getLogger(__name__)

'''
      {
        "filter": "SymbolFilter",
        "config": {
          "whitelist": [".*USDT"],
          "blacklist": ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        }
      }
'''
class SymbolFilter(Filter):
    def __init__(self, bot, name: str, filter_config, redis_host, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.blacklist_filters: List[Pattern] = []
        self.whitelist_filters: List[Pattern] = []
        self.exchange_state: ExchangeState = None  # injected by framework
        self.init_config(self.filter_config)

    @classmethod
    def filter_name(cls):
        return cls.__name__

    def init_config(self, filter_config):
        if 'whitelist' in filter_config:
            [self.whitelist_filters.append(re.compile(f'{regex}$')) for regex in filter_config['whitelist']]

        if 'blacklist' in filter_config:
            [self.blacklist_filters.append(re.compile(f'{regex}$')) for regex in filter_config['blacklist']]

    def filter_symbols(self,
                       starting_list: List[str],
                       first_filter: bool,
                       previous_filter_results: List[FilterResult]) -> Dict[str, Dict]:
        if first_filter:
            starting_list = self.exchange_state.get_all_symbol_informations_by_symbol().keys()

        filtered_symbols = {}
        if len(self.whitelist_filters) > 0:
            for whitelist_filter in self.whitelist_filters:
                for row in starting_list:
                    if whitelist_filter.match(row):
                        filtered_symbols[row] = {}
            logger.debug(f'The following symbols are selected based on the set whitelist filter: {[row for row in filtered_symbols]}')
        else:
            logger.debug('Adding all symbols because no whitelist is set')
            for row in starting_list:
                filtered_symbols[row] = {}

        symbols_to_remove: List[str] = []
        if len(self.blacklist_filters) > 0:
            for blacklist_filter in self.blacklist_filters:
                [symbols_to_remove.append(row) for row in filtered_symbols.keys() if blacklist_filter.match(row)]

        if len(symbols_to_remove) > 0:
            logger.debug(f'Removing the following symbols because of the set blacklist: '
                         f'{[row for row in symbols_to_remove]}')
        [filtered_symbols.pop(row) for row in symbols_to_remove if row in filtered_symbols]

        return filtered_symbols
