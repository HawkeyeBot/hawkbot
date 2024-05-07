import logging
from typing import List, Dict

from hawkbot.core.data_classes import ExchangeState, FilterResult
from hawkbot.core.filters.filter import Filter
from hawkbot.core.time_provider import TimeProvider
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.utils import period_as_ms

logger = logging.getLogger(__name__)

'''
      {
        "filter": "AgeFilter",
        "config": {
          "older_than": "5D",
          "newer_than": "1Y"
        }
      }
'''


class AgeFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def __init__(self, bot, name: str, filter_config, redis_host: str, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange_state: ExchangeState = None  # injected by framework
        self.time_provider: TimeProvider = None  # injected by framework
        self.older_than: float = None
        self.older_than_ms: float = None
        self.newer_than: float = None
        self.newer_than_ms: float = None
        self.init_config(filter_config)

    def init_config(self, filter_config):
        if 'older_than' in filter_config:
            self.older_than = filter_config['older_than']

        if 'newer_than' in filter_config:
            self.newer_than = filter_config['newer_than']

        if self.older_than is None and self.newer_than is None:
            raise InvalidConfigurationException("There is no configuration value supplied for either 'older_than' or "
                                                "'newer_than'. Either or both of these should be set when using the "
                                                "AgeFilter")

        if self.older_than is not None:
            self.older_than_ms = period_as_ms(self.older_than)

        if self.newer_than is not None:
            self.newer_than_ms = period_as_ms(self.newer_than)

        if self.newer_than_ms is not None and self.older_than_ms is not None \
                and self.older_than_ms >= self.newer_than_ms:
            raise InvalidConfigurationException(f"The configured 'older_than' value of {self.older_than} needs to be "
                                                f"less than the configured 'newer_than' value of {self.newer_than}")

    def filter_symbols(self,
                       starting_list: List[str],
                       first_filter: bool,
                       previous_filter_results: List[FilterResult]) -> Dict[str, Dict]:
        if first_filter:
            starting_list = self.exchange_state.get_all_symbol_informations_by_symbol().keys()

        filtered_symbols = {}
        for symbol in starting_list:
            symbol_information = self.exchange_state.get_symbol_information(symbol)

            ms_since_launch = self.time_provider.get_utc_now_timestamp() - symbol_information.onboard_date

            if ms_since_launch < 0:
                logger.debug(f"{symbol}: Not adding to the filtered symbol list because the time "
                             f"passed since launch ({ms_since_launch}ms) passed since launch is invalid")
                continue
            if self.older_than_ms is not None and ms_since_launch < self.older_than_ms:
                logger.debug(f"{symbol}: Not adding to the filtered symbol list because the since "
                             f"launch ({ms_since_launch}ms) is less than the specified 'older_than' value "
                             f"of {self.older_than} ({self.older_than_ms}ms)")
                continue

            if self.newer_than_ms is not None and ms_since_launch > self.newer_than_ms:
                logger.debug(f"{symbol}: Not adding to the filtered symbol list because the time "
                             f"passed since launch ({ms_since_launch}ms) is more than the specified 'newer_than' value "
                             f"of {self.newer_than} ({self.newer_than_ms}ms)")
                continue

            logger.debug(f"{symbol}: Added to the filtered symbol list because the time passed since "
                         f"launch ({ms_since_launch}ms) is more than the 'older_than' value of "
                         f"{self.older_than} ({self.older_than_ms}ms) and less than the 'newer_than' value of "
                         f"{self.newer_than} ({self.newer_than_ms})ms")
            filtered_symbols[symbol] = {}

        return filtered_symbols
