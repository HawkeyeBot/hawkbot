import logging
from typing import List

from hawkbot.core.data_classes import Candle
from hawkbot.core.model import PositionSide, SymbolInformation, Timeframe
from hawkbot.plugins.clustering_sr.algos.algo import Algo
from hawkbot.plugins.clustering_sr.data_classes import SupportResistance
from hawkbot.utils import readable

logger = logging.getLogger(__name__)


class ImmediateLinearAlgo(Algo):
    def get_candles_start_date(self, symbol: str, timeframe: Timeframe, start_date: int, outer_grid_price: float):
        return start_date if outer_grid_price is None else None  # this will make it not download candles

    def calculate_levels(self,
                         symbol: str,
                         position_side: PositionSide,
                         candles: List[Candle],
                         nr_clusters: int,
                         current_price: float,
                         outer_price: float,
                         original_start_date: int,
                         symbol_information: SymbolInformation) -> SupportResistance:
        supports = []
        resistances = []

        distance_per_level = abs(outer_price - current_price) / nr_clusters
        for i in range(0, nr_clusters):
            if position_side == PositionSide.LONG:
                price = current_price - (i * distance_per_level)
                price -= 3 * symbol_information.price_step
                supports.append(price)
            else:
                price = current_price + (i * distance_per_level)
                price += 3 * symbol_information.price_step
                resistances.append(price)

        return SupportResistance(supports, resistances)
