import logging
from typing import List, Dict, Set

from hawkbot.core.data_classes import Candle
from hawkbot.core.model import PositionSide, SymbolInformation, Timeframe
from hawkbot.exceptions import UnsupportedParameterException
from hawkbot.plugins.clustering_sr.algos.algo import Algo
from hawkbot.plugins.clustering_sr.algos.lin_algo import LinAlgo
from hawkbot.plugins.clustering_sr.algos.peakstroughs_highlow_algo import PeaksTroughsHighLowAlgo
from hawkbot.plugins.clustering_sr.data_classes import SupportResistance
from hawkbot.utils import round_

logger = logging.getLogger(__name__)


class LinPeaksTroughsHighLowAlgo(Algo):
    """
    Find the closest PT support/resistance from the LOG price within the configured threshold.
    If no PT support/resistance available, simply keep the LOG level
    """

    def __init__(self, algo_config: Dict = None):
        super().__init__(algo_config=algo_config)
        self.troughs_cache: Dict[str, Dict[Timeframe, Set[Candle]]] = {}
        self.peaks_cache: Dict[str, Dict[Timeframe, Set[Candle]]] = {}
        self.cache_last_close_date: Dict[str, Dict[Timeframe, int]] = {}
        self.cache_diff_average: Dict[str, Dict[Timeframe, float]] = {}
        self.lin_algo = LinAlgo()
        self.pt = PeaksTroughsHighLowAlgo()

    def get_candles_start_date(self, symbol: str, timeframe: Timeframe, start_date: int, outer_grid_price: float):
        return self.pt.get_candles_start_date(symbol, timeframe, start_date, outer_grid_price)

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
            raise UnsupportedParameterException(
                f'{symbol} {position_side.name}: The LogPeaksTroughsHighLowAlgo does not support '
                f'calculation without an outer price')

        # Get LOG supports+resistances
        log_support_resistances = self.lin_algo.calculate_levels(symbol,
                                                                 position_side,
                                                                 candles,
                                                                 nr_clusters,
                                                                 current_price,
                                                                 outer_price,
                                                                 original_start_date,
                                                                 symbol_information)

        # Get P/T supports+resistances
        pt_support_resistances = self.pt.calculate_levels(symbol=symbol,
                                                          position_side=position_side,
                                                          candles=candles,
                                                          nr_clusters=nr_clusters,
                                                          current_price=current_price,
                                                          outer_price=None,
                                                          original_start_date=original_start_date,
                                                          symbol_information=symbol_information)

        supports = []
        resistances = []
        threshold = 0.0025
        pt_support_resistances.supports = sorted(pt_support_resistances.supports)
        for s in log_support_resistances.supports:
            tmp = self.bisection(pt_support_resistances.supports, s)
            # Keep LOG value if value is outside threshold (%)
            if tmp >= 0 and tmp < len(pt_support_resistances.supports):
                logger.info(f'S> {round_(pt_support_resistances.supports[tmp], symbol_information.price_step)} - {s}')
                if abs(pt_support_resistances.supports[tmp] - s) / s < threshold \
                        and pt_support_resistances.supports[tmp] not in supports:
                    supports.append(pt_support_resistances.supports[tmp])
                else:
                    supports.append(s)
            else:
                supports.append(s)

        for r in log_support_resistances.resistances:
            tmp = self.bisection(pt_support_resistances.resistances, r)
            # Keep LOG value if value is outside threshold (%)
            if tmp >= 0 and tmp < len(pt_support_resistances.resistances):
                logger.info(f'R> {round_(pt_support_resistances.resistances[tmp], symbol_information.price_step)} - {r}')
                if abs(pt_support_resistances.resistances[tmp] - r) / r < threshold and \
                        pt_support_resistances.resistances[tmp] not in resistances:
                    resistances.append(pt_support_resistances.resistances[tmp])
                else:
                    resistances.append(r)
            else:
                resistances.append(r)

        return SupportResistance(supports=supports, resistances=resistances)

    def bisection(self, array, value):
        """Given an ``array`` , and given a ``value`` , returns an index j such that ``value`` is between array[j]
        and array[j+1]. ``array`` must be monotonic increasing. j=-1 or j=len(array) is returned
        to indicate that ``value`` is out of range below and above respectively."""
        n = len(array)
        try:
            if (value < array[0]):
                return -1
            elif (value > array[n - 1]):
                return n
        except:
            return -1

        jl = 0  # Initialize lower
        ju = n - 1  # and upper limits.
        while (ju - jl > 1):  # If we are not yet done,
            jm = (ju + jl) >> 1  # compute a midpoint with a bitshift
            if (value >= array[jm]):
                jl = jm  # and replace either the lower limit
            else:
                ju = jm  # or the upper limit, as appropriate.
            # Repeat until the test condition is satisfied.
        if (value == array[0]):  # edge cases at bottom
            return 0
        elif (value == array[n - 1]):  # and top
            return n - 1
        else:
            return jl
