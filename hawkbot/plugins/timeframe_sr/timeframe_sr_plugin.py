import logging
from typing import List, Dict

import numpy as np

from hawkbot.core.candlestore.candlestore import Candlestore
from hawkbot.core.candlestore.candlestore_listener import CandlestoreListener
from hawkbot.core.data_classes import Timeframe, Candle
from hawkbot.core.time_provider import TimeProvider
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.plugins.timeframe_sr.data_classes import SupportResistance, LevelType
from hawkbot.plugins.timeframe_sr.timeframe_sr_repository import TimeframeSupportResistanceRepository
from hawkbot.utils import round_

logger = logging.getLogger(__name__)


class TimeframeSupportResistancePlugin(Plugin, CandlestoreListener):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.candlestore: Candlestore = None
        self.repository: TimeframeSupportResistanceRepository = TimeframeSupportResistanceRepository(plugin_config)
        self.time_provider: TimeProvider = None

    def start(self):
        super().start()
        self.candlestore.add_listener(listener=self)

    def on_new_candle(self, candle: Candle):
        cache_valid_until = self.repository.cache_valid_until(symbol=candle.symbol,
                                                              timeframe=candle.timeframe)
        if candle.close_date > cache_valid_until:
            self.get_or_update_sr_from_cache(symbol=candle.symbol,
                                             timeframes=[candle.timeframe])
        else:
            logger.warning(f'Received candle whose close date ({candle.close_date}) was at or before the cache valid '
                           f'date of {cache_valid_until}')

    def get_or_update_sr_from_cache(self,
                                    symbol: str,
                                    timeframes: List[Timeframe]) -> Dict[Timeframe, SupportResistance]:
        support_resistances = {}
        timeframes.sort(key=lambda x: x.milliseconds)
        cache_changed = False
        for timeframe in set(timeframes):
            if self.should_refresh_cache(symbol=symbol, timeframe=timeframe):
                latest_candle = self.candlestore.get_last_candles(symbol=symbol, timeframe=timeframe, amount=1)
                last_closing_date = latest_candle[0].close_date
                if last_closing_date > self.repository.cache_valid_until(symbol=symbol, timeframe=timeframe):
                    cache_changed = True
                    candles = self.candlestore.get_candles(symbol=symbol, timeframe=timeframe)

                    support_resistance = self._get_levels_for_timeframe(candles=candles)
                    logger.debug(f'{symbol}: '
                                 f'Calculated supports for {timeframe.name} = {support_resistance.supports}, '
                                 f'calculated resistances for {timeframe.name} = {support_resistance.resistances}')

                    self.repository.set_in_cache(symbol=symbol,
                                                 timeframe=timeframe,
                                                 last_candle_close=last_closing_date,
                                                 support_resistance=support_resistance)
            sr_from_cache = self.repository.get_from_cache(symbol=symbol, timeframe=timeframe)
            support_resistances[timeframe] = sr_from_cache.support_resistance

        if cache_changed is True:
            logger.info(f'{symbol}: Supports/resistances are {support_resistances}')

        return support_resistances

    def get_support_resistance_levels(self,
                                      symbol: str,
                                      timeframes: List[Timeframe],
                                      even_price: float,
                                      price_step: float) -> Dict[Timeframe, SupportResistance]:
        support_resistances = self.get_or_update_sr_from_cache(symbol=symbol,
                                                               timeframes=timeframes)
        final_support_levels = {}

        for timeframe in set(timeframes):
            support_resistance = support_resistances[timeframe]
            rounded_support_prices = {}
            rounded_resistance_prices = {}

            for price, level_type in support_resistance.supports.items():
                if price < even_price:
                    rounded_support_prices[round_(price, price_step)] = level_type

            for price, level_type in support_resistance.resistances.items():
                if price > even_price:
                    rounded_resistance_prices[round_(price, price_step)] = level_type

            # only return supports below the position price
            final_support_levels[timeframe] = SupportResistance(supports=rounded_support_prices,
                                                                resistances=rounded_resistance_prices)

        return final_support_levels

    def should_refresh_cache(self, symbol: str, timeframe: Timeframe) -> bool:
        now = self.time_provider.get_utc_now_timestamp()
        latest_candle_close = self.repository.cache_valid_until(symbol=symbol, timeframe=timeframe)
        # a new close date is only going to be available when the next candle's close date has passed
        if now > latest_candle_close + timeframe.milliseconds:
            logger.info(f'Updating support cache for {symbol}, as {now} is past the cache expiration {latest_candle_close}')
            return True
        else:
            logger.debug(f'Not updating support cache for {symbol}, as {now} is not past cache expiration {latest_candle_close}')
            return False

    def _get_levels_for_timeframe(self, candles: List[Candle]) -> SupportResistance:
        levels = []
        support: Dict[float, LevelType] = {}
        resistance: Dict[float, LevelType] = {}

        last_price = candles[len(candles) - 1].close
        diffs = [c.hc_average - c.lc_average for c in candles]
        average = np.mean(diffs)

        for i in range(2, len(candles) - 2):
            if self.is_support(candles, i):
                level = candles[i].lc_average
                if self.is_far_from_level(level, levels, average):
                    levels.append((i, level))
                    if last_price > level:
                        support[level] = LevelType.TROUGH
                    else:
                        resistance[level] = LevelType.TROUGH

            elif self.is_resistance(candles, i):
                level = candles[i].hc_average
                if self.is_far_from_level(level, levels, average):
                    levels.append((i, level))
                    if last_price > level:
                        support[level] = LevelType.PEAK
                    else:
                        resistance[level] = LevelType.PEAK

        support = {k: v for k, v in sorted(support.items())}
        resistance = {k: v for k, v in sorted(resistance.items())}
        return SupportResistance(supports=support, resistances=resistance)

    def is_support(self, candles: List[Candle], i) -> bool:
        cond1 = candles[i].lc_average < candles[i - 1].lc_average
        cond2 = candles[i].lc_average < candles[i + 1].lc_average
        cond3 = candles[i + 1].lc_average < candles[i + 2].lc_average
        cond4 = candles[i - 1].lc_average < candles[i - 2].lc_average
        return cond1 and cond2 and cond3 and cond4

    def is_resistance(self, candles: List[Candle], i) -> bool:
        cond1 = candles[i].hc_average > candles[i - 1].hc_average
        cond2 = candles[i].hc_average > candles[i + 1].hc_average
        cond3 = candles[i + 1].hc_average > candles[i + 2].hc_average
        cond4 = candles[i - 1].hc_average > candles[i - 2].hc_average
        return cond1 and cond2 and cond3 and cond4

    def is_far_from_level(self, value, levels, average) -> bool:
        return np.sum([abs(value - level) < average for _, level in levels]) == 0