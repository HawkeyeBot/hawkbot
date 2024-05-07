import logging
import threading
from dataclasses import field, dataclass
from typing import Dict, List

from hawkbot.core.data_classes import ExchangeState
from hawkbot.core.model import PositionSide, Order, Position, LimitOrder, OrderTypeIdentifier, SymbolInformation, Side, \
    Mode, Timeframe
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.plugins.clustering_sr.algo_type import AlgoType
from hawkbot.plugins.clustering_sr.algos.algo import Algo
from hawkbot.plugins.clustering_sr.clustering_sr_plugin import ClusteringSupportResistancePlugin
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.utils import round_, calc_min_qty, round_up, round_dn, calc_diff

logger = logging.getLogger(__name__)


@dataclass
class WiggleConfig:
    enabled: bool = field(default_factory=lambda: True)
    activate_on_stuck: bool = field(default_factory=lambda: False)
    decrease_size: float = field(default_factory=lambda: None)
    decrease_coin_size: float = field(default_factory=lambda: None)
    increase_size: float = field(default_factory=lambda: None)
    increase_coin_size: float = field(default_factory=lambda: None)
    force_exit_position_price_distance: float = field(default_factory=lambda: None)
    force_exit_position_quantity_below: float = field(default_factory=lambda: None)
    force_exit_position_wallet_exposure_distance_below: float = field(default_factory=lambda: None)
    mode_after_closing: Mode = field(default_factory=lambda: None)
    tp_on_profit: bool = field(default_factory=lambda: True)  # Used by strategies
    period: str = field(default_factory=lambda: None)
    timeframe: Timeframe = field(default_factory=lambda: None)
    algo: AlgoType = field(default_factory=lambda: AlgoType.PEAKS_TROUGHS_HIGHLOW)
    algo_instance_cache: Algo = field(default_factory=lambda: None)
    wiggle_execution_delay_ms: int = field(default_factory=lambda: 2500)

    @property
    def algo_instance(self):
        if self.algo_instance_cache is None:
            self.algo_instance_cache = self.algo.value[1]()
        return self.algo_instance_cache


class WigglePlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange_state: ExchangeState = None  # Injected by plugin loader
        self.sr_plugin: ClusteringSupportResistancePlugin = None
        self.last_execution_timestamp: int = 0
        self.execution_lock: threading.Lock = threading.Lock()

    def start(self):
        self.started = True
        self.sr_plugin = self.plugin_loader.get_plugin(ClusteringSupportResistancePlugin.plugin_name())

    def parse_config(self, wiggle_dict: Dict) -> WiggleConfig:
        wiggle_config = WiggleConfig()
        if len(wiggle_dict.keys()) == 0:
            wiggle_config.enabled = False
            return wiggle_config
        if 'enabled' in wiggle_dict:
            wiggle_config.enabled = wiggle_dict['enabled']
        if 'activate_on_stuck' in wiggle_dict:
            wiggle_config.activate_on_stuck = wiggle_dict['activate_on_stuck']

        if 'decrease_size' in wiggle_dict:
            wiggle_config.decrease_size = wiggle_dict["decrease_size"]
        if 'decrease_coin_size' in wiggle_dict:
            wiggle_config.decrease_coin_size = wiggle_dict["decrease_coin_size"]

        if 'increase_size' in wiggle_dict:
            wiggle_config.increase_size = wiggle_dict["increase_size"]
        if 'increase_coin_size' in wiggle_dict:
            wiggle_config.increase_coin_size = wiggle_dict["increase_coin_size"]

        if 'force_exit_position_price_distance' in wiggle_dict:
            wiggle_config.force_exit_position_price_distance = wiggle_dict["force_exit_position_price_distance"]
        if 'force_exit_position_quantity_below' in wiggle_dict:
            wiggle_config.force_exit_position_quantity_below = wiggle_dict["force_exit_position_quantity_below"]
        if 'force_exit_position_wallet_exposure_distance_below' in wiggle_dict:
            wiggle_config.force_exit_position_wallet_exposure_distance_below = wiggle_dict[
                "force_exit_position_wallet_exposure_distance_below"]
        if 'mode_after_closing' in wiggle_dict:
            wiggle_config.mode_after_closing = Mode[wiggle_dict['mode_after_closing']]

        if 'period' in wiggle_dict:
            wiggle_config.period = wiggle_dict['period']
        else:
            raise InvalidConfigurationException("The parameter 'period' is not set in the configuration")

        if 'timeframe' in wiggle_dict:
            wiggle_config.timeframe = Timeframe.parse(wiggle_dict['timeframe'])
        else:
            raise InvalidConfigurationException("The parameter 'timeframe' is not set in the configuration")

        if 'algo' in wiggle_dict:
            wiggle_config.algo = AlgoType[wiggle_dict['algo']]

        if wiggle_config.decrease_size is not None and wiggle_config.decrease_coin_size is not None:
            raise InvalidConfigurationException('Both the parameters \'decrease_size\' and \'decrease_coin_size\' are '
                                                'set, but only one of the two is supported')

        if wiggle_config.decrease_size is None and wiggle_config.decrease_coin_size is None:
            logger.warning('Both the parameters \'decrease_size\' and \'decrease_coin_size\', are not set, but at '
                           'least one is required. If you were trying to disable the wiggle plugin, use the '
                           '\'enabled\' parameter')

        return wiggle_config

    def calculate_wiggle_orders(self,
                                symbol: str,
                                position_side: PositionSide,
                                position: Position,
                                symbol_information: SymbolInformation,
                                wiggle_config: WiggleConfig,
                                current_price: float,
                                wallet_exposure: float) -> List[Order]:
        if wiggle_config.enabled is False:
            return []
        if position.no_position():
            return []
        with self.execution_lock:
            now = self.bot.time_provider.get_utc_now_timestamp()
            if now < self.last_execution_timestamp + wiggle_config.wiggle_execution_delay_ms:
                logger.info(f'{symbol} {position_side.name}: Skipping wiggle calculation because last execution time '
                            f'{self.last_execution_timestamp} + wiggle_execution_delay_ms '
                            f'{wiggle_config.wiggle_execution_delay_ms} is not beyond current time {now}')
                return self.exchange_state.open_wiggle_orders(symbol=symbol, position_side=position_side)

            logger.debug(f'Calculate wiggle at {self.bot.time_provider.get_utc_now_timestamp()}')
            logger.info(f'{symbol} {position_side.name}: Calculating wiggle orders')

            force_sell_at_current_price = self.force_sell_at_price(symbol=symbol,
                                                                   position_side=position_side,
                                                                   position=position,
                                                                   current_price=current_price,
                                                                   wiggle_config=wiggle_config,
                                                                   wallet_exposure=wallet_exposure)

            orders = []
            if force_sell_at_current_price:
                close_order = self.calculate_force_exit_order(position=position,
                                                              current_price=current_price,
                                                              symbol_information=symbol_information)
                logger.info(f'{symbol} {position_side.name}: Creating force close order {close_order}')
                if close_order is not None:
                    orders.append(close_order)
            else:
                logger.info(f'{symbol} {position_side.name}: Updating wiggle increase & decrease orders')
                decrease_order = self.calculate_decrease_order(symbol=symbol,
                                                               position_side=position_side,
                                                               symbol_information=symbol_information,
                                                               current_price=current_price,
                                                               position=position,
                                                               wiggle_config=wiggle_config)
                if decrease_order is not None:
                    orders.append(decrease_order)

                increase_order = self.calculate_increase_order(symbol=symbol,
                                                               position_side=position_side,
                                                               symbol_information=symbol_information,
                                                               current_price=current_price,
                                                               position=position,
                                                               wiggle_config=wiggle_config)
                if increase_order is not None:
                    orders.append(increase_order)

            self.last_execution_timestamp = self.bot.time_provider.get_utc_now_timestamp()

        return orders

    def force_sell_at_price(self,
                            symbol: str,
                            position_side: PositionSide,
                            position: Position,
                            current_price: float,
                            wiggle_config: WiggleConfig,
                            wallet_exposure: float) -> bool:
        if wiggle_config.force_exit_position_quantity_below is not None:
            if position.position_size < wiggle_config.force_exit_position_quantity_below:
                logger.info(f'{symbol} {position_side.name}: Force exiting position because position size '
                            f'{position.position_size} is below configured exit quantity '
                            f'{wiggle_config.force_exit_position_quantity_below}')
                return True
        if wiggle_config.force_exit_position_price_distance is not None:
            price_distance = calc_diff(position.entry_price, current_price)
            if price_distance < wiggle_config.force_exit_position_price_distance:
                logger.info(
                    f'{symbol} {position_side.name}: Force exiting position because current price {current_price} '
                    f'is {price_distance} away from position price {position.entry_price}, which is less than '
                    f'configured {wiggle_config.force_exit_position_price_distance}')
                return True

        if wiggle_config.force_exit_position_wallet_exposure_distance_below is not None:
            cost_at_current_price = current_price * position.position_size
            max_cost = self.exchange_state.symbol_balance(symbol) * wallet_exposure
            if calc_diff(cost_at_current_price,
                         max_cost) < wiggle_config.force_exit_position_wallet_exposure_distance_below:
                logger.info(f'{symbol} {position_side.name}: Force exiting position because cost at current price '
                            f'{cost_at_current_price} is less than {wiggle_config.force_exit_position_wallet_exposure_distance_below} of '
                            f'maximum cost {max_cost} based on wallet exposure {wallet_exposure}')
                return True
        return False

    def calculate_force_exit_order(self,
                                   position: Position,
                                   current_price: float,
                                   symbol_information: SymbolInformation) -> Order:
        position_side = position.position_side
        if position_side == PositionSide.LONG:
            decrease_price = round_dn(current_price, symbol_information.price_step)
        else:
            decrease_price = round_up(current_price, symbol_information.price_step)

        return LimitOrder(order_type_identifier=OrderTypeIdentifier.WIGGLE_DECREASE,
                          symbol=symbol_information.symbol,
                          quantity=position.position_size,
                          side=Side.SELL if position_side == PositionSide.LONG else Side.BUY,
                          position_side=position_side,
                          initial_entry=False,
                          price=decrease_price,
                          reduce_only=True)

    def calculate_decrease_order(self,
                                 symbol: str,
                                 position_side: PositionSide,
                                 symbol_information: SymbolInformation,
                                 current_price: float,
                                 position: Position,
                                 wiggle_config: WiggleConfig) -> Order:
        if wiggle_config.enabled is False:
            return None
        if wiggle_config.decrease_size is None and wiggle_config.decrease_coin_size is None:
            return None

        # calculate reverse levels since we're wiggling in reverse
        decrease_position_side = PositionSide.SHORT if position_side == PositionSide.LONG else PositionSide.LONG
        sr_levels = self.sr_plugin.get_sr(symbol=symbol,
                                          position_side=decrease_position_side,
                                          period=wiggle_config.period,
                                          period_start_date=None,
                                          nr_clusters=10,
                                          outer_grid_price=None,
                                          period_timeframe=wiggle_config.timeframe,
                                          current_price=current_price,
                                          algo=wiggle_config.algo_instance)

        last_filled_decrease_price = self.exchange_state.last_filled_decrease_price(symbol=symbol,
                                                                                    position_side=position_side)
        last_filled_increase_price = self.exchange_state.last_filled_increase_price(symbol=symbol,
                                                                                    position_side=position_side)
        last_filled_wiggle_order = self.exchange_state.last_filled_order(symbol=symbol,
                                                                         position_side=position_side,
                                                                         order_type_identifiers=[
                                                                             OrderTypeIdentifier.WIGGLE_DECREASE,
                                                                             OrderTypeIdentifier.WIGGLE_INCREASE])
        last_filled_dca_price = self.exchange_state.last_filled_dca_price(symbol=symbol, position_side=position_side)

        if position_side == PositionSide.LONG:
            candidate_resistances = [resistance for resistance in sr_levels.resistances
                                     if resistance > current_price
                                     and resistance < position.entry_price
                                     and (last_filled_decrease_price is None or
                                          resistance != last_filled_decrease_price or
                                          last_filled_wiggle_order.order_type_identifier == OrderTypeIdentifier.WIGGLE_INCREASE)
                                     and (last_filled_increase_price is None or
                                          resistance != last_filled_increase_price)]
            if len(candidate_resistances) > 0:
                decrease_price = min(candidate_resistances)
            else:
                logger.info(f'{symbol} {position_side.name}: No resistance found above current price {current_price} '
                            f'and below position price {position.entry_price} and not equal to last filled decrease '
                            f'price {last_filled_decrease_price} and above last filled DCA price '
                            f'{last_filled_dca_price}, not placing decrease order.')
                return None
        else:
            candidate_supports = [support for support in sr_levels.supports
                                  if support < current_price
                                  and support > position.entry_price
                                  and (last_filled_decrease_price is None or
                                       support != last_filled_decrease_price or
                                       last_filled_wiggle_order.order_type_identifier == OrderTypeIdentifier.WIGGLE_INCREASE)
                                  and (last_filled_increase_price is None or support != last_filled_increase_price)]
            if len(candidate_supports) > 0:
                decrease_price = max(candidate_supports)
            else:
                logger.info(f'{symbol} {position_side.name}: No support found below current price {current_price} and '
                            f'above position price {position.entry_price} and not equal to last filled decrease price '
                            f'{last_filled_decrease_price} and below last filled DCA price {last_filled_dca_price}, '
                            f'not placing decrease order.')
                return None

        if wiggle_config.decrease_coin_size is not None:
            decrease_quantity = wiggle_config.decrease_coin_size
        else:
            decrease_quantity = round_(position.position_size * wiggle_config.decrease_size,
                                       symbol_information.quantity_step)

        logger.info(f'{symbol} {position_side.name}: Placing decrease order with quantity {decrease_quantity} at '
                    f'{decrease_price} based on current price {current_price} and position price '
                    f'{position.entry_price}')

        # create a buy order at the next lower support level
        return LimitOrder(order_type_identifier=OrderTypeIdentifier.WIGGLE_DECREASE,
                          symbol=symbol_information.symbol,
                          quantity=decrease_quantity,
                          side=Side.SELL if position_side == PositionSide.LONG else Side.BUY,
                          position_side=position_side,
                          initial_entry=False,
                          price=round_(decrease_price, symbol_information.price_step),
                          reduce_only=True)

    def calculate_increase_order(self,
                                 symbol: str,
                                 position_side: PositionSide,
                                 position: Position,
                                 symbol_information: SymbolInformation,
                                 wiggle_config: WiggleConfig,
                                 current_price: float) -> Order:
        if wiggle_config.enabled is False:
            return None

        last_filled_decrease_price = self.exchange_state.last_filled_decrease_price(symbol=symbol,
                                                                                    position_side=position_side)

        if last_filled_decrease_price is None:
            logger.info(f'{symbol} {position_side.name}: Not placing increase order because no decrease order was '
                        f'filled yet')
            return None

        last_filled_wiggle_order = self.exchange_state.last_filled_order(symbol=symbol,
                                                                         position_side=position_side,
                                                                         order_type_identifiers=[
                                                                             OrderTypeIdentifier.WIGGLE_DECREASE,
                                                                             OrderTypeIdentifier.WIGGLE_INCREASE])
        if last_filled_wiggle_order.order_type_identifier == OrderTypeIdentifier.WIGGLE_INCREASE:
            logger.info(f'{symbol} {position_side.name}: Not placing increase order because the last filled wiggle '
                        f'order was an increase order. A wiggle increase order is only allowed after a decrease order '
                        f'has been filled')
            return None

        sr_levels = self.sr_plugin.get_sr(symbol=symbol,
                                          position_side=position_side,
                                          period=wiggle_config.period,
                                          period_start_date=None,
                                          nr_clusters=10,
                                          outer_grid_price=None,
                                          period_timeframe=wiggle_config.timeframe,
                                          current_price=current_price,
                                          algo=wiggle_config.algo_instance)

        if position_side == PositionSide.LONG:
            supports_below_current_price = [support for support in sr_levels.supports
                                            if support < current_price
                                            and support < position.entry_price
                                            and support < last_filled_decrease_price]
            if len(supports_below_current_price) > 0:
                increase_price = max(supports_below_current_price)
            else:
                logger.info(f'{symbol} {position_side.name}: No support found below current price {current_price} and '
                            f'lower than the position price {position.entry_price} and last filled decrease price '
                            f'{last_filled_decrease_price}, not placing increase order')
                return None
        else:
            resistance_above_current_price = [resistance for resistance in sr_levels.resistances
                                              if resistance > current_price
                                              and resistance > position.entry_price
                                              and resistance > last_filled_decrease_price]
            if len(resistance_above_current_price) > 0:
                increase_price = min(resistance_above_current_price)
            else:
                logger.info(f'{symbol} {position_side.name}: No resistance found above current price {current_price} '
                            f'and higher than the position price {position.entry_price} and last filled decrease price '
                            f'{last_filled_decrease_price}, not placing decrease order.')
                return None

        if position_side == PositionSide.LONG:
            min_cost = symbol_information.minimal_buy_cost
        else:
            min_cost = symbol_information.minimal_sell_cost

        if wiggle_config.increase_coin_size is not None:
            increase_quantity = wiggle_config.increase_coin_size
        elif wiggle_config.increase_size is not None:
            increase_quantity = round_(position.position_size * wiggle_config.increase_size,
                                       symbol_information.quantity_step)
        else:
            increase_quantity = self.exchange_state.last_filled_decrease_quantity(symbol=symbol,
                                                                                  position_side=position_side)

        min_qty = calc_min_qty(price=self.exchange_state.last_tick_price(symbol),
                               inverse=False,
                               qty_step=symbol_information.quantity_step,
                               min_qty=symbol_information.minimum_quantity,
                               min_cost=min_cost)
        if increase_quantity is None:
            increase_quantity = min_qty
        increase_quantity = max(min_qty, increase_quantity)

        logger.info(f'{symbol} {position_side.name}: Placing increase order with quantity {increase_quantity} at '
                    f'{increase_price} based on current price {current_price} and position price '
                    f'{position.entry_price}')

        # create a buy order at the next lower support level
        return LimitOrder(order_type_identifier=OrderTypeIdentifier.WIGGLE_INCREASE,
                          symbol=symbol_information.symbol,
                          quantity=increase_quantity,
                          side=Side.BUY if position_side == PositionSide.LONG else Side.SELL,
                          position_side=position_side,
                          initial_entry=False,
                          price=increase_price)
