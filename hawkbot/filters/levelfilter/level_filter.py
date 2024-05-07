import concurrent
import logging
from concurrent.futures import wait
from typing import List, Dict

from hawkbot.core.data_classes import SymbolPositionSide, Timeframe, FilterResult
from hawkbot.core.model import PositionSide
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.core.filters.filter import Filter
from hawkbot.plugins.clustering_sr.clustering_sr_plugin import ClusteringSupportResistancePlugin
from hawkbot.plugins.clustering_sr.data_classes import SupportResistance
from hawkbot.utils import get_percentage_difference

logger = logging.getLogger(__name__)


class LevelFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def __init__(self, bot, name: str, filter_config, redis_host: str, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.time_provider = None  # injected by framework
        self.candle_store = None  # inject by framework
        self.exchange = None  # injected by framework
        self.exchange_state = None  # injected by framework
        self.plugin_loader = None  # injected by framework
        self.clustering_sr_plugin: ClusteringSupportResistancePlugin = None

        self.below_support_distance: float = None
        self.above_support_distance: float = None
        self.below_resistance_distance: float = None
        self.above_resistance_distance: float = None
        self.period: str = None
        self.nr_clusters: int = 10
        self.period_timeframe: Timeframe = None
        self.period_start_date: int = None
        self.even_price: float = None
        self.price_step: float = None
        self.outer_price: float = None
        self.outer_price_timeframe: Timeframe = None
        self.outer_price_period: str = None
        self.outer_price_period_start_date: int = None
        self.outer_price_level_nr: int = 1
        self.outer_price_nr_clusters: int = 10
        self.minimum_distance_to_outer_price: float = None
        self.maximum_distance_from_outer_price: float = None
        self.minimum_number_of_available_dcas: int = 3
        self.overlap: float = 0.001
        self.grid_span: float = 1.0

        self.init_config(self.filter_config)

    def init_config(self, filter_config):
        if 'below_support_distance' in filter_config:
            self.below_support_distance = filter_config['below_support_distance']

        if 'above_support_distance' in filter_config:
            self.above_support_distance = filter_config['above_support_distance']

        if 'below_resistance_distance' in filter_config:
            self.below_resistance_distance = filter_config['below_resistance_distance']

        if 'above_resistance_distance' in filter_config:
            self.above_resistance_distance = filter_config['above_resistance_distance']

        if self.above_support_distance is None and \
                self.below_support_distance is None and \
                self.above_resistance_distance is None and \
                self.below_resistance_distance is None:
            logger.warning(f"There is no level distance parameter provided for long; at least "
                           f"one of 'above_support_distance', 'below_support_distance' 'above_resistance_distance' or "
                           f"'below_resistance_distance' is to be used if the level filter is expected to select entry "
                           f"based on level proximity.")

        if 'period' not in filter_config and 'period_start_date' not in filter_config:
            raise InvalidConfigurationException("One of the parameters 'period' or 'period_start_date is mandatory")

        if 'period' in filter_config:
            self.period = filter_config['period']

        if 'period_timeframe' in filter_config:
            self.period_timeframe = Timeframe.parse(filter_config['period_timeframe'])
        else:
            raise InvalidConfigurationException("The parameter 'period_timeframe' is not set in the configuration")

        if 'period_start_date' in filter_config:
            self.period_start_date = filter_config['period_start_date']

        if 'outer_price' in filter_config:
            self.outer_price = filter_config['outer_price']

        if 'outer_price_period' in filter_config:
            self.outer_price_period = filter_config['outer_price_period']

        if 'outer_price_period_start_date' in filter_config:
            self.outer_price_period_start_date = filter_config['outer_price_period_start_date']

        if 'outer_price_timeframe' in filter_config:
            self.outer_price_timeframe = Timeframe.parse(filter_config['outer_price_timeframe'])

        if 'minimum_distance_to_outer_price' in filter_config:
            self.minimum_distance_to_outer_price = filter_config['minimum_distance_to_outer_price']

        if 'maximum_distance_from_outer_price' in filter_config:
            self.maximum_distance_from_outer_price = filter_config['maximum_distance_from_outer_price']

        if 'outer_price_level_nr' in filter_config:
            self.outer_price_level_nr = filter_config['outer_price_level_nr']

        if 'outer_price_nr_clusters' in filter_config:
            self.outer_price_nr_clusters = filter_config['outer_price_nr_clusters']

        if 'nr_clusters' in filter_config:
            self.nr_clusters = filter_config['nr_clusters']

        if 'minimum_number_of_available_dcas' in filter_config:
            self.minimum_number_of_available_dcas = filter_config['minimum_number_of_available_dcas']

        if 'grid_span' in filter_config:
            self.grid_span = filter_config['grid_span']

        if 'overlap' in filter_config:
            self.overlap = filter_config['overlap']

        if self.minimum_distance_to_outer_price is not None \
                and self.minimum_distance_to_outer_price <= 0:
            raise InvalidConfigurationException(f"LevelFilter: The parameter "
                                                f"'minimum_distance_to_outer_price' needs to be a positive value "
                                                f"(current value = '{self.minimum_distance_to_outer_price}')")

        if self.maximum_distance_from_outer_price is not None \
                and self.maximum_distance_from_outer_price <= 0:
            raise InvalidConfigurationException(f"LevelFilter: The parameter "
                                                f"'maximum_distance_from_outer_price' needs to be a positive value "
                                                f"(current value = '{self.maximum_distance_from_outer_price}')")

        if self.outer_price_timeframe is None and self.outer_price_period is not None:
            raise InvalidConfigurationException("LevelFilter: The parameter 'outer_price_timeframe' is "
                                                "required when the parameter 'outer_price_period' is set")

        if self.outer_price_timeframe is not None and self.outer_price_period is None:
            raise InvalidConfigurationException("LevelFilter: The parameter 'outer_price_period' is "
                                                "required when the parameter 'outer_price_timeframe' is set")

    def start(self):
        super().start()
        self.clustering_sr_plugin = self.plugin_loader.get_plugin(ClusteringSupportResistancePlugin.plugin_name())

    def filter_symbols(self,
                       starting_list: List[SymbolPositionSide],
                       first_filter: bool,
                       position_side: PositionSide,
                       previous_filter_results: List[FilterResult]) -> Dict[SymbolPositionSide, Dict]:
        filtered_symbols = {}
        current_prices = self.exchange.fetch_all_current_prices()

        self.preload_candles(position_side, starting_list)

        for symbol_positionside in starting_list:
            symbol = symbol_positionside.symbol
            logger.debug(f'Checking if volatile symbol {symbol} is close enough to the entry level')
            if self.bot.config.position_side_enabled(symbol=symbol, position_side=position_side):
                continue

            current_price = current_prices[symbol].price
            price_step = self.exchange_state.get_symbol_information(symbol).price_step
            support_resistance = self.clustering_sr_plugin \
                .get_support_resistance_levels_expanded(symbol=symbol,
                                                        position_side=position_side,
                                                        period=self.period,
                                                        nr_clusters=self.nr_clusters,
                                                        period_timeframe=self.period_timeframe,
                                                        period_start_date=self.period_start_date,
                                                        even_price=current_price,
                                                        price_step=price_step,
                                                        outer_price=self.outer_price,
                                                        outer_price_timeframe=self.outer_price_timeframe,
                                                        outer_price_period=self.outer_price_period,
                                                        outer_price_period_start_date=self.outer_price_period_start_date,
                                                        outer_price_level_nr=self.outer_price_level_nr,
                                                        outer_price_nr_clusters=self.outer_price_nr_clusters,
                                                        minimum_distance_to_outer_price=self.minimum_distance_to_outer_price,
                                                        maximum_distance_from_outer_price=self.maximum_distance_from_outer_price)

            accept_entry = self.is_price_close_to_level(symbol=symbol,
                                                        position_side=position_side,
                                                        current_price=current_prices[symbol].price,
                                                        support_resistance=support_resistance)
            if accept_entry:
                accept_entry &= self.minimum_nr_dcas_available(symbol=symbol,
                                                               position_side=position_side,
                                                               support_resistance=support_resistance)

            if accept_entry:
                filtered_symbols[symbol_positionside] = {}

        return filtered_symbols

    def minimum_nr_dcas_available(self,
                                  symbol: str,
                                  position_side: PositionSide,
                                  support_resistance: SupportResistance):
        if self.minimum_number_of_available_dcas is None:
            return True

        if position_side == PositionSide.LONG:
            nr_supports = len(support_resistance.supports)
            if nr_supports >= self.minimum_number_of_available_dcas:
                logger.info(f"{symbol} {position_side.name}: Accepting candidate because the number of available "
                            f"supports ({nr_supports}) is equal or more than the specified number of supports "
                            f"'minimum_number_of_available_dcas' ({self.minimum_number_of_available_dcas})")
                return True
            else:
                logger.info(f"{symbol} {position_side.name}: Not accepting candidate because the number of available "
                            f"supports ({nr_supports}) is less than the specified number of supports "
                            f"'minimum_number_of_available_dcas' ({self.minimum_number_of_available_dcas})")
        else:
            nr_resistances = len(support_resistance.resistances)
            if nr_resistances >= self.minimum_number_of_available_dcas:
                logger.info(f"{symbol} {position_side.name}: Accepting candidate because the number of available "
                            f"resistances ({nr_resistances}) is equal or more than the specified number of resistances "
                            f"'minimum_number_of_available_dcas' ({self.minimum_number_of_available_dcas})")
                return True
            else:
                logger.info(f"{symbol} {position_side.name}: Not accepting candidate because the number of available "
                            f"supports ({nr_resistances}) is less than the specified number of resistances "
                            f"'minimum_number_of_available_dcas' ({self.minimum_number_of_available_dcas})")

        return False

    def preload_candles(self, position_side, symbol_list):
        futures = []
        with concurrent.futures.ThreadPoolExecutor(thread_name_prefix='level_filter') as executor:
            for symbol_positionside in symbol_list:
                symbol = symbol_positionside.symbol
                if self.bot.config.position_side_enabled(symbol=symbol, position_side=position_side):
                    continue

                logger.debug(f'{symbol} {position_side.name}: Preloading candles in parallel for faster processing')
                futures.append(executor.submit(self.candle_store.update_candles,
                                               symbol=symbol,
                                               timeframes=[self.period_timeframe], ))
            (finished, not_finished_tasks) = wait(futures, 300)
            leftover_tasks = 0
            for not_finished_task in not_finished_tasks:
                succesfully_canceled = not_finished_task.cancel()
                if not succesfully_canceled:
                    leftover_tasks += 1
            if leftover_tasks > 0:
                logger.warning(f'There are {leftover_tasks} threads still running while waiting for futures when '
                               f'the timeout kicked in. If this happens more often, there is a chance for leftover '
                               f'hanging threads. If you see this message more than once in your logs, please report '
                               f'it!')

    def is_price_close_to_level(self,
                                symbol: str,
                                position_side: PositionSide,
                                current_price: float,
                                support_resistance: SupportResistance) -> bool:
        if self.above_support_distance is not None \
                or self.below_support_distance is not None \
                or self.above_resistance_distance is not None \
                or self.below_resistance_distance is not None:
            if self.is_price_close_to_support_level(symbol=symbol,
                                                    position_side=position_side,
                                                    current_price=current_price,
                                                    support_resistance=support_resistance):
                return True

            if self.is_price_close_to_resistance_level(symbol=symbol,
                                                       position_side=position_side,
                                                       current_price=current_price,
                                                       support_resistance=support_resistance):
                return True
            return False
        return True

    def is_price_close_to_support_level(self,
                                        symbol: str,
                                        position_side: PositionSide,
                                        current_price: float,
                                        support_resistance: SupportResistance) -> bool:
        if self.below_support_distance is None and self.above_support_distance is None:
            return False
        if len(support_resistance.supports) == 0:
            logger.info(f'{symbol} {position_side}: Not adding to candidate list because there are no support '
                        f'levels found.')
            return False
        else:
            supports = [support for support in support_resistance.supports]
            # below support
            if self.below_support_distance is not None:
                close_supports = [support for support in supports
                                  if support > current_price
                                  and support <= current_price * (1 + self.below_support_distance)]
                if len(close_supports) > 0:
                    logger.info(f'{symbol} {position_side.name}: Adding to candidate list because current price '
                                f'{current_price} is within '
                                f'{self.below_support_distance * 100}% BELOW the '
                                f'{self.period_timeframe.name} support price of '
                                f'{min(close_supports)}')
                    return True
                else:
                    higher_supports = [support for support in supports if support > current_price]
                    if len(higher_supports) == 0:
                        logger.info(f'{symbol} {position_side.name}: Not adding  because there is no support found '
                                    f'above the current price {current_price}')
                    else:
                        next_higher_support = min(higher_supports)
                        difference = get_percentage_difference(next_higher_support, current_price)
                        logger.info(f'{symbol} {position_side.name}: Not adding because the current price '
                                    f'{current_price} is {difference} away from the higher '
                                    f'{self.period_timeframe.name} support at {next_higher_support}, which does '
                                    f'not match the configured setting of {self.below_support_distance} '
                                    f'({next_higher_support} + (({next_higher_support} * {self.below_support_distance}) / 100) = '
                                    f'{next_higher_support + ((next_higher_support * self.below_support_distance) / 100)})')

            # above support
            if self.above_support_distance is not None:
                close_supports = [support for support in supports
                                  if support < current_price
                                  and support >= current_price * (1 - self.above_support_distance)]
                if len(close_supports) > 0:
                    logger.info(f'{symbol} {position_side.name}: Adding to candidate list because current price '
                                f'{current_price} is within '
                                f'{self.above_support_distance} ABOVE '
                                f'the {self.period_timeframe.name} support price of '
                                f'{max(close_supports)}')
                    return True
                else:
                    lower_supports = [support for support in supports if support < current_price]
                    if len(lower_supports) == 0:
                        logger.info(f'{symbol} {position_side.name}: Not adding because there is no support found '
                                    f'below the current price {current_price}')
                    else:
                        next_lower_support = max(lower_supports)
                        difference = get_percentage_difference(next_lower_support, current_price)
                        logger.info(f'{symbol} {position_side.name}: Not adding because the current price '
                                    f'{current_price} is {difference} away from the lower '
                                    f'{self.period_timeframe.name} support at {next_lower_support}, which does '
                                    f'not match the configured setting of {self.above_support_distance} '
                                    f'({next_lower_support} + (({next_lower_support} * {self.above_support_distance}) / 100) = '
                                    f'{next_lower_support + ((next_lower_support * self.above_support_distance) / 100)})')

    def is_price_close_to_resistance_level(self,
                                           symbol: str,
                                           position_side: PositionSide,
                                           current_price: float,
                                           support_resistance: SupportResistance) -> bool:
        if self.below_resistance_distance is None and self.above_resistance_distance is None:
            return False
        if len(support_resistance.resistances) == 0:
            logger.info(f'{symbol} {position_side}: Not adding to candidate list because there are no resistance '
                        f'levels found.')
            return False
        else:
            resistances = [resistance for resistance in support_resistance.resistances]
            # below resistance
            if self.below_resistance_distance is not None:
                close_resistances = [resistance for resistance in resistances
                                     if resistance > current_price
                                     and resistance <= current_price * (1 + self.below_resistance_distance)]
                if len(close_resistances) > 0:
                    logger.info(f'{symbol} {position_side.name}: Adding to candidate list because current price '
                                f'{current_price} is within '
                                f'{self.below_resistance_distance} BELOW '
                                f'the {self.period_timeframe.name} resistance price of '
                                f'{min(close_resistances)}')
                    return True
                else:
                    higher_resistances = [resistance for resistance in resistances if resistance > current_price]
                    if len(higher_resistances) == 0:
                        logger.info(f'{symbol} {position_side.name}: Not adding because there is no resistance found '
                                    f'above the current price {current_price}')
                    else:
                        next_higher_resistance = min(higher_resistances)
                        difference = get_percentage_difference(next_higher_resistance, current_price)
                        logger.info(f'{symbol} {position_side.name}: Not adding because the current price '
                                    f'{current_price} is {difference}% away from the higher '
                                    f'{self.period_timeframe.name} resistance at {next_higher_resistance}, which '
                                    f'does not match the configured setting of '
                                    f'{self.below_resistance_distance} '
                                    f'({next_higher_resistance} + (({next_higher_resistance} * {self.below_resistance_distance}) / 100) = '
                                    f'{next_higher_resistance + ((next_higher_resistance * self.below_resistance_distance) / 100)})')

            # above resistance
            if self.above_resistance_distance is not None:
                close_resistances = [resistance for resistance in resistances
                                     if resistance < current_price
                                     and resistance >= current_price * (1 - self.above_resistance_distance)]
                if len(close_resistances) > 0:
                    logger.info(f'{symbol} {position_side.name}: Adding to candidate list because current price '
                                f'{current_price} is within '
                                f'{self.above_resistance_distance} ABOVE '
                                f'the {self.period_timeframe.name} resistance price of '
                                f'{max(close_resistances)}')
                    return True
                else:
                    lower_resistances = [resistance for resistance in resistances if resistance < current_price]
                    if len(lower_resistances) == 0:
                        logger.info(f'{symbol} {position_side.name}: Not adding because there is no resistance found '
                                    f'below the current price {current_price}')
                    else:
                        next_lower_resistance = max(lower_resistances)
                        difference = get_percentage_difference(next_lower_resistance, current_price)
                        logger.info(f'{symbol} {position_side.name}: Not adding because the current price '
                                    f'{current_price} is {difference} away from the lower '
                                    f'{self.period_timeframe.name} resistance at {next_lower_resistance}, which '
                                    f'does not match the configured setting of '
                                    f'{self.above_resistance_distance} '
                                    f'({next_lower_resistance} + (({next_lower_resistance} * {self.above_resistance_distance}) / 100) = '
                                    f'{next_lower_resistance + ((next_lower_resistance * self.above_resistance_distance) / 100)})')
