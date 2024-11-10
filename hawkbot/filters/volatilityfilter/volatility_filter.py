import logging
from typing import List, Dict

from hawkbot.core.candlestore.candlestore import Candlestore
from hawkbot.core.data_classes import Timeframe, ExchangeState, FilterResult
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.exchange.exchange import Exchange
from hawkbot.core.filters.filter import Filter
from hawkbot.utils import get_percentage_difference, readable

logger = logging.getLogger(__name__)


class VolatilityFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def __init__(self, bot, name: str, filter_config, redis_host: str, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange: Exchange = None  # Injected by framework
        self.exchange_state: ExchangeState = None  # Injected by framework
        self.candle_store: Candlestore = None  # Injected by framework
        self.positive_threshold: float = None
        self.negative_threshold: float = None
        self.reference_timeframe: Timeframe = None
        self.reference_candle_nr: int = None

        if 'positive_threshold' in self.filter_config:
            self.positive_threshold = self.filter_config['positive_threshold']
            if self.positive_threshold <= 0:
                raise InvalidConfigurationException(f"The parameter 'positive_threshold' contains a value of "
                                                    f"{self.positive_threshold} which is not supported. If specified, "
                                                    f"the value must be greater than 0.")
        if 'negative_threshold' in self.filter_config:
            self.negative_threshold = self.filter_config['negative_threshold']
            if self.negative_threshold >= 0:
                raise InvalidConfigurationException(f"The parameter 'negative_threshold' contains a value of "
                                                    f"{self.negative_threshold} which is not supported. If specified, "
                                                    f"the value must be less than 0.")

        if self.positive_threshold is None and self.negative_threshold is None:
            raise InvalidConfigurationException("Both parameters 'positive_threshold' and 'negative_threshold' are "
                                                "not specified, at least one of the two is mandatory when specifying "
                                                "the VolatilityFilter filter")

        if 'reference_timeframe' not in self.filter_config:
            raise InvalidConfigurationException("VolatilityFilter configuration is missing the mandatory parameter "
                                                "'reference_timeframe'")
        else:
            self.reference_timeframe = Timeframe.parse(self.filter_config['reference_timeframe'])

        if 'reference_candle_nr' not in self.filter_config:
            raise InvalidConfigurationException("VolatilityFilter configuration is missing the mandatory parameter "
                                                "'reference_candle_nr'")
        else:
            self.reference_candle_nr = int(self.filter_config['reference_candle_nr'])

        if self.reference_candle_nr <= 0:
            raise InvalidConfigurationException("The parameter 'reference_candle_nr' for the VolatilityFilter needs to "
                                                "be greater than 0")

    def filter_symbols(self,
                       starting_list: List[str],
                       first_filter: bool,
                       previous_filter_results: List[FilterResult]) -> Dict[str, Dict]:
        volatile_symbols = {}
        all_current_prices = self.exchange.fetch_all_current_prices()
        if first_filter:
            symbols_to_process = self.exchange_state.get_all_symbol_informations_by_symbol().keys()
        else:
            symbols_to_process = starting_list

        for symbol in symbols_to_process:
            add_symbol = False
            reference_candles = self.candle_store.get_last_candles(symbol=symbol,
                                                                   timeframe=self.reference_timeframe,
                                                                   amount=self.reference_candle_nr)
            last_candle_close_date = max([candle.close_date for candle in reference_candles])
            last_candle_close_date = readable(last_candle_close_date)
            new_price = all_current_prices[symbol].price

            if self.positive_threshold is not None:
                lowest_low = min([candle.low for candle in reference_candles])
                price_ratio_change = get_percentage_difference(lowest_low, new_price)
                if price_ratio_change > 0:
                    threshold_percentage = self.positive_threshold * 100
                    price_percentage_change = price_ratio_change * 100

                    if price_ratio_change >= self.positive_threshold:
                        logger.info(f"{symbol}: Adding to volatile symbols for potential "
                                    f"entry, price changed {price_percentage_change:.3f}% from the lowest low price "
                                    f"of {lowest_low} in the past {self.reference_candle_nr} candles of "
                                    f"{self.reference_timeframe.name} (last close: {last_candle_close_date}), current "
                                    f"price {new_price} is ABOVE the positive threshold {threshold_percentage}%")
                        add_symbol = True
                    else:
                        logger.info(f"{symbol}: Not Adding to volatile symbols for potential "
                                    f"entry, price changed {price_percentage_change:.3f}% from the lowest low price "
                                    f"of {lowest_low} in the past {self.reference_candle_nr} candles of "
                                    f"{self.reference_timeframe.name} (last close: {last_candle_close_date}), current "
                                    f"price {new_price} is BELOW the positive threshold {threshold_percentage}%")
                else:
                    logger.info(f"{symbol}: Not Adding to volatile symbols for potential "
                                f"entry, price did not change between lowest low {lowest_low} and {new_price} in the "
                                f"past {self.reference_candle_nr} candles of {self.reference_timeframe.name} "
                                f"(last close: {last_candle_close_date})")

            if self.negative_threshold is not None:
                highest_high = max([candle.high for candle in reference_candles])
                price_ratio_change = get_percentage_difference(highest_high, new_price)
                if price_ratio_change < 0:
                    threshold_percentage = self.negative_threshold * 100
                    price_percentage_change = price_ratio_change * 100

                    if price_ratio_change <= self.negative_threshold:
                        logger.info(f"{symbol}: Adding to volatile symbols for potential "
                                    f"entry, price changed {price_percentage_change:.3f}% from the highest high price "
                                    f"of {highest_high} in the past {self.reference_candle_nr} candles of "
                                    f"{self.reference_timeframe.name} (last close: {last_candle_close_date}), current "
                                    f"price {new_price} is ABOVE the negative threshold {threshold_percentage}%")
                        add_symbol = True
                    else:
                        logger.info(f"{symbol}: Not Adding to volatile symbols for potential "
                                    f"entry, price changed {price_percentage_change:.3f}% from the highest high price "
                                    f"of {highest_high} in the past {self.reference_candle_nr} candles of "
                                    f"{self.reference_timeframe.name} (last close: {last_candle_close_date}), current "
                                    f"price {new_price} is BELOW the negative threshold {threshold_percentage}%")
                else:
                    logger.info(f"{symbol}: Not Adding to volatile symbols for potential "
                                f"entry, price did not change between highest high {highest_high} and {new_price} in "
                                f"the past {self.reference_candle_nr} candles of {self.reference_timeframe.name} "
                                f"(last close: {last_candle_close_date})")

            if add_symbol:
                volatile_symbols[symbol] = symbol \
                    if symbol in starting_list else {}

        return volatile_symbols
