import logging
from typing import List, Dict

import numpy as np

from hawkbot.core.data_classes import Candle
from hawkbot.core.model import PositionSide, SymbolInformation
from hawkbot.logging import user_log
from hawkbot.plugins.clustering_sr.algos.algo import Algo
from hawkbot.plugins.clustering_sr.data_classes import SupportResistance

logger = logging.getLogger(__name__)


class PeaksTroughsAlgo(Algo):
    def __init__(self, algo_config: Dict = None):
        super().__init__(algo_config=algo_config)
        self.outer_price_warning_logged: bool = False

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

        levels = []
        support: List[float] = []
        resistance: List[float] = []

        last_price = candles[len(candles) - 1].close
        diffs = [c.hc_average - c.lc_average for c in candles]
        average = np.mean(diffs)

        for i in range(2, len(candles) - 2):
            if self.is_support(candles, i):
                level = candles[i].lc_average
                if self.is_far_from_level(level, levels, average):
                    levels.append((i, level))
                    if last_price > level:
                        support.append(level)
                    else:
                        resistance.append(level)

            elif self.is_resistance(candles, i):
                level = candles[i].hc_average
                if self.is_far_from_level(level, levels, average):
                    levels.append((i, level))
                    if last_price > level:
                        support.append(level)
                    else:
                        resistance.append(level)

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
