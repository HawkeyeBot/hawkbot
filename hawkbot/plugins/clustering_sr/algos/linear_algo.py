import logging
from typing import List

from hawkbot.core.data_classes import Candle
from hawkbot.core.model import PositionSide, SymbolInformation, Timeframe
from hawkbot.plugins.clustering_sr.algos.algo import Algo
from hawkbot.plugins.clustering_sr.data_classes import SupportResistance
from hawkbot.utils import readable

logger = logging.getLogger(__name__)


class LinearAlgo(Algo):
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
        if len(candles) < nr_clusters * 2:
            logger.debug(f"{symbol} {position_side.name}: The number of candles ({len(candles)}) passed to the "
                         f"kmeans algorithm is less than the number of clusters * 2 ({nr_clusters} * 2 = "
                         f"{nr_clusters * 2}). ")
            if len(candles) > 0:
                logger.warning(
                    f"The first candle start_date = {readable(min([candle.start_date for candle in candles]))}, "
                    f"the last candle start_date = {readable(max([candle.start_date for candle in candles]))}, "
                    f"the lowest close price = {min([candle.close for candle in candles])}, "
                    f"the highest close price = {max([candle.close for candle in candles])}.")

        supports = []
        resistances = []

        if outer_price is None:
            candles.sort(key=lambda x: x.close_date)
            if position_side == PositionSide.LONG:
                outer_price = min([candle.close for candle in candles])
            else:
                outer_price = max([candle.close for candle in candles])

        distance_per_level = abs(outer_price - current_price) / nr_clusters
        for i in range(1, nr_clusters + 1):
            if position_side == PositionSide.LONG:
                supports.append(current_price - (i * distance_per_level))
            else:
                resistances.append(current_price + (i * distance_per_level))

        return SupportResistance(supports, resistances)
