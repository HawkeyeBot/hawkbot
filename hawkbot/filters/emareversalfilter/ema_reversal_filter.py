import logging
from enum import Enum
from typing import List, Dict

from hawkbot.core.candlestore.candlestore import Candlestore
from hawkbot.core.data_classes import FilterResult
from hawkbot.core.filters.filter import Filter
from hawkbot.core.model import Timeframe
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.utils import fill_required_parameters
import ta.trend
from pandas import DataFrame

logger = logging.getLogger(__name__)


class Pivot(Enum):
    TOP = 'TOP'
    BOTTOM = 'BOTTOM'


class EmaReversalFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def __init__(self, bot, name: str, filter_config, redis_host: str, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.candle_store: Candlestore = None  # injected by framework
        self.window: int = None
        self.timeframe: Timeframe = None
        self.pivot: Pivot = None
        self.init_config(filter_config)

    def init_config(self, filter_config):
        fill_required_parameters(target=self,
                                 config=filter_config,
                                 required_parameters=['window'])

        if 'timeframe' in filter_config:
            self.timeframe = Timeframe.parse(filter_config['timeframe'])
        else:
            raise InvalidConfigurationException('The parameter \'timeframe\' is mandatory')

        if 'pivot' in filter_config:
            self.pivot = Pivot[filter_config['pivot']]
        else:
            raise InvalidConfigurationException('The parameter \'pivot\' is mandatory')

    def filter_symbols(self,
                       starting_list: List[str],
                       first_filter: bool,
                       previous_filter_results: List[FilterResult]) -> Dict[str, Dict]:
        filtered_symbols = {}
        for symbol in starting_list:
            candles = self.candle_store.get_last_candles(symbol=symbol, timeframe=self.timeframe, amount=self.window + 1)
            ema = ta.trend.ema_indicator(close=DataFrame(candles)["close"], window=self.window)
            if self.pivot is Pivot.BOTTOM:
                if ema.iloc[-1] > ema.iloc[-2]:
                    logger.info(f'{symbol}: BOTTOM - last EMA {ema.iloc[-1]} is higher than previous EMA {ema.iloc[-2]}, '
                                f'indicating a potential trend reversal, allowing_symbol')
                    filtered_symbols[symbol] = {}
                else:
                    logger.info(f'{symbol}: BOTTOM - last EMA {ema.iloc[-1]} is equal or less than previous EMA {ema.iloc[-2]}, '
                                f'not a potential candidate')
            else:
                if ema.iloc[-1] < ema.iloc[-2]:
                    logger.info(f'{symbol}: TOP - last EMA {ema.iloc[-1]} is lower than previous EMA {ema.iloc[-2]}, '
                                f'indicating a potential trend reversal, allowing symbol')
                    filtered_symbols[symbol] = {}
                else:
                    logger.info(f'{symbol}: TOP - last EMA {ema.iloc[-1]} is equal or more than previous EMA {ema.iloc[-2]}, '
                                f'not a potential candidate')

        return filtered_symbols
