import logging
from typing import List

from hawkbot.core.data_classes import Candle
from hawkbot.core.model import PositionSide, SymbolInformation
from hawkbot.plugins.clustering_sr.algos.algo import Algo
from hawkbot.plugins.clustering_sr.data_classes import SupportResistance

logger = logging.getLogger(__name__)


class CustomAlgo(Algo):

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

        if position_side == PositionSide.LONG:
            supports.extend([current_price * price_distance for price_distance in self.algo_config['price_distances']])
        elif position_side == PositionSide.SHORT:
            resistances.extend([current_price * price_distance for price_distance in self.algo_config['price_distances']])

        return SupportResistance(supports, resistances)
