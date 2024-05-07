import logging
from typing import List

import numpy as np
from kneed import KneeLocator
from sklearn.cluster import KMeans

from hawkbot.core.data_classes import Candle
from hawkbot.core.model import PositionSide, SymbolInformation
from hawkbot.plugins.clustering_sr.algos.algo import Algo
from hawkbot.plugins.clustering_sr.data_classes import SupportResistance
from hawkbot.utils import readable

logger = logging.getLogger(__name__)


class KMeansAlgo(Algo):
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
            logger.warning(f"{symbol} {position_side.name}: The number of candles ({len(candles)}) passed to the "
                           f"kmeans algorithm is less than the number of clusters * 2 ({nr_clusters} * 2 = "
                           f"{nr_clusters * 2}). "
                           f"The first candle start_date = {readable(min([candle.start_date for candle in candles]))}, "
                           f"the last candle start_date = {readable(max([candle.start_date for candle in candles]))}, "
                           f"the lowest close price = {min([candle.close for candle in candles])}, "
                           f"the highest close price = {max([candle.close for candle in candles])}.")
            return SupportResistance()

        candles.sort(key=lambda x: x.close_date)

        supports = []
        resistances = []

        try:
            sum_of_sq_distances = []
            X = np.array([candle.close for candle in candles])
            K = range(1, nr_clusters + 1)
            for k in K:
                km = KMeans(n_clusters=k)
                km = km.fit(X.reshape(-1, 1))
                sum_of_sq_distances.append(km.inertia_)
            kn = KneeLocator(K, sum_of_sq_distances, S=1.0, curve="concave", direction="decreasing")
            kmeans = KMeans(n_clusters=kn.knee).fit(X.reshape(-1, 1))
            c = kmeans.predict(X.reshape(-1, 1))
            min_and_max = []
            for i in range(kn.knee):
                min_and_max.append([-np.inf, np.inf])
            for i in range(len(X)):
                cluster = c[i]
                if X[i] > min_and_max[cluster][0]:
                    min_and_max[cluster][0] = X[i]
                if X[i] < min_and_max[cluster][1]:
                    min_and_max[cluster][1] = X[i]

            for resistance, support in min_and_max:
                supports.append(support)
                resistances.append(resistance)
        except:
            logger.exception(
                f"{symbol} {position_side.name}: An unexpected error occurred while processing the "
                f"support/resistance algorithm. "
                f"The number of candles pass to the kmeans algorithm is {len(candles)}. "
                f"The first candle start_date = {min([candle.start_date for candle in candles])}, "
                f"the last candle start_date = {max([candle.start_date for candle in candles])}, "
                f"the lowest close price = {min([candle.close for candle in candles])}, "
                f"the highest close price = {max([candle.close for candle in candles])}.")

        return SupportResistance(supports, resistances)
