import logging
import random
from collections import OrderedDict
from typing import List, Dict

from hawkbot.core.data_classes import FilterResult
from hawkbot.core.filters.filter import Filter

logger = logging.getLogger(__name__)

'''
      {
        "filter": "RandomizerFilter"
      }
'''
class RandomizerFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def filter_symbols(self,
                       starting_list: List[str],
                       first_filter: bool,
                       previous_filter_results: List[FilterResult]) -> Dict[str, Dict]:
        keys = starting_list.copy()
        random.shuffle(keys)
        result = OrderedDict()
        for key in keys:
            result[key] = {}
        return result

