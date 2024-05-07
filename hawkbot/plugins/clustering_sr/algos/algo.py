import logging
from typing import List

from hawkbot.core.data_classes import Candle
from hawkbot.core.model import PositionSide, SymbolInformation, Timeframe
from hawkbot.exceptions import FunctionNotImplementedException
from hawkbot.plugins.clustering_sr.data_classes import SupportResistance

logger = logging.getLogger(__name__)


class Algo:
    def __init__(self):
        pass

    def calculate_levels(self,
                         symbol: str,
                         position_side: PositionSide,
                         candles: List[Candle],
                         nr_clusters: int,
                         current_price: float,
                         outer_price: float,
                         original_start_date: int,
                         symbol_information: SymbolInformation) -> SupportResistance:
        raise FunctionNotImplementedException('Algo not implemented')

    def get_candles_start_date(self, symbol: str, timeframe: Timeframe, start_date: int, outer_grid_price: float) -> int:
        return start_date
