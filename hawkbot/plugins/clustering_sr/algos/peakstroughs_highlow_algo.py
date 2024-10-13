import logging
from typing import List, Dict, Set

import numpy as np

from hawkbot.core.data_classes import Candle
from hawkbot.core.model import PositionSide, SymbolInformation, Timeframe
from hawkbot.logging import user_log
from hawkbot.plugins.clustering_sr.algos.algo import Algo
from hawkbot.plugins.clustering_sr.data_classes import SupportResistance
from hawkbot.utils import readable

logger = logging.getLogger(__name__)


class PeaksTroughsHighLowAlgo(Algo):
    def __init__(self, algo_config: Dict = None):
        super().__init__(algo_config=algo_config)
        self.troughs_cache: Dict[str, Dict[Timeframe, Set[Candle]]] = {}
        self.peaks_cache: Dict[str, Dict[Timeframe, Set[Candle]]] = {}
        self.cache_last_close_date: Dict[str, Dict[Timeframe, int]] = {}
        self.cache_diff_average: Dict[str, Dict[Timeframe, float]] = {}
        self.outer_price_warning_logged: bool = False
        self.sort_prices: bool = True

    def get_candles_start_date(self, symbol: str, timeframe: Timeframe, start_date: int, outer_grid_price: float):
        if symbol in self.cache_last_close_date and timeframe in self.cache_last_close_date[symbol]:
            start_date = self.cache_last_close_date[symbol][timeframe] - 10 * timeframe.milliseconds
        logger.debug(f'{symbol}: Returning start_date {readable(start_date)}')
        return start_date

    def calculate_levels(self,
                         symbol: str,
                         position_side: PositionSide,
                         candles: List[Candle],
                         nr_clusters: int,
                         current_price: float,
                         outer_price: float,
                         original_start_date: int,
                         symbol_information: SymbolInformation) -> SupportResistance:
        if outer_price is not None and self.outer_price_warning_logged is False:
            self.outer_price_warning_logged = True
            user_log.warning(f'{symbol} {position_side.name}: The configuration uses an outer '
                             f'price, but this has no effect when combining this with the '
                             f'{self.__class__.__name__} algo. ', __name__)

        timeframe = candles[0].timeframe
        self.prepare_cache(symbol=symbol, timeframe=timeframe)

        levels = []
        levels.extend(candle.low for candle in self.troughs_cache[symbol][timeframe])
        levels.extend(candle.high for candle in self.peaks_cache[symbol][timeframe])

        if timeframe not in self.cache_diff_average[symbol]:
            diffs = [c.high - c.low for c in candles]
            self.cache_diff_average[symbol][timeframe] = np.mean(diffs)

        average = self.cache_diff_average[symbol][timeframe]

        for i in range(2, len(candles) - 2):
            candle = candles[i]
            if self.is_trough(candles, i) and candle not in self.peaks_cache[symbol][timeframe]:
                if self.is_far_from_level(candle.low, levels, average):
                    levels.append(candle.low)
                    self.troughs_cache[symbol][timeframe].add(candle)
            elif self.is_peak(candles, i) and candle.high not in self.peaks_cache[symbol][timeframe]:
                if self.is_far_from_level(candle.high, levels, average):
                    levels.append(candle.high)
                    self.peaks_cache[symbol][timeframe].add(candle)

        selected_supports = []
        selected_resistances = []
        # logger.info(f'{symbol} {position_side.name}: Currently cached peaks: {self.peaks_cache[symbol][timeframe]}')
        # logger.info(f'{symbol} {position_side.name}: Currently cached troughs: {self.troughs_cache[symbol][timeframe]}')
        if position_side == PositionSide.LONG:
            selected_supports.extend(
                [candle.low for candle in self.troughs_cache[symbol][timeframe] if candle.low < current_price])
            logger.info(f'{symbol} {position_side.name}: All supports are {selected_supports}')
            if self.sort_prices:
                selected_supports = sorted(selected_supports, reverse=True)
        else:
            selected_resistances.extend(
                [candle.high for candle in self.peaks_cache[symbol][timeframe] if candle.high > current_price])
            logger.info(f'{symbol} {position_side.name}: All resistances are {selected_resistances}')
            if self.sort_prices:
                selected_resistances = sorted(selected_resistances)

        logger.debug(f'{symbol} {position_side.name}: Purging expired peaks candles')
        self.peaks_cache[symbol][timeframe] = self.purged_candles(symbol=symbol,
                                                                  position_side=position_side,
                                                                  candles=self.peaks_cache[symbol][timeframe],
                                                                  purge_start_before=original_start_date)

        logger.debug(f'{symbol} {position_side.name}: Purging expired troughs candles')
        self.troughs_cache[symbol][timeframe] = self.purged_candles(symbol=symbol,
                                                                    position_side=position_side,
                                                                    candles=self.troughs_cache[symbol][timeframe],
                                                                    purge_start_before=original_start_date)

        self.cache_last_close_date[symbol][timeframe] = max([candle.close_date for candle in candles])

        return SupportResistance(supports=selected_supports, resistances=selected_resistances)

    def purged_candles(self,
                       symbol: str,
                       position_side: PositionSide,
                       candles: Set[Candle],
                       purge_start_before: int) -> Set[Candle]:
        updated_peaks = set()
        for candle in candles:
            if candle.start_date > purge_start_before:
                updated_peaks.add(candle)
            else:
                logger.info(f'{symbol} {position_side.name}: Purging candle {candle} because start_date '
                            f'{readable(candle.start_date)} is older than the period\'s start date '
                            f'{readable(purge_start_before)}')
        return updated_peaks

    def prepare_cache(self, symbol: str, timeframe: Timeframe):
        if symbol not in self.peaks_cache:
            self.peaks_cache[symbol] = {}
        if timeframe not in self.peaks_cache[symbol]:
            self.peaks_cache[symbol][timeframe] = set()

        if symbol not in self.troughs_cache:
            self.troughs_cache[symbol] = {}
        if timeframe not in self.troughs_cache[symbol]:
            self.troughs_cache[symbol][timeframe] = set()

        if symbol not in self.cache_last_close_date:
            self.cache_last_close_date[symbol] = {}

        if symbol not in self.cache_diff_average:
            self.cache_diff_average[symbol] = {}

    def is_trough(self, candles: List[Candle], i) -> bool:
        cond1 = candles[i].low < candles[i - 1].low
        cond2 = candles[i].low < candles[i + 1].low
        cond3 = candles[i + 1].low < candles[i + 2].low
        cond4 = candles[i - 1].low < candles[i - 2].low
        return cond1 and cond2 and cond3 and cond4

    def is_peak(self, candles: List[Candle], i) -> bool:
        cond1 = candles[i].high > candles[i - 1].high
        cond2 = candles[i].high > candles[i + 1].high
        cond3 = candles[i + 1].high > candles[i + 2].high
        cond4 = candles[i - 1].high > candles[i - 2].high
        return cond1 and cond2 and cond3 and cond4

    def is_far_from_level(self, value: float, levels: List[float], average) -> bool:
        distances = [abs(value - level) for level in levels]
        return not any([distance < average for distance in distances])
