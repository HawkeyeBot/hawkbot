import logging
from typing import List, Dict

from hawkbot.core.data_classes import FilterResult
from hawkbot.core.filters.filter import Filter
from hawkbot.exceptions import InvalidConfigurationException

logger = logging.getLogger(__name__)

'''
      {
        "filter": "SubListFilter",
        "config": {
          "size": 1
        }
      }
'''
class SubListFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def __init__(self, bot, name: str, filter_config, redis_host: str, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.size: int = None
        self.init_config(self.filter_config)

    def init_config(self, filter_config):
        if 'size' in filter_config:
            self.size = filter_config['size']

        if self.size is None:
            raise InvalidConfigurationException("The parameter 'size' needs to be specified for "
                                                "the SubListFilter")

    def filter_symbols(self,
                       starting_list: List[str],
                       first_filter: bool,
                       previous_filter_results: List[FilterResult]) -> Dict[str, Dict]:
        result = {}
        keys = list(starting_list)
        keys = keys[:self.size]
        for key in keys:
            result[key] = {}
        return result
