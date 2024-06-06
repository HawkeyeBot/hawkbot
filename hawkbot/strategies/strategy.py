import logging
from typing import List, Dict

from hawkbot.core.candlestore.candlestore import Candlestore
from hawkbot.core.config.active_config_manager import ActiveConfigManager
from hawkbot.core.config.bot_config import SymbolConfig, PositionSideConfig
from hawkbot.core.data_classes import Tick, OrderSet, SymbolInformation, ExchangeState, Trigger, \
    PositionSide, Mode, Position
from hawkbot.core.dynamic_entry.candidate_state import CandidateState
from hawkbot.core.liquidation.liquidationstore import LiquidationStore
from hawkbot.core.model import Order, OrderTypeIdentifier, LimitOrder, MarketOrder
from hawkbot.core.order_executor import OrderExecutor
from hawkbot.core.orderbook.orderbook import OrderBook
from hawkbot.core.strategy.data_classes import InitializeConfig
from hawkbot.core.tickstore.tickstore import Tickstore
from hawkbot.core.time_provider import TimeProvider
from hawkbot.exceptions import InvalidOrderException, InvalidArgumentException, OrderCancelException, PassedPriceException
from hawkbot.logging import user_log
from hawkbot.core.plugins.plugin_loader import PluginLoader
from hawkbot.utils import calc_min_qty, round_

logger = logging.getLogger(__name__)


