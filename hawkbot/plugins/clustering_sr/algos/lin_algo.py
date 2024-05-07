import logging
from typing import List

import numpy as np

from hawkbot.core.data_classes import Candle
from hawkbot.core.model import PositionSide, SymbolInformation, Timeframe
from hawkbot.exceptions import UnsupportedParameterException
from hawkbot.plugins.clustering_sr.algos.algo import Algo
from hawkbot.plugins.clustering_sr.data_classes import SupportResistance

logger = logging.getLogger(__name__)


class LinAlgo(Algo):
    def get_candles_start_date(self, symbol: str, timeframe: Timeframe, start_date: int, outer_grid_price: float):
        return None

    def calculate_levels(self,
                         symbol: str,
                         position_side: PositionSide,
                         candles: List[Candle],
                         nr_clusters: int,
                         current_price: float,
                         outer_price: float,
                         original_start_date: int,
                         symbol_information: SymbolInformation) -> SupportResistance:
        if outer_price is None:
            raise UnsupportedParameterException(f'{symbol} {position_side.name}: The LinAlgo does not support '
                                                f'calculation without an outer price')

        supports = []
        resistances = []

        diff = abs(current_price - outer_price)
        factors = np.linspace(0.0, 1.0, num=nr_clusters + 1) ** 2
        for i, factor in enumerate(factors):
            if i == 0:
                continue
            if position_side == PositionSide.LONG:
                supports.append(current_price - (diff * factor))
            else:
                resistances.append(current_price + (diff * factor))

        return SupportResistance(supports, resistances)

    def powspace(self, start, stop, power, num):
        start = np.power(start, 1 / float(power))
        stop = np.power(stop, 1 / float(power))
        return np.power(np.linspace(start, stop, num=num), power)
