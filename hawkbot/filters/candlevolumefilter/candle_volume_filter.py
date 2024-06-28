import logging
from statistics import median
from typing import List, Dict

from hawkbot.core.candlestore.candlestore import Candlestore
from hawkbot.core.data_classes import ExchangeState, FilterResult
from hawkbot.core.data_classes import Timeframe
from hawkbot.core.filters.filter import Filter
from hawkbot.exceptions import InvalidConfigurationException

logger = logging.getLogger(__name__)


class CandleVolumeFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def __init__(self, bot, name: str, filter_config, redis_host, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.candle_store: Candlestore = None  # injected by framework
        self.exchange_state: ExchangeState = None  # injected by framework
        self.minimum_volume: float = None
        self.number_candles: int = None
        self.timeframe: Timeframe = None
        self.init_config(filter_config)
        logger.info(f'Init CandleVolumeFilter with minimum_volume = {self.minimum_volume} based on last '
                    f'{self.number_candles} candles of {self.timeframe.name}')
        
    def init_config(self, filter_config):
        if 'minimum_volume_M' not in filter_config:
            raise InvalidConfigurationException("CandleVolumeFilter configuration is missing the mandatory parameter "
                                                "'minimum_volume_M'")
        else:
            self.minimum_volume = filter_config['minimum_volume_M'] * 1_000_000

        if 'timeframe' not in filter_config:
            raise InvalidConfigurationException("CandleVolumeFilter configuration is missing the mandatory parameter "
                                                "'timeframe'")
        else:
            self.timeframe = Timeframe.parse(filter_config['timeframe'])

        if 'number_candles' not in filter_config:
            raise InvalidConfigurationException("CandleVolumeFilter configuration is missing the mandatory parameter "
                                                "'timeframe'")
        else:
            self.number_candles = int(filter_config['number_candles'])

        if self.number_candles <= 0:
            raise InvalidConfigurationException(f"The value of 'number_candles' {self.number_candles} for "
                                                f"CandleVolumeFilter needs to greater than 0")

    def filter_symbols(self,
                       starting_list: List[str],
                       first_filter: bool,
                       previous_filter_results: List[FilterResult]) -> Dict[str, Dict]:
        if first_filter:
            starting_list = self.exchange_state.get_all_symbol_informations_by_symbol().keys()

        filtered_symbols = {}
        for symbol in starting_list:
            candles = self.candle_store.get_last_candles(symbol=symbol,
                                                         timeframe=self.timeframe,
                                                         amount=self.number_candles)

            median_volume = median([candle.quote_volume for candle in candles])

            if median_volume >= self.minimum_volume:
                logger.info(f"ADDING {symbol} to filtered symbols with because median volume of "
                            f"{median_volume} is equal or greater than the required minimum volume of "
                            f"{self.minimum_volume}")
                filtered_symbols[symbol] = {}
            else:
                logger.info(f"NOT ADDING {symbol} to filtered symbols with because median volume of "
                            f"{median_volume} is less than the required minimum volume of {self.minimum_volume}")

        return filtered_symbols
