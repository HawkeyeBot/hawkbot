import logging
from typing import List, Dict

from hawkbot.core.candlestore.candlestore import Candlestore
from hawkbot.core.data_classes import SymbolPositionSide, Timeframe, Candle, FilterResult
from hawkbot.core.model import PositionSide
from hawkbot.core.time_provider import TimeProvider
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.core.filters.filter import Filter
from hawkbot.utils import readable

logger = logging.getLogger(__name__)


class TrendReversalFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def __init__(self, bot, name: str, filter_config, redis_host: str, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.candlestore_client: Candlestore = None  # Injected by framework
        self.time_provider: TimeProvider = None  # Injected by framework
        self.number_candles: int = None
        self.timeframe: Timeframe = None
        self.init_config(filter_config)

    def init_config(self, filter_config):
        if 'number_candles' in filter_config:
            self.number_candles = filter_config['number_candles']
        else:
            raise InvalidConfigurationException("The parameter 'number_candles' is not provided for the "
                                                "TrendReversalFilter")

        if self.number_candles < 4:
            raise InvalidConfigurationException("The parameter 'number_candles' needs to be at least 4")

        if 'timeframe' in filter_config:
            self.timeframe = Timeframe.parse(filter_config['timeframe'])
        else:
            raise InvalidConfigurationException("The parameter 'timeframe' is not provided for the TrendReversalFilter")

    def filter_symbols(self,
                       starting_list: List[SymbolPositionSide],
                       first_filter: bool,
                       position_side: PositionSide,
                       previous_filter_results: List[FilterResult]) -> Dict[SymbolPositionSide, Dict]:
        new_list = {}
        for symbol_positionside in starting_list:
            start = self.time_provider.get_utc_now_timestamp()
            symbol = symbol_positionside.symbol
            last_candles = self.candlestore_client.get_last_candles(symbol=symbol,
                                                                    timeframe=self.timeframe,
                                                                    amount=self.number_candles)
            if len(last_candles) < self.number_candles:
                logger.warning(f'{symbol} {position_side.name}: Number of candles retrieved ({len(last_candles)}) is '
                               f'less than the configured {self.number_candles} candles, skipping inclusion')
                continue
            if len(last_candles) == 0:
                logger.warning(f'{symbol} {position_side.name}: No candles were retrieved, skipping inclusion')
                continue

            last_close = max([candle.close_date for candle in last_candles])
            if last_close < self.time_provider.get_utc_now_timestamp() - self.timeframe.milliseconds:
                logger.info(f'{symbol} {position_side.name}: Last close date of {last_close} is more than '
                            f'{self.timeframe.milliseconds} ms ago, this indicates the candles are out of date. '
                            f'Skipping inclusion of this symbol.')
                continue

            elapsed = self.time_provider.get_utc_now_timestamp() - start
            logger.info(f'{symbol} {position_side.name}: Retrieved {self.number_candles} candles in {elapsed}ms')

            if position_side == PositionSide.LONG and \
                    self.swing_low_detected(symbol=symbol, position_side=position_side, candles=last_candles):
                new_list[symbol_positionside] = {'stoploss_price': last_candles[-2].low}
            if position_side == PositionSide.SHORT and \
                    self.swing_high_detected(symbol=symbol, position_side=position_side, candles=last_candles):
                new_list[symbol_positionside] = {'stoploss_price': last_candles[-2].high}

        return new_list

    def swing_low_detected(self, symbol: str, position_side: PositionSide, candles: List[Candle]) -> bool:
        first_candle = candles[-3]
        middle_candle = candles[-2]
        last_candle = candles[-1]

        if last_candle.close > first_candle.high and last_candle.close > middle_candle.high \
                and middle_candle.low < first_candle.low and middle_candle.low < last_candle.low\
                and first_candle.open > first_candle.close:
            logger.info(f'{symbol} {position_side.name}: SWING LOW detected: '
                        f'First candle: [start: {readable(first_candle.start_date)}, close: {first_candle.close}, low: {first_candle.low}, high: {first_candle.high}], '
                        f'Middle candle: [start: {readable(middle_candle.start_date)}, close: {middle_candle.close}, low: {middle_candle.low}, high: {middle_candle.high}], '
                        f'Last candle: [start: {readable(last_candle.start_date)}, close: {last_candle.close}, low: {last_candle.low}, high: {last_candle.high}]')
            return True
        else:
            logger.info(f'{symbol} {position_side.name}: SWING LOW NOT detected: '
                        f'First candle: [start: {readable(first_candle.start_date)}, close: {first_candle.close}, low: {first_candle.low}, high: {first_candle.high}], '
                        f'Middle candle: [start: {readable(middle_candle.start_date)}, close: {middle_candle.close}, low: {middle_candle.low}, high: {middle_candle.high}], '
                        f'Last candle: [start: {readable(last_candle.start_date)}, close: {last_candle.close}, low: {last_candle.low}, high: {last_candle.high}]')
            return False

    def swing_high_detected(self, symbol: str, position_side: PositionSide, candles: List[Candle]) -> bool:
        first_candle = candles[-3]
        middle_candle = candles[-2]
        last_candle = candles[-1]

        if last_candle.close < first_candle.low and last_candle.close < middle_candle.low \
                and middle_candle.high > first_candle.high and middle_candle.high > last_candle.high\
                and first_candle.open < first_candle.close:
            logger.info(f'{symbol} {position_side.name}: SWING HIGH detected: '
                        f'First candle: [start: {readable(first_candle.start_date)}, close: {first_candle.close}, low: {first_candle.low}, high: {first_candle.high}], '
                        f'Middle candle: [start: {readable(middle_candle.start_date)}, close: {middle_candle.close}, low: {middle_candle.low}, high: {middle_candle.high}], '
                        f'Last candle: [start: {readable(last_candle.start_date)}, close: {last_candle.close}, low: {last_candle.low}, high: {last_candle.high}]')
            return True
        else:
            logger.info(f'{symbol} {position_side.name}: SWING HIGH NOT detected: '
                        f'First candle: [start: {readable(first_candle.start_date)}, close: {first_candle.close}, low: {first_candle.low}, high: {first_candle.high}], '
                        f'Middle candle: [start: {readable(middle_candle.start_date)}, close: {middle_candle.close}, low: {middle_candle.low}, high: {middle_candle.high}], '
                        f'Last candle: [start: {readable(last_candle.start_date)}, close: {last_candle.close}, low: {last_candle.low}, high: {last_candle.high}]')
            return False