class Strategy(object):
    def __init__(self):
        self.redis_host: str = None  # Set after initialization by bot
        self.redis_port: int = None  # Set after initialization by bot
        self.symbol_config: SymbolConfig = None  # Set after initialization by bot
        self.position_side_config: PositionSideConfig = None  # Set after initialization by bot
        self.plugin_loader: PluginLoader = None  # Set after initialization by bot
        self.order_executor: OrderExecutor = None  # Set after initialization by bot
        self.time_provider: TimeProvider = None  # Set after initialization by bot
        self.candlestore_client: Candlestore = None  # Set after initialization by bot
        self.orderbook: OrderBook = None  # Set after initialization by bot
        self.exchange_state: ExchangeState = None  # Set after initialization by bot
        self.liquidation_store: LiquidationStore = None  # Set after initialization by bot
        self.tick_store: Tickstore = None  # Set after initialization by bot
        self.filter_params: Dict[str, Dict] = {}  # Set after initialization by bot
        self.symbol: str = None  # Set after initialization by bot
        self.position_side: PositionSide = None  # Set after initialization by bot
        self.strategy_config: Dict = None  # Set after initialization by bot
        self.candidate_state: CandidateState = None  # Set after initialization by bot
        self.mode_processor = None  # Set after initialization by bot
        self.config = None  # Filled in init() function

    # to be implemented by strategy implementation
    def get_initializing_config(self) -> InitializeConfig:
        """
        Create an initial config that is used to initialize the exchange streams.
        :return: An InitialConfig specifying the streams, symbols.
        """
        return InitializeConfig()

    # to be implemented by strategy implementation
    def init(self):
        """
        Gives the strategy an opportunity to perform initialization before being called for processing.
        For example getting a plugin from the plugin_loader for easy reference can be done here
        :return: None
        """
        self.config = ActiveConfigManager(redis_host=self.redis_host, redis_port=self.redis_port)

    # to be implemented by strategy implementation
    def on_tick(self,
                tick: Tick,
                position: Position,
                symbol_information: SymbolInformation,
                wallet_balance: float):
        pass

    # to be implemented by strategy implementation
    def on_pulse(self,
                 symbol: str,
                 position: Position,
                 symbol_information: SymbolInformation,
                 wallet_balance: float,
                 current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_strategy_activated(self,
                              symbol: str,
                              position: Position,
                              symbol_information: SymbolInformation,
                              wallet_balance: float,
                              current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_no_open_position(self,
                            symbol: str,
                            position: Position,
                            symbol_information: SymbolInformation,
                            wallet_balance: float,
                            current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_position_closed(self,
                           symbol: str,
                           position: Position,
                           symbol_information: SymbolInformation,
                           wallet_balance: float,
                           current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_mode_changed(self,
                        symbol: str,
                        position: Position,
                        symbol_information: SymbolInformation,
                        wallet_balance: float,
                        current_price: float,
                        new_mode: Mode):
        pass

    # to be implemented by strategy implementation
    def on_position_on_startup(self,
                               symbol: str,
                               position: Position,
                               symbol_information: SymbolInformation,
                               wallet_balance: float,
                               current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_no_position_on_startup(self,
                                  symbol: str,
                                  position: Position,
                                  symbol_information: SymbolInformation,
                                  wallet_balance: float,
                                  current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_position_change(self,
                           symbol: str,
                           position: Position,
                           symbol_information: SymbolInformation,
                           wallet_balance: float,
                           current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_initial_entry_order_filled(self,
                                      symbol: str,
                                      position: Position,
                                      symbol_information: SymbolInformation,
                                      wallet_balance: float,
                                      current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_tp_order_filled(self,
                           symbol: str,
                           position: Position,
                           symbol_information: SymbolInformation,
                           wallet_balance: float,
                           current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_dca_order_filled(self,
                            symbol: str,
                            position: Position,
                            symbol_information: SymbolInformation,
                            wallet_balance: float,
                            current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_entry_order_filled(self,
                              symbol: str,
                              position: Position,
                              symbol_information: SymbolInformation,
                              wallet_balance: float,
                              current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_reduce_order_filled(self,
                               symbol: str,
                               position: Position,
                               symbol_information: SymbolInformation,
                               wallet_balance: float,
                               current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_position_reduced(self,
                            symbol: str,
                            position: Position,
                            symbol_information: SymbolInformation,
                            wallet_balance: float,
                            current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_tp_refill_order_filled(self,
                                  symbol: str,
                                  position: Position,
                                  symbol_information: SymbolInformation,
                                  wallet_balance: float,
                                  current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_order_cancelled(self,
                           symbol: str,
                           position: Position,
                           symbol_information: SymbolInformation,
                           wallet_balance: float,
                           current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_periodic_check(self,
                          symbol: str,
                          position: Position,
                          symbol_information: SymbolInformation,
                          wallet_balance: float,
                          current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_wallet_changed(self,
                          symbol: str,
                          position: Position,
                          symbol_information: SymbolInformation,
                          wallet_balance: float,
                          current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_wiggle_decrease_filled(self,
                                  symbol: str,
                                  position: Position,
                                  symbol_information: SymbolInformation,
                                  wallet_balance: float,
                                  current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_wiggle_increase_filled(self,
                                  symbol: str,
                                  position: Position,
                                  symbol_information: SymbolInformation,
                                  wallet_balance: float,
                                  current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_orderbook_updated(self,
                             symbol: str,
                             position: Position,
                             symbol_information: SymbolInformation,
                             wallet_balance: float,
                             current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_stoploss_filled(self,
                           symbol: str,
                           position: Position,
                           symbol_information: SymbolInformation,
                           wallet_balance: float,
                           current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_unknown_filled(self,
                          symbol: str,
                          position: Position,
                          symbol_information: SymbolInformation,
                          wallet_balance: float,
                          current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_shutdown(self,
                    symbol: str,
                    position: Position,
                    symbol_information: SymbolInformation,
                    wallet_balance: float,
                    current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_manual_place_grid(self,
                             symbol: str,
                             position: Position,
                             symbol_information: SymbolInformation,
                             wallet_balance: float,
                             current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_manual_remove_grid(self,
                              symbol: str,
                              position: Position,
                              symbol_information: SymbolInformation,
                              wallet_balance: float,
                              current_price: float):
        pass

    # to be implemented by strategy implementation
    def on_new_data(self,
                    symbol: str,
                    position: Position,
                    symbol_information: SymbolInformation,
                    wallet_balance: float,
                    current_price: float):
        pass

    def log_trigger(self, trigger: Trigger) -> bool:
        return trigger not in [Trigger.PULSE]

    #######################
    # BASE IMPLEMENTATION #
    #######################

    def process_pulse(self,
                      symbol: str,
                      position: Position,
                      symbol_information: SymbolInformation,
                      wallet_balance: float,
                      current_price: float):
        self.mode_processor.enforce_mode(symbol=symbol, position_side=self.position_side)

        self.on_pulse(symbol=symbol,
                      position=position,
                      symbol_information=symbol_information,
                      wallet_balance=wallet_balance,
                      current_price=current_price)

    def process_tick(self, tick: Tick):
        if self.mode_processor.get_mode(symbol=tick.symbol, position_side=self.position_side) == Mode.MANUAL:
            return

        symbol = tick.symbol
        position = self.exchange_state.position(symbol=symbol, position_side=self.position_side)
        symbol_information = self.exchange_state.get_symbol_information(symbol)
        wallet_balance = self.exchange_state.symbol_balance(symbol)

        self.mode_processor.enforce_mode(symbol=symbol, position_side=self.position_side)

        self.on_tick(tick=tick,
                     position=position,
                     symbol_information=symbol_information,
                     wallet_balance=wallet_balance)

    def process_trigger(self, symbol: str, triggers: List[Trigger]):
        if self.exchange_state.is_initialized(symbol) is False:
            logger.debug(f"Service not initialized yet for symbol {symbol}")
            return

        active_mode = self.mode_processor.get_mode(symbol=symbol, position_side=self.position_side)
        if active_mode == Mode.MANUAL:
            logger.debug(f'{symbol} {self.position_side.name}: ignoring triggers because '
                         f'mode MANUAL is active')
            return

        symbol_information = self.exchange_state.get_symbol_information(symbol)
        position = self.exchange_state.position(symbol=symbol, position_side=self.position_side)

        if Trigger.SHUTDOWN in triggers:
            user_log.debug(f'{symbol} {self.position_side.name}: Received trigger SHUTDOWN', __name__)
            self.on_shutdown(symbol=symbol,
                             position=position,
                             symbol_information=symbol_information,
                             wallet_balance=self.exchange_state.symbol_balance(symbol),
                             current_price=self.exchange_state.last_tick_price(symbol))
            self.config.shutdown()
        if Trigger.POSITION_CLOSED in triggers:
            user_log.debug(f'{symbol} {self.position_side.name}: Received trigger POSITION_CLOSED', __name__)
            self.on_position_closed(symbol=symbol,
                                    position=position,
                                    symbol_information=symbol_information,
                                    wallet_balance=self.exchange_state.symbol_balance(symbol),
                                    current_price=self.exchange_state.last_tick_price(symbol))
        if Trigger.MODE_CHANGED in triggers:
            if active_mode == Mode.NORMAL and \
                    self.exchange_state.has_no_open_position(symbol=symbol, position_side=self.position_side):
                logger.info(f'{symbol} {self.position_side.name}: Actively triggering NO_OPEN_POSITION because mode '
                            f'changed to NORMAL')
                triggers.append(Trigger.NO_OPEN_POSITION)

            user_log.debug(f'{symbol} {self.position_side.name}: Received trigger MODE_CHANGED', __name__)
            self.on_mode_changed(symbol=symbol,
                                 position=position,
                                 symbol_information=symbol_information,
                                 wallet_balance=self.exchange_state.symbol_balance(symbol),
                                 current_price=self.exchange_state.last_tick_price(symbol),
                                 new_mode=self.position_side_config.mode)

        if Trigger.STOPLOSS_FILLED in triggers:
            user_log.debug(f'{symbol} {self.position_side.name}: Received trigger STOPLOSS_FILLED', __name__)
            self.on_stoploss_filled(symbol=symbol,
                                    position=position,
                                    symbol_information=symbol_information,
                                    wallet_balance=self.exchange_state.symbol_balance(symbol),
                                    current_price=self.exchange_state.last_tick_price(symbol))
        if Trigger.NO_OPEN_POSITION in triggers:
            if active_mode != Mode.NORMAL:
                logger.info(f'{symbol} {self.position_side.name}: Ignoring no open position because of active mode '
                            f'{self.mode_processor.get_mode(symbol=symbol, position_side=self.position_side)}')
                if active_mode in [Mode.GRACEFUL_STOP, Mode.NO_ORDERS_ALLOWED]:
                    orders = self.exchange_state.all_open_orders(symbol=symbol, position_side=self.position_side)
                    orders = [order for order in orders if
                              order.order_type_identifier == OrderTypeIdentifier not in [OrderTypeIdentifier.UNKNOWN,
                                                                                         OrderTypeIdentifier.WEB]]
                    self.order_executor.cancel_orders(orders)
                return
            else:
                if position.no_position():
                    user_log.debug(f'{symbol} {self.position_side.name}: Received trigger NO_OPEN_POSITION', __name__)
                    self.on_no_open_position(symbol=symbol,
                                             position=position,
                                             symbol_information=symbol_information,
                                             wallet_balance=self.exchange_state.symbol_balance(symbol),
                                             current_price=self.exchange_state.last_tick_price(symbol))
        else:
            if Trigger.STRATEGY_ACTIVATED in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger STRATEGY_ACTIVATED',
                               __name__)
                self.on_strategy_activated(symbol=symbol,
                                           position=position,
                                           symbol_information=symbol_information,
                                           wallet_balance=self.exchange_state.symbol_balance(symbol),
                                           current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.OPEN_POSITION_ON_STARTUP in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger OPEN_POSITION_ON_STARTUP',
                               __name__)
                self.on_position_on_startup(symbol=symbol,
                                            position=position,
                                            symbol_information=symbol_information,
                                            wallet_balance=self.exchange_state.symbol_balance(symbol),
                                            current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.NO_POSITION_ON_STARTUP in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger NO_POSITION_AT_STARTUP',
                               __name__)
                self.on_no_position_on_startup(symbol=symbol,
                                               position=position,
                                               symbol_information=symbol_information,
                                               wallet_balance=self.exchange_state.symbol_balance(symbol),
                                               current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.POSITION_CHANGE_DETECTED in triggers:
                if Trigger.INITIAL_ENTRY_FILLED in triggers:
                    logger.debug(f'{symbol} {position.position_side.name}: Skipping trigger POSITION_CHANGE_DETECTED, '
                                 f'because the trigger INITIAL_ENTRY_FILLED is given off at the same time')
                else:
                    user_log.debug(f'{symbol} {position.position_side.name}: Received trigger POSITION_CHANGE_DETECTED', __name__)
                    self.on_position_change(symbol=symbol,
                                            position=position,
                                            symbol_information=symbol_information,
                                            wallet_balance=self.exchange_state.symbol_balance(symbol),
                                            current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.INITIAL_ENTRY_FILLED in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger INITIAL_ENTRY_FILLED', __name__)
                self.on_initial_entry_order_filled(symbol=symbol,
                                                   position=position,
                                                   symbol_information=symbol_information,
                                                   wallet_balance=self.exchange_state.symbol_balance(symbol),
                                                   current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.TP_ORDER_FILLED in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger TP_ORDER_FILLED', __name__)
                self.on_tp_order_filled(symbol=symbol,
                                        position=position,
                                        symbol_information=symbol_information,
                                        wallet_balance=self.exchange_state.symbol_balance(symbol),
                                        current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.DCA_ORDER_FILLED in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger DCA_ORDER_FILLED', __name__)
                self.on_dca_order_filled(symbol=symbol,
                                         position=position,
                                         symbol_information=symbol_information,
                                         wallet_balance=self.exchange_state.symbol_balance(symbol),
                                         current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.ENTRY_FILLED in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger ENTRY_FILLED', __name__)
                self.on_entry_order_filled(symbol=symbol,
                                           position=position,
                                           symbol_information=symbol_information,
                                           wallet_balance=self.exchange_state.symbol_balance(symbol),
                                           current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.REDUCE_FILLED in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger REDUCE_FILLED', __name__)
                self.on_reduce_order_filled(symbol=symbol,
                                            position=position,
                                            symbol_information=symbol_information,
                                            wallet_balance=self.exchange_state.symbol_balance(symbol),
                                            current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.POSITION_REDUCED in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger POSITION_REDUCED', __name__)
                self.on_position_reduced(symbol=symbol,
                                         position=position,
                                         symbol_information=symbol_information,
                                         wallet_balance=self.exchange_state.symbol_balance(symbol),
                                         current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.TP_REFILL_FILLED in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger TP_REFILL_FILLED', __name__)
                self.on_tp_refill_order_filled(symbol=symbol,
                                               position=position,
                                               symbol_information=symbol_information,
                                               wallet_balance=self.exchange_state.symbol_balance(symbol),
                                               current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.ORDER_CANCELLED in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger ORDER_CANCELLED', __name__)
                self.on_order_cancelled(symbol=symbol,
                                        position=position,
                                        symbol_information=symbol_information,
                                        wallet_balance=self.exchange_state.symbol_balance(symbol),
                                        current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.WALLET_CHANGED in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger WALLET_CHANGED', __name__)
                self.on_wallet_changed(symbol=symbol,
                                       position=position,
                                       symbol_information=symbol_information,
                                       wallet_balance=self.exchange_state.symbol_balance(symbol),
                                       current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.WIGGLE_DECREASE_FILLED in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger WIGGLE_DECREASE_FILLED', __name__)
                self.on_wiggle_decrease_filled(symbol=symbol,
                                               position=position,
                                               symbol_information=symbol_information,
                                               wallet_balance=self.exchange_state.symbol_balance(symbol),
                                               current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.WIGGLE_INCREASE_FILLED in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger WIGGLE_INCREASE_FILLED', __name__)
                self.on_wiggle_increase_filled(symbol=symbol,
                                               position=position,
                                               symbol_information=symbol_information,
                                               wallet_balance=self.exchange_state.symbol_balance(symbol),
                                               current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.ORDERBOOK_UPDATED in triggers:
                logger.debug(f'{symbol} {self.position_side.name}: Received trigger ORDERBOOK_UPDATED')
                self.on_orderbook_updated(symbol=symbol,
                                          position=position,
                                          symbol_information=symbol_information,
                                          wallet_balance=self.exchange_state.symbol_balance(symbol),
                                          current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.PERIODIC_CHECK in triggers:
                logger.debug(f'{symbol} {self.position_side.name}: Received trigger PERIODIC_CHECK')
                if self.position_side_config.cancel_duplicate_orders:
                    self.cancel_duplicate_side_dca_orders(symbol=symbol, position_side=self.position_side)
                self.on_periodic_check(symbol=symbol,
                                       position=position,
                                       symbol_information=symbol_information,
                                       wallet_balance=self.exchange_state.symbol_balance(symbol),
                                       current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.PULSE in triggers:
                logger.debug(f'{symbol} {self.position_side.name}: Received trigger PULSE')
                self.process_pulse(symbol=symbol,
                                   position=position,
                                   symbol_information=symbol_information,
                                   wallet_balance=self.exchange_state.symbol_balance(symbol),
                                   current_price=self.exchange_state.last_tick_price(symbol))
            if Trigger.MANUAL_PLACE_GRID in triggers:
                logger.debug(f'{symbol} {self.position_side.name}: Received trigger MANUAL_PLACE_GRID')
                self.on_manual_place_grid(symbol=symbol,
                                          position=position,
                                          symbol_information=symbol_information,
                                          wallet_balance=self.exchange_state.symbol_balance(symbol),
                                          current_price=self.exchange_state.last_tick_price(symbol))

            if Trigger.MANUAL_REMOVE_GRID in triggers:
                logger.debug(f'{symbol} {self.position_side.name}: Received trigger MANUAL_REMOVE_GRID')
                self.on_manual_remove_grid(symbol=symbol,
                                           position=position,
                                           symbol_information=symbol_information,
                                           wallet_balance=self.exchange_state.symbol_balance(symbol),
                                           current_price=self.exchange_state.last_tick_price(symbol))

            if Trigger.NEW_DATA in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: Received trigger NEW_DATA', __name__)
                self.on_new_data(symbol=symbol,
                                 position=position,
                                 symbol_information=symbol_information,
                                 wallet_balance=self.exchange_state.symbol_balance(symbol),
                                 current_price=self.exchange_state.last_tick_price(symbol))

            if Trigger.UNKNOWN_ORDER_FILLED in triggers:
                user_log.debug(f'{symbol} {self.position_side.name}: An unknown order has been filled', __name__)
                self.on_unknown_filled(symbol=symbol,
                                       position=position,
                                       symbol_information=symbol_information,
                                       wallet_balance=self.exchange_state.symbol_balance(symbol),
                                       current_price=self.exchange_state.last_tick_price(symbol))

    def _is_valid_orderset(self,
                           order_set: OrderSet,
                           symbol_information: SymbolInformation):
        try:
            order_set.validate(symbol_information)
            return True
        except InvalidOrderException as e:
            logger.warning(f"Orderset contains one or more invalid orders({e}), "
                           f"not executing the orderset! Orderset = {order_set}")
            return False

    def cancel_duplicate_side_dca_orders(self, symbol: str, position_side: PositionSide):
        open_orders = self.exchange_state.open_dca_orders(symbol=symbol, position_side=position_side)
        encountered_orders = []  # make sure we flush out potential duplicate entries on the exchange
        for order in open_orders:
            same_orders = [o for o in encountered_orders
                           if o.side == order.side
                           and o.position_side == order.position_side
                           and o.type == order.type
                           and o.price == order.price]

            if len(same_orders) == 0:
                encountered_orders.append(order)
            else:
                user_log.info(f'Cancelling detected duplicate {position_side.name} order {order}', __name__)
                self.order_executor.cancel_order(order)

    def calc_wallet_exposure_ratio(self):
        wallet_exposure = self.position_side_config.wallet_exposure
        wallet_exposure_ratio = self.position_side_config.wallet_exposure_ratio

        return self.exchange_state.calculate_wallet_exposure_ratio(symbol=self.symbol,
                                                                   wallet_exposure=wallet_exposure,
                                                                   wallet_exposure_ratio=wallet_exposure_ratio)

    def enforce_grid(self,
                     new_orders: List[Order],
                     exchange_orders: List[Order],
                     lowest_price_first: bool = False,
                     cancel_before_create: bool = True,
                     throw_exception_on_price_passed: bool = False) -> bool:
        if len(new_orders) == 0 and len(exchange_orders) == 0:
            return False

        if len(new_orders) > 0:
            if any([order.order_type_identifier == OrderTypeIdentifier.INITIAL_ENTRY for order in new_orders]):
                if self.exchange_state.has_open_position(symbol=new_orders[0].symbol, position_side=new_orders[0].position_side):
                    logger.warning(f'{new_orders[0].symbol} {new_orders[0].position_side.name}: Not placing orders with initial entry order(s) because an open position exists. '
                                   f'This can happen when the state synchronizer determined there is no open position, and before this trigger is processed, a position is opened. '
                                   f'This situation is expected to correct itself')
                    return False

        market_order = any([isinstance(o, MarketOrder) for o in new_orders])
        if market_order or (sorted(new_orders, key=lambda x: x.price) != sorted(exchange_orders, key=lambda x: x.price)):
            if len(new_orders) > 0:
                symbol = new_orders[0].symbol
                position_side = new_orders[0].position_side
            else:
                symbol = exchange_orders[0].symbol
                position_side = exchange_orders[0].position_side
            logger.info(f'{symbol} {position_side.name}: Enforcing grid, on_exchange = {exchange_orders}, '
                        f'new_orders = {new_orders}, current price = {self.exchange_state.last_tick_price(symbol)}')

            if cancel_before_create is True:
                try:
                    self._cancel_orders(symbol=symbol, position_side=position_side, exchange_orders=exchange_orders, new_orders=new_orders)
                except OrderCancelException:
                    return True

                try:
                    self._create_orders(exchange_orders=exchange_orders, new_orders=new_orders, lowest_price_first=lowest_price_first)
                except PassedPriceException as e:
                    if throw_exception_on_price_passed is True:
                        raise e
                    return False
                return True
            else:
                try:
                    self._create_orders(exchange_orders=exchange_orders, new_orders=new_orders, lowest_price_first=lowest_price_first)
                except PassedPriceException as e:
                    if throw_exception_on_price_passed is True:
                        raise e
                    return False
                try:
                    self._cancel_orders(symbol=symbol, position_side=position_side, exchange_orders=exchange_orders, new_orders=new_orders)
                except OrderCancelException:
                    pass

                return True
        return False

    def _create_orders(self, exchange_orders: List[Order], new_orders: List[Order], lowest_price_first: bool):
        market_orders = [o for o in new_orders if isinstance(o, MarketOrder)]
        new_orders_to_place = [o for o in new_orders if not isinstance(o, MarketOrder)]
        new_orders_to_place.sort(key=lambda x: x.price, reverse=not lowest_price_first)
        new_orders_to_place.extend(market_orders)
        orders_to_place = []
        for new_order in new_orders:
            if new_order not in exchange_orders:
                orders_to_place.append(new_order)
        self.order_executor.create_orders(orders_to_place)

    def _cancel_orders(self, symbol: str, position_side: PositionSide, exchange_orders: List[Order], new_orders: List[Order]) -> bool:
        # orders on exchange that need to be cancelled
        orders_to_cancel = []
        encountered_orders = []  # make sure we flush out potential duplicate entries on the exchange
        for exchange_order in exchange_orders:
            if exchange_order not in new_orders:
                orders_to_cancel.append(exchange_order)
            if exchange_order not in encountered_orders:
                encountered_orders.append(exchange_order)
            else:
                orders_to_cancel.append(exchange_order)

        logger.debug(f'{symbol} {position_side.name}: Cancelling orders: {orders_to_cancel}')

        all_orders_cancelled_successfully = self.order_executor.cancel_orders(orders=orders_to_cancel)
        if all_orders_cancelled_successfully is False:
            if len(new_orders) == 1 and new_orders[0].order_type_identifier == OrderTypeIdentifier.INITIAL_ENTRY and \
                    len(exchange_orders) == 1 and exchange_orders[0].order_type_identifier == OrderTypeIdentifier.INITIAL_ENTRY:
                logger.warning(f"{symbol} {position_side.name}: Failed to cancel the existing initial entry order on the exchange before attempting to place a new initial "
                               f"entry order. This can happen when the websocket data hasn't come in yet/been processed yet at the time the new initial entry order was "
                               f"calculated. Not continuing with placing the new entry order, because this could lead to a duplicate initial entry.")
                raise OrderCancelException()

    def place_entry_order(self,
                          order_price: float,
                          order_quantity: float = None,
                          ratio_of_exposed_balance: float = None,
                          position_side: PositionSide = None):
        if position_side is None:
            position_side = self.position_side

        symbol_information = self.exchange_state.get_symbol_information(self.symbol)
        if ratio_of_exposed_balance is not None:
            total_balance = self.exchange_state.symbol_balance(self.symbol)
            wallet_exposure_ratio = self.calc_wallet_exposure_ratio()
            exposed_balance = total_balance * wallet_exposure_ratio
            cost_for_order = exposed_balance * ratio_of_exposed_balance

            order_quantity = cost_for_order / order_price
        elif order_quantity is None:
            raise InvalidArgumentException(f"{self.symbol} {position_side.name}: Either order_quantity or ratio_of_exposed_balance is required")

        order_quantity = round_(number=order_quantity, step=symbol_information.quantity_step)
        min_entry_qty = calc_min_qty(price=order_price,
                                     inverse=False,
                                     qty_step=symbol_information.quantity_step,
                                     min_qty=symbol_information.minimum_quantity,
                                     min_cost=symbol_information.minimal_buy_cost)
        if order_quantity < min_entry_qty:
            logger.warning(f'{self.symbol} {self.position_side.name}: The entry at price {order_price} with quantity '
                           f'{order_quantity} does not meet minimum quantity {min_entry_qty}.')
            return

        order_type_identifier = OrderTypeIdentifier.INITIAL_ENTRY
        if self.exchange_state.has_open_position(symbol=self.symbol, position_side=position_side):
            order_type_identifier = OrderTypeIdentifier.DCA

        new_order = LimitOrder(
            order_type_identifier=order_type_identifier,
            symbol=self.symbol,
            quantity=order_quantity,
            side=position_side.increase_side(),
            position_side=self.position_side,
            initial_entry=False,
            price=round_(number=order_price, step=symbol_information.price_step))

        existing_orders = self.exchange_state.open_orders(symbol=self.symbol, position_side=position_side, order_type_identifiers=[order_type_identifier])
        self.enforce_grid(new_orders=[new_order], exchange_orders=existing_orders)
