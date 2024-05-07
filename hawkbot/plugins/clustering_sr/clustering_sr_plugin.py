import logging
from typing import Dict

from hawkbot.core.candlestore.candlestore import Candlestore
from hawkbot.core.candlestore.candlestore_listener import CandlestoreListener
from hawkbot.core.data_classes import ExchangeState
from hawkbot.core.model import PositionSide, Timeframe
from hawkbot.core.time_provider import TimeProvider
from hawkbot.exceptions import NoLevelFoundException
from hawkbot.exchange.exchange import Exchange
from hawkbot.plugins.clustering_sr.algo_type import AlgoType
from hawkbot.plugins.clustering_sr.algos.algo import Algo
from hawkbot.plugins.clustering_sr.data_classes import SupportResistance
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.utils import round_, period_as_ms, readable

logger = logging.getLogger(__name__)


class ClusteringSupportResistancePlugin(Plugin, CandlestoreListener):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.candlestore: Candlestore = None  # Injected by framework
        self.time_provider: TimeProvider = None  # Overwritten by injection by framework
        self.exchange_state: ExchangeState = None  # Injected by framework
        self.exchange: Exchange = None  # Injected by plugin loader
        self.algos: Dict[str, Dict[PositionSide, Dict[AlgoType, Algo]]] = {}

    def get_support_resistance_levels(self,
                                      symbol: str,
                                      position_side: PositionSide,
                                      even_price: float,
                                      price_step: float,
                                      dca_config) -> SupportResistance:
        self.algos.setdefault(symbol, {}).setdefault(position_side, {})
        if dca_config.algo not in self.algos[symbol][position_side]:
            self.algos[symbol][position_side][dca_config.algo] = dca_config.algo.value[1]()
        if dca_config.outer_price_algo is not None:
            if dca_config.outer_price_algo not in self.algos[symbol][position_side]:
                self.algos[symbol][position_side][dca_config.outer_price_algo] = dca_config.outer_price_algo.value[1]()
            outer_price_algo = self.algos[symbol][position_side][dca_config.outer_price_algo]
        else:
            outer_price_algo = None
        if dca_config.first_level_algo is not None:
            if dca_config.first_level_algo not in self.algos[symbol][position_side]:
                self.algos[symbol][position_side][dca_config.first_level_algo] = dca_config.first_level_algo.value[1]()
            first_level_algo = self.algos[symbol][position_side][dca_config.first_level_algo]
        else:
            first_level_algo = None

        return self.get_support_resistance_levels_expanded(symbol=symbol,
                                                           position_side=position_side,
                                                           first_level_period=dca_config.first_level_period,
                                                           first_level_period_timeframe=dca_config.first_level_period_timeframe,
                                                           first_level_algo=first_level_algo,
                                                           first_level_nr_clusters=dca_config.first_level_nr_clusters,
                                                           period=dca_config.period,
                                                           nr_clusters=dca_config.nr_clusters,
                                                           period_timeframe=dca_config.period_timeframe,
                                                           period_start_date=dca_config.period_start_date,
                                                           algo=self.algos[symbol][position_side][dca_config.algo],
                                                           even_price=even_price,
                                                           price_step=price_step,
                                                           outer_price=dca_config.outer_price,
                                                           outer_price_distance=dca_config.outer_price_distance,
                                                           outer_price_timeframe=dca_config.outer_price_timeframe,
                                                           outer_price_period=dca_config.outer_price_period,
                                                           outer_price_period_start_date=dca_config.outer_price_period_start_date,
                                                           outer_price_level_nr=dca_config.outer_price_level_nr,
                                                           outer_price_nr_clusters=dca_config.outer_price_nr_clusters,
                                                           outer_price_algo=outer_price_algo,
                                                           minimum_distance_to_outer_price=dca_config.minimum_distance_to_outer_price,
                                                           maximum_distance_from_outer_price=dca_config.maximum_distance_from_outer_price)

    def get_support_resistance_levels_expanded(self,
                                               symbol: str,
                                               position_side: PositionSide,
                                               first_level_period: str,
                                               first_level_period_timeframe: Timeframe,
                                               first_level_algo: Algo,
                                               first_level_nr_clusters: int,
                                               period: str,
                                               period_start_date: int,
                                               algo: Algo,
                                               nr_clusters: int,
                                               period_timeframe: Timeframe,
                                               even_price: float,
                                               price_step: float,
                                               outer_price: float,
                                               outer_price_distance: float,
                                               outer_price_timeframe: Timeframe,
                                               outer_price_period: str,
                                               outer_price_period_start_date: int,
                                               outer_price_level_nr: int,
                                               outer_price_nr_clusters: int,
                                               outer_price_algo: Algo,
                                               minimum_distance_to_outer_price: float,
                                               maximum_distance_from_outer_price: float) -> SupportResistance:
        try:
            outer_grid_price = self.determine_outer_price(symbol=symbol,
                                                          position_side=position_side,
                                                          even_price=even_price,
                                                          outer_price=outer_price,
                                                          outer_price_distance=outer_price_distance,
                                                          outer_price_timeframe=outer_price_timeframe,
                                                          outer_price_period=outer_price_period,
                                                          outer_price_period_start_date=outer_price_period_start_date,
                                                          nr_clusters=outer_price_nr_clusters,
                                                          outer_price_level_nr=outer_price_level_nr,
                                                          outer_price_algo=outer_price_algo,
                                                          minimum_distance_to_outer_price=minimum_distance_to_outer_price,
                                                          maximum_distance_from_outer_price=maximum_distance_from_outer_price)
        except NoLevelFoundException:
            return SupportResistance()

        support_resistance = self.get_sr(symbol=symbol,
                                         position_side=position_side,
                                         period=period,
                                         period_start_date=period_start_date,
                                         nr_clusters=nr_clusters,
                                         outer_grid_price=outer_grid_price,
                                         period_timeframe=period_timeframe,
                                         current_price=even_price,
                                         algo=algo)

        if first_level_period is not None:
            first_level_sr = self.get_sr(symbol=symbol,
                                         position_side=position_side,
                                         period=first_level_period,
                                         period_start_date=None,
                                         nr_clusters=first_level_nr_clusters,
                                         outer_grid_price=outer_grid_price,
                                         period_timeframe=first_level_period_timeframe,
                                         current_price=even_price,
                                         algo=first_level_algo)
            first_level_sr.supports.sort(reverse=True)
            first_level_sr.resistances.sort()

            first_level_supports = first_level_sr.supports[0:first_level_nr_clusters]
            if len(first_level_supports) > 0:
                lowest_first_level_support = min(first_level_supports)
                lower_inner_supports = [s for s in support_resistance.supports if s < lowest_first_level_support]
                first_level_supports.extend(lower_inner_supports)
                support_resistance.supports = first_level_supports

            first_level_resistances = first_level_sr.resistances[0:first_level_nr_clusters]
            if len(first_level_resistances) > 0:
                highest_first_level_resistance = min(first_level_resistances)
                lower_inner_resistances = [r for r in support_resistance.resistances if r > highest_first_level_resistance]
                first_level_resistances.extend(lower_inner_resistances)
                support_resistance.resistances = first_level_resistances

        rounded_support_prices = [round_(price, price_step) for price in support_resistance.supports if price < even_price]
        rounded_resistance_prices = [round_(price, price_step) for price in support_resistance.resistances if price > even_price]

        # only return supports below the position price
        return SupportResistance(supports=rounded_support_prices,
                                 resistances=rounded_resistance_prices)

    def determine_outer_price(self,
                              symbol: str,
                              position_side: PositionSide,
                              even_price: float,
                              outer_price: float,
                              outer_price_distance: float,
                              outer_price_timeframe: Timeframe,
                              outer_price_period: str,
                              outer_price_period_start_date: int,
                              nr_clusters: int,
                              outer_price_level_nr: int,
                              outer_price_algo: Algo,
                              minimum_distance_to_outer_price: float,
                              maximum_distance_from_outer_price: float) -> float:
        if outer_price is not None or outer_price_distance is not None:
            if outer_price_distance is not None:
                if position_side == PositionSide.LONG:
                    outer_price = even_price * (1 - outer_price_distance)
                elif position_side == PositionSide.SHORT:
                    outer_price = even_price * (1 + outer_price_distance)
            if minimum_distance_to_outer_price is not None:
                if position_side == PositionSide.LONG:
                    if even_price < outer_price * (1 + minimum_distance_to_outer_price):
                        logger.warning(f"{symbol} {position_side.name}: The current price {even_price} is less than "
                                       f"{minimum_distance_to_outer_price} ('minimum_distance_to_outer_price') above "
                                       f"the specified outer price {outer_price}")
                        raise NoLevelFoundException()
                elif position_side == PositionSide.SHORT:
                    if even_price > outer_price * (1 - minimum_distance_to_outer_price):
                        logger.warning(f"{symbol} {position_side.name}: The current price {even_price} is less than "
                                       f"{minimum_distance_to_outer_price} ('minimum_distance_to_outer_price') below "
                                       f"the specified outer price {outer_price}")
                        raise NoLevelFoundException()

            if maximum_distance_from_outer_price is not None:
                if position_side == PositionSide.LONG:
                    if even_price > outer_price * (1 + maximum_distance_from_outer_price):
                        logger.warning(f"{symbol} {position_side.name}: The current price {even_price} is more than "
                                       f"{maximum_distance_from_outer_price} ('maximum_distance_from_outer_price') "
                                       f"above the specified outer price {outer_price}")
                        raise NoLevelFoundException()
                elif position_side == PositionSide.SHORT:
                    if even_price < outer_price * (1 - maximum_distance_from_outer_price):
                        logger.warning(f"{symbol} {position_side.name}: The current price {even_price} is more than "
                                       f"{maximum_distance_from_outer_price} ('maximum_distance_from_outer_price') "
                                       f"below the specified outer price {outer_price}")
                        raise NoLevelFoundException()

            logger.info(f'{symbol} {position_side.name}: Using explicitly set outer price of '
                        f'{outer_price}')
            return outer_price

        if outer_price_timeframe is not None:
            support_resistance = self.get_sr(symbol=symbol,
                                             position_side=position_side,
                                             period=outer_price_period,
                                             period_start_date=outer_price_period_start_date,
                                             nr_clusters=nr_clusters,
                                             outer_grid_price=None,
                                             period_timeframe=outer_price_timeframe,
                                             current_price=even_price,
                                             algo=outer_price_algo)
            if position_side == PositionSide.LONG:
                supports = [support for support in support_resistance.supports if support <= even_price]
                supports.sort(reverse=True)
                logger.info(f'{symbol} {position_side.name}: Supports returned by plugin for outer grid price '
                            f'selection: {supports} for timeframe {outer_price_timeframe.name}, '
                            f'period {outer_price_period} and even price {even_price}')
                supports = supports[outer_price_level_nr - 1:]
                if minimum_distance_to_outer_price is not None:
                    highest_support_allowed = even_price * (1 - minimum_distance_to_outer_price)
                    filtered_supports = [support for support in supports if support <= highest_support_allowed]
                else:
                    filtered_supports = supports

                if len(filtered_supports) == 0:
                    logger.info(f'{symbol} {position_side.name}: There are no '
                                f'{outer_price_timeframe.name} supports available beyond the minimum '
                                f'grid distance of {minimum_distance_to_outer_price} from price '
                                f'{even_price} in supports {supports}')
                    raise NoLevelFoundException()
                else:
                    outer_price = max(list(filtered_supports))
                    logger.info(f'{symbol} {position_side.name}: selecting support '
                                f'#{outer_price_level_nr} from supports that are at least '
                                f'{minimum_distance_to_outer_price} away from current price '
                                f'{even_price}, which are {filtered_supports}, which results in an outer price of '
                                f'{outer_price}')
                    return outer_price
            else:
                resistances = [resistance for resistance in support_resistance.resistances if resistance >= even_price]
                resistances.sort()
                logger.info(f'{symbol} {position_side.name}: Resistances returned by plugin for outer grid price '
                            f'selection: {resistances} for timeframe {outer_price_timeframe.name}, '
                            f'period {outer_price_period} and even price {even_price}')
                resistances = resistances[outer_price_level_nr - 1:]
                if minimum_distance_to_outer_price is not None:
                    lowest_resistance_allowed = even_price * (1 + minimum_distance_to_outer_price)
                    filtered_resistances = [resistance for resistance in resistances if resistance >= lowest_resistance_allowed]
                else:
                    filtered_resistances = resistances

                if len(filtered_resistances) == 0:
                    logger.info(f'{symbol} {position_side.name}: There are no '
                                f'{outer_price_timeframe.name} resistances available beyond the '
                                f'minimum grid distance of {minimum_distance_to_outer_price} from price '
                                f'{even_price} in resistances {resistances}')
                    raise NoLevelFoundException()
                else:
                    outer_price = min(list(filtered_resistances))
                    logger.info(f'{symbol} {position_side.name}: selecting resistance '
                                f'#{outer_price_level_nr} from resistances that are at least '
                                f'{minimum_distance_to_outer_price} away from current price '
                                f'{even_price} {resistances}, which are {filtered_resistances}, which results in an '
                                f'outer price of {outer_price}')
                    return outer_price
        else:
            return None

    def get_sr(self,
               symbol: str,
               position_side: PositionSide,
               period: str,
               period_start_date: int,
               nr_clusters: int,
               outer_grid_price: float,
               period_timeframe: Timeframe,
               current_price: float,
               algo: Algo) -> SupportResistance:
        if period_start_date is not None:
            original_start_date = period_start_date
            self.candlestore.add_symbol_start_date(symbol=symbol,
                                                   timeframe=period_timeframe,
                                                   start_date=original_start_date)
        elif period is not None:
            self.candlestore.add_symbol_timeframe_period(symbol=symbol, timeframe=period_timeframe, period=period)
            original_start_date = self.time_provider.get_utc_now_timestamp() - period_as_ms(period)
        else:
            original_start_date = None

        if position_side == PositionSide.LONG:
            upper_price = current_price if outer_grid_price is not None else None
            lower_price = outer_grid_price
            exchange_lower_price_limit = self.exchange.get_lower_price_limit(symbol=symbol)
            if exchange_lower_price_limit is not None:
                if lower_price is not None:
                    lower_price = max(lower_price, exchange_lower_price_limit)
                else:
                    lower_price = exchange_lower_price_limit
        else:
            lower_price = current_price if outer_grid_price is not None else None
            upper_price = outer_grid_price
            exchange_upper_price_limit = self.exchange.get_upper_price_limit(symbol=symbol)
            if exchange_upper_price_limit is not None:
                if upper_price is not None:
                    upper_price = min(upper_price, exchange_upper_price_limit)
                else:
                    upper_price = exchange_upper_price_limit

        start_date = algo.get_candles_start_date(symbol=symbol,
                                                 timeframe=period_timeframe,
                                                 start_date=original_start_date,
                                                 outer_grid_price=outer_grid_price)
        if start_date is None:
            candles = []

            logger.info(
                f"{symbol} {position_side.name}: Calculating the support and resistances based on {len(candles)} "
                f"candles and {nr_clusters} clusters on timeframe {period_timeframe} using algo "
                f"{algo.__class__.__name__}.")
        else:
            candles = self.candlestore.get_candles_close_price_between(symbol=symbol,
                                                                       timeframe=period_timeframe,
                                                                       start_date=start_date,
                                                                       lower_price=lower_price,
                                                                       upper_price=upper_price)
            if len(candles) == 0 and outer_grid_price is not None:
                logger.warning(f'{symbol} {position_side.name}: the required outer_price of {outer_grid_price} '
                               f'is not reached in the specified period of {period_timeframe}. This leads to a '
                               f'grid that does not meet the specified minimum distance. Not returning results '
                               f'to force denial of grid. Number of candles used: {len(candles)}')
                return SupportResistance()

            logger.info(f"{symbol} {position_side.name}: Calculating the support and resistances based on {len(candles)} "
                        f"candles and {nr_clusters} clusters on timeframe {period_timeframe}."
                        f"The first candle start_date = {readable(min([candle.start_date for candle in candles]))}, "
                        f"the last candle start_date = {readable(max([candle.start_date for candle in candles]))}, "
                        f"the lowest close price = {min([candle.close for candle in candles])}, "
                        f"the highest close price = {max([candle.close for candle in candles])}."
                        )

        start = self.time_provider.get_utc_now_timestamp()
        support_resistance = algo.calculate_levels(symbol=symbol,
                                                   position_side=position_side,
                                                   candles=candles,
                                                   nr_clusters=nr_clusters,
                                                   current_price=current_price,
                                                   outer_price=outer_grid_price,
                                                   original_start_date=original_start_date,
                                                   symbol_information=self.exchange_state.get_symbol_information(symbol))
        end = self.time_provider.get_utc_now_timestamp()
        logger.debug(f'{symbol} {position_side.name}: {algo.__class__.__name__} calculation took {end - start}ms')

        price_step = self.exchange_state.get_symbol_information(symbol).price_step
        support_resistance.supports = [round_(support, price_step) for support in support_resistance.supports]
        support_resistance.resistances = [round_(resistance, price_step) for resistance in
                                          support_resistance.resistances]

        if len(candles) > 0:
            logger.debug(f'{symbol} {period_timeframe.name}: '
                         f'Calculated supports for {period_timeframe.name} = {support_resistance.supports}, '
                         f'calculated resistances for {period_timeframe.name} = {support_resistance.resistances}, '
                         f'# used candles: {len(candles)}, '
                         f'lowest candle close price = {min([candle.close for candle in candles])}, '
                         f'highest candle close price {max([candle.close for candle in candles])}')

        support_resistance.supports.sort(reverse=True)
        support_resistance.resistances.sort()

        logger.info(f'{symbol} {position_side.name}: Supports/resistances calculated with current price '
                    f'{current_price}, outer price {outer_grid_price} are {support_resistance}')

        return support_resistance
