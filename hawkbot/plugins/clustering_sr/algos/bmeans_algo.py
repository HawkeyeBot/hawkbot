import logging
from typing import List
import ckwrap


import numpy as np

from hawkbot.core.data_classes import Candle
from hawkbot.core.model import PositionSide, SymbolInformation
from hawkbot.plugins.clustering_sr.algos.algo import Algo
from hawkbot.plugins.clustering_sr.data_classes import SupportResistance

logger = logging.getLogger(__name__)


class BMeansAlgo(Algo):
    def calculate_levels(self,
                         symbol: str,
                         position_side: PositionSide,
                         candles: List[Candle],
                         nr_clusters: int,
                         current_price: float,
                         outer_price: float,
                         original_start_date: int,
                         symbol_information: SymbolInformation) -> SupportResistance:

        X = np.array([float(candle.close) for candle in candles])
        Y = np.array([float(candle.volume) for candle in candles])

        kmeans = ckwrap.ckmeans(X,nr_clusters,Y)

        min_and_max = []
        for i in range(nr_clusters):
            min_and_max.append([-np.inf, np.inf])
        for i in range(len(X)):
            cluster = kmeans.labels[i]
            if X[i] > min_and_max[cluster][0]:
                min_and_max[cluster][0] = X[i]
            if X[i] < min_and_max[cluster][1]:
                min_and_max[cluster][1] = X[i]

        supports = []
        resistances = []
        for resistance, support in min_and_max:
            supports.append(support)
            resistances.append(resistance)

        return SupportResistance(supports=supports, resistances=resistances)
