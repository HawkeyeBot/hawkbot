import logging
from typing import List, Dict

import pandas as pd
from ta.volatility import AverageTrueRange

from hawkbot.core.candlestore.candlestore import Candlestore
from hawkbot.core.data_classes import ExchangeState, FilterResult
from hawkbot.core.model import Timeframe
from hawkbot.exchange.exchange import Exchange
from hawkbot.core.filters.filter import Filter

logger = logging.getLogger(__name__)


class ATRFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def __init__(self, bot, name: str, filter_config, redis_host: str, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange_state: ExchangeState = None  # injected by framework
        self.exchange: Exchange = None  # injected by framework
        self.candlestore_client: Candlestore = None  # injected by framework

    def filter_symbols(self,
                       starting_list: List[str],
                       first_filter: bool,
                       previous_filter_results: List[FilterResult]) -> Dict[str, Dict]:
        if first_filter:
            starting_list = self.exchange_state.get_all_symbol_informations_by_symbol().keys()

        symbol_data = {}
        for symbol in starting_list:
            # Get all futures symbols
            try:
                symbol_data[symbol] = self.calculate_indicators(symbol)
            except Exception:
                logger.exception(f"{symbol}: Error calculating ATR")

        sorted_symbols = sorted(symbol_data.items(), key=lambda x:x[1], reverse=True)
        sorted_symbols = [symbol for symbol, _ in sorted_symbols]
        filtered_symbols = {}
        for symbol in sorted_symbols:
            filtered_symbols[symbol] = {}

        return filtered_symbols

    def calculate_indicators(self, symbol: str, timeframe: Timeframe = Timeframe.FIVE_MINUTES, lookback_period: int = 14) -> float:
        # Fetch historical candle data for the symbol
        candles = self.candlestore_client.get_last_candles(symbol=symbol, timeframe=timeframe, amount=lookback_period)

        # Create a DataFrame
        df = pd.DataFrame(candles, columns=['open', 'high', 'low', 'close', 'volume'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])

        # Calculate ATRP
        atr_indicator = AverageTrueRange(df['high'], df['low'], df['close'], window=lookback_period)
        df['atr'] = atr_indicator.average_true_range()
        atrp = (df['atr'] / df['close']) * 100
        return atrp.iloc[-1]
