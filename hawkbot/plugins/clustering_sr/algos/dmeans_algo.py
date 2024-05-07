import logging
from typing import List

import numpy as np
from scipy.signal import find_peaks
from sklearn.model_selection import GridSearchCV
from sklearn.neighbors import KernelDensity

from hawkbot.core.data_classes import Candle
from hawkbot.core.model import PositionSide, SymbolInformation
from hawkbot.plugins.clustering_sr.algos.algo import Algo
from hawkbot.plugins.clustering_sr.data_classes import SupportResistance
from hawkbot.utils import readable

logger = logging.getLogger(__name__)


class DMeansAlgo(Algo):
    def calculate_levels(
            self,
            symbol: str,
            position_side: PositionSide,
            candles: List[Candle],
            nr_clusters: int,
            current_price: float,
            outer_price: float,
            original_start_date: int,
            symbol_information: SymbolInformation) -> SupportResistance:
        if len(candles) < nr_clusters * 2:
            logger.warning(
                f"{symbol} {position_side.name}: The number of candles ({len(candles)}) passed to the "
                f"kmeans algorithm is less than the number of clusters * 2 ({nr_clusters} * 2 = "
                f"{nr_clusters * 2}). "
                f"The first candle start_date = {readable(min([candle.start_date for candle in candles]))}, "
                f"the last candle start_date = {readable(max([candle.start_date for candle in candles]))}, "
                f"the lowest close price = {min([candle.close for candle in candles])}, "
                f"the highest close price = {max([candle.close for candle in candles])}."
            )
            return SupportResistance()

        # ideally we want to pass the params to this instead of hardcoded
        min_bandwidth_log = -2
        max_bandwidth_log = 1
        n_bandwidths = 1000
        min_prominence = 0.01

        candles.sort(key=lambda x: x.close_date)

        opens = [float(candle.open) for candle in candles]
        closes = [float(candle.close) for candle in candles]
        # volumes = [float(candle.volume) for candle in candles] # we can add volumes in the mix, maybe later
        prices = np.vstack((opens, closes)).reshape(-1, 1)

        # Define values of bandwidths to try (hyperparameter space)
        bandwidths = 10 ** np.linspace(min_bandwidth_log, max_bandwidth_log, n_bandwidths)

        # Grid search
        grid = GridSearchCV(KernelDensity(), {"kernel": ["gaussian", "exponential"], "bandwidth": bandwidths})
        grid.fit(prices)
        best_estimator = grid.best_estimator_

        # Fit best estimator to data
        kde = best_estimator.fit(prices)

        # Construct pdf
        a, b = min(prices), max(prices)
        xx = np.linspace(a, b, 1000).reshape(-1, 1)
        pdf = np.exp(kde.score_samples(xx))

        # Find maxima
        # Get the supports and resistances
        peaks, _ = find_peaks(pdf, prominence=min_prominence)
        support_resistances = xx[peaks]  # price values
        strengths = pdf[
            peaks
        ]  # density (related to strength of resistance/support == more clustered candles in the area and inherently more volume)

        return SupportResistance(support_resistances.reshape(-1, ), strengths.reshape(-1, ))
