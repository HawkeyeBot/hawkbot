import logging

from hawkbot.core.model import PositionSide, Position, SymbolInformation, Mode, OrderTypeIdentifier
from hawkbot.core.strategy.data_classes import InitializeConfig
from hawkbot.exceptions import MultipleOrdersException, InvalidConfigurationException
from hawkbot.logging import user_log
from hawkbot.plugins.autoreduce.autoreduce_plugin import AutoreducePlugin, AutoreduceConfig
from hawkbot.plugins.clustering_sr.clustering_sr_plugin import ClusteringSupportResistancePlugin
from hawkbot.plugins.dca.dca_plugin import DcaPlugin, DcaConfig
from hawkbot.plugins.gridstorage.gridstorage_plugin import GridStoragePlugin
from hawkbot.plugins.gtfo.gtfo_plugin import GtfoPlugin, GtfoConfig
from hawkbot.plugins.hedge_plugin.hedge_plugin import HedgePlugin, HedgeConfig
from hawkbot.plugins.ob_tp.ob_tp_plugin import ObTpConfig, ObTpPlugin
from hawkbot.plugins.stoploss.stoploss_plugin import StoplossPlugin, StoplossConfig
from hawkbot.plugins.stoplosses.data_classes import StoplossesConfig
from hawkbot.plugins.stoplosses.stoplosses_plugin import StoplossesPlugin
from hawkbot.plugins.tp.tp_plugin import TpPlugin, TpConfig
from hawkbot.plugins.tp_refill.tp_refill_plugin import TpRefillPlugin, TpRefillConfig
from hawkbot.plugins.wiggle.wiggle_plugin import WigglePlugin, WiggleConfig
from hawkbot.strategies.strategy import Strategy

logger = logging.getLogger(__name__)


class AbstractBaseStrategy(Strategy):
    support_plugin: ClusteringSupportResistancePlugin = None
    gridstorage_plugin: GridStoragePlugin = None
    dca_plugin: DcaPlugin = None
    tp_plugin: TpPlugin = None
    obtp_plugin: ObTpPlugin = None
    tp_refill_plugin: TpRefillPlugin = None
    stoploss_plugin: StoplossPlugin = None
    stoplosses_plugin: StoplossesPlugin = None
    wiggle_plugin: WigglePlugin = None
    gtfo_plugin: GtfoPlugin = None
    autoreduce_plugin: AutoreducePlugin = None
    hedge_plugin: HedgePlugin = None

    def __init__(self):
        super().__init__()
        self.dca_config: DcaConfig = None
        self.tp_config: TpConfig = None
        self.obtp_config: ObTpConfig = None
        self.tp_refill_config: TpRefillConfig = None
        self.stoploss_config: StoplossConfig = None
        self.stoplosses_config: StoplossesConfig = None
        self.wiggle_config: WiggleConfig = None
        self.gtfo_config: GtfoConfig = None
        self.autoreduce_config: AutoreduceConfig = None
        self.hedge_config: HedgeConfig = None
        self.no_entry_above: float = None
        self.no_entry_below: float = None
        self.previous_price: float = None
        self.mode_on_price_outside_boundaries: Mode = None
        self.minimum_number_of_available_dcas: int = 3
        self.cancel_orders_on_position_close: bool = True
        self.strategy_last_execution: int = 0

    def init(self):
        super().init()
        self.init_config()

    def init_config(self):
        if 'no_entry_below' in self.strategy_config:
            self.no_entry_below = self.strategy_config['no_entry_below']
        if 'no_entry_above' in self.strategy_config:
            self.no_entry_above = self.strategy_config['no_entry_above']
        if 'mode_on_price_outside_boundaries' in self.strategy_config:
            self.mode_on_price_outside_boundaries = Mode[self.strategy_config['mode_on_price_outside_boundaries']]
        if 'minimum_number_of_available_dcas' in self.strategy_config:
            self.minimum_number_of_available_dcas = self.strategy_config['minimum_number_of_available_dcas']
        if 'cancel_orders_on_position_close' in self.strategy_config:
            self.cancel_orders_on_position_close = self.strategy_config['cancel_orders_on_position_close']

        if 'dca' in self.strategy_config:
            self.dca_config = self.dca_plugin.parse_config(self.strategy_config['dca'])
        else:
            self.dca_config = self.dca_plugin.parse_config({})

        if 'tp' in self.strategy_config:
            self.tp_config = self.tp_plugin.parse_config(self.strategy_config['tp'])
        else:
            self.tp_config = self.tp_plugin.parse_config({})

        if 'obtp' in self.strategy_config:
            self.obtp_config = self.obtp_plugin.parse_config(self.strategy_config['obtp'])
        else:
            self.obtp_config = self.obtp_plugin.parse_config({})

        if self.tp_config.enabled and self.obtp_config.enabled:
            raise InvalidConfigurationException(f'Specifying both \'tp\' and \'obtp\' in the configuration is not '
                                                f'allowed. Either remove one of the two or disable one using the '
                                                f'\'enabled\' parameter')

        if 'stoploss' in self.strategy_config:
            self.stoploss_config = self.stoploss_plugin.parse_config(self.strategy_config['stoploss'])
        else:
            self.stoploss_config = self.stoploss_plugin.parse_config({})

        if 'stoplosses' in self.strategy_config:
            self.stoplosses_config = self.stoplosses_plugin.parse_config(self.strategy_config['stoplosses'])
        else:
            self.stoplosses_config = self.stoplosses_plugin.parse_config({})

        if 'tp_refill' in self.strategy_config:
            self.tp_refill_config = self.tp_refill_plugin.parse_config(self.strategy_config['tp_refill'])
        else:
            self.tp_refill_config = self.tp_refill_plugin.parse_config({})

        if 'wiggle' in self.strategy_config:
            self.wiggle_config = self.wiggle_plugin.parse_config(self.strategy_config['wiggle'])
        else:
            self.wiggle_config = self.wiggle_plugin.parse_config({})

        if 'gtfo' in self.strategy_config:
            self.gtfo_config = self.gtfo_plugin.parse_config(self.strategy_config['gtfo'])
        else:
            self.gtfo_config = self.gtfo_plugin.parse_config({})

        if 'autoreduce' in self.strategy_config:
            self.autoreduce_config = self.autoreduce_plugin.parse_config(self.strategy_config['autoreduce'])
        else:
            self.autoreduce_config = self.autoreduce_plugin.parse_config({})

        if 'hedge' in self.strategy_config:
            self.hedge_config = self.hedge_plugin.parse_config(self.strategy_config['hedge'])
        else:
            self.hedge_config = self.hedge_plugin.parse_config({})

    def get_initializing_config(self) -> InitializeConfig:
        init_config = InitializeConfig()
        if self.dca_config is not None:
            if self.dca_config.first_level_period is not None:
                init_config.add_period(self.dca_config.first_level_period_timeframe, self.dca_config.first_level_period)
            if self.dca_config.period is not None:
                init_config.add_period(self.dca_config.period_timeframe, self.dca_config.period)
            if self.dca_config.outer_price_period is not None:
                init_config.add_period(self.dca_config.outer_price_timeframe, self.dca_config.outer_price_period)
        if self.wiggle_config is not None and self.wiggle_config.period is not None:
            init_config.add_period(self.wiggle_config.timeframe, self.wiggle_config.period)

        return init_config

    def on_pulse(self,
                 symbol: str,
                 position: Position,
                 symbol_information: SymbolInformation,
                 wallet_balance: float,
                 current_price: float):
        wallet_exposure = self.calc_wallet_exposure_ratio()
        exposed_balance = wallet_balance * wallet_exposure
        gtfo_executed = self.gtfo_plugin.run_gtfo(symbol=symbol,
                                                  current_price=current_price,
                                                  gtfo_config=self.gtfo_config,
                                                  position=position,
                                                  exposed_balance=exposed_balance,
                                                  wallet_balance=wallet_balance)

        ms_since_last_execution = abs(self.time_provider.get_utc_now_timestamp() - self.strategy_last_execution)
        if ms_since_last_execution < self.position_side_config.tick_execution_interval_ms:
            logger.debug('%s %s: SKIPPING PULSE EXECUTION Strategy executed within last %sms at %s.',
                         self.symbol,
                         position.position_side.name,
                         self.position_side_config.tick_execution_interval_ms,
                         self.strategy_last_execution)
            return

        if gtfo_executed is False and position.has_position():
            if self.tp_refill_config.enabled is True and current_price >= position.entry_price:
                # If there is a TP_REFILL order, make sure it is adjusted on each tick processing to the highest bid
                # to ensure it's filled as fast as possible
                try:
                    tp_refill_order = self.exchange_state.open_tp_refill_order(symbol=position.symbol,
                                                                               position_side=PositionSide.LONG)
                    if tp_refill_order is not None:
                        highest_bid = self.orderbook.get_highest_bid(symbol=position.symbol,
                                                                     current_price=current_price)
                        if highest_bid > tp_refill_order.price:
                            logger.info(f'Adjusting price of long tp-refill order from {tp_refill_order.price} '
                                        f'to {highest_bid}')
                            order_actually_cancelled = self.order_executor.cancel_order(tp_refill_order)
                            if order_actually_cancelled is True:
                                self.enforce_tp_refill(symbol=symbol, position=position,
                                                       symbol_information=symbol_information,
                                                       current_price=current_price)
                            else:
                                logger.warning(f"{symbol} {self.position_side.name}: Cancelling the previous "
                                               f"TP_REFILL_ORDER that is supposedly on the exchange didn't actually "
                                               f"cancel an order. This is most likely a result of that TP_REFILL_ORDER "
                                               f"having been hit in the meantime. Not creating an adjusted TP_REFILL "
                                               f"order in this cycle to prevent accidentally having 2 TP_REFILL orders "
                                               f"filled.")
                except MultipleOrdersException:
                    logger.warning('Unexpectedly encountered multiple TP_REFILL orders, cancelling all but 1')
                    all_tp_refill_orders = self.exchange_state.open_tp_refill_orders(symbol=symbol,
                                                                                     position_side=self.position_side)
                    # cancel all TP_REFILL orders except the first one
                    [self.order_executor.cancel_order(order) for order in all_tp_refill_orders[1:]]

            if self.shift_tp_grid_needed(symbol=symbol, position_side=self.position_side,
                                         current_price=current_price):
                changed = self.enforce_tp_grid(position=position,
                                               symbol_information=symbol_information,
                                               symbol=symbol,
                                               current_price=current_price,
                                               wiggle_config=self.wiggle_config)
                if changed:
                    user_log.info(f"{symbol} {self.position_side.name}: Recreating TP grid because price crossed "
                                  f"previous TP price", __name__)
            elif self.previous_price is not None:
                crossed_entry = False
                crossed_entry |= self.position_side == PositionSide.LONG and \
                                 current_price <= position.entry_price < self.previous_price
                crossed_entry |= self.position_side == PositionSide.SHORT and \
                                 current_price >= position.entry_price > self.previous_price
                if crossed_entry:
                    changed = self.enforce_tp_grid(position=position,
                                                   symbol_information=symbol_information,
                                                   symbol=symbol,
                                                   current_price=current_price,
                                                   wiggle_config=self.wiggle_config)
                    if changed:
                        user_log.info(f"{symbol} {self.position_side.name}: Recreating TP grid because price crossed "
                                      f"entry", __name__)

            self.enforce_wiggle(symbol=symbol,
                                position=position,
                                symbol_information=symbol_information,
                                current_price=current_price)
        self.enforce_stoploss(symbol=symbol,
                              position=position,
                              position_side=self.position_side,
                              symbol_information=symbol_information,
                              current_price=current_price)

        self.enforce_autoreduce(symbol=symbol,
                                position_side=position.position_side,
                                position=position,
                                symbol_information=symbol_information,
                                current_price=current_price)

        self.previous_price = current_price
        self.strategy_last_execution = int(self.time_provider.get_utc_now_timestamp())

    def on_shutdown(self,
                    symbol: str,
                    position: Position,
                    symbol_information: SymbolInformation,
                    wallet_balance: float,
                    current_price: float):
        if self.position_side == PositionSide.BOTH:
            if not self.exchange_state.has_open_position(symbol=symbol, position_side=PositionSide.BOTH):
                user_log.info(f'{symbol} {PositionSide.BOTH.name}: During deactivation, there were open orders detected '
                              f'but no open position. Cancelling all open orders as a precaution', __name__)
                open_orders = self.exchange_state.all_open_orders(symbol=symbol, position_side=PositionSide.BOTH)
                self.order_executor.cancel_orders(open_orders)
        else:
            for position_side in [PositionSide.LONG, PositionSide.SHORT]:
                if not self.exchange_state.has_open_position(symbol=symbol, position_side=position_side):
                    user_log.info(
                        f'{symbol} {position_side.name}: During deactivation, there were open orders detected '
                        f'but no open position. Cancelling all open orders as a precaution', __name__)
                    open_orders = self.exchange_state.all_open_orders(symbol=symbol, position_side=position_side)
                    self.order_executor.cancel_orders(open_orders)

    def on_initial_entry_order_filled(self,
                                      symbol: str,
                                      position: Position,
                                      symbol_information: SymbolInformation,
                                      wallet_balance: float,
                                      current_price: float):
        self.enforce_tp_grid(symbol=symbol,
                             position=position,
                             symbol_information=symbol_information,
                             current_price=current_price,
                             wiggle_config=self.wiggle_config)
        self.enforce_stoploss(symbol=symbol,
                              position=position,
                              position_side=self.position_side,
                              symbol_information=symbol_information,
                              current_price=current_price)

    def on_dca_order_filled(self,
                            symbol: str,
                            position: Position,
                            symbol_information: SymbolInformation,
                            wallet_balance: float,
                            current_price: float):
        if self.enforce_tp_grid(position=position,
                                symbol_information=symbol_information,
                                symbol=symbol,
                                current_price=current_price,
                                wiggle_config=self.wiggle_config):
            user_log.info(f'{symbol} {position.position_side.name}: Recreating TP grid because a DCA order was filled',
                          __name__)

        self.enforce_stoploss(symbol=symbol,
                              position=position,
                              position_side=self.position_side,
                              symbol_information=symbol_information,
                              current_price=current_price)

        position_side = position.position_side
        if self.wiggle_config.enabled \
                and self.wiggle_config.activate_on_stuck \
                and self.exchange_state.no_dca_orders_on_exchange(symbol=symbol, position_side=position.position_side) \
                and self.mode_processor.get_mode(symbol=symbol, position_side=position_side) == Mode.NORMAL:
            logger.info(f'{symbol} {position_side.name}: Last DCA order filled, activating mode WIGGLE because '
                        f'parameter \'activate_on_stuck\' is {self.wiggle_config.activate_on_stuck}')
            self.mode_processor.set_mode(symbol=symbol, position_side=position_side, mode=Mode.WIGGLE)
            self.enforce_wiggle(symbol=symbol,
                                position=position,
                                symbol_information=symbol_information,
                                current_price=current_price)

    def on_position_change(self,
                           symbol: str,
                           position: Position,
                           symbol_information: SymbolInformation,
                           wallet_balance: float,
                           current_price: float):
        self.enforce_tp_grid(position=position,
                             symbol_information=symbol_information,
                             symbol=symbol,
                             current_price=current_price,
                             wiggle_config=self.wiggle_config)
        self.enforce_stoploss(symbol=symbol,
                              position=position,
                              position_side=self.position_side,
                              symbol_information=symbol_information,
                              current_price=current_price)

    def on_position_closed(self,
                           symbol: str,
                           position: Position,
                           symbol_information: SymbolInformation,
                           wallet_balance: float,
                           current_price: float):
        position_side = position.position_side
        if self.cancel_orders_on_position_close is True:
            orders_to_cancel = self.exchange_state.open_dca_orders(symbol=symbol, position_side=position_side)
            entry_orders = self.exchange_state.open_entry_orders(symbol=symbol, position_side=position_side)
            orders_to_cancel.extend(entry_orders)
            tp_refill_orders = self.exchange_state.open_tp_refill_orders(symbol=symbol, position_side=position_side)
            orders_to_cancel.extend(tp_refill_orders)
            stoploss_orders = self.exchange_state.open_stoploss_orders(symbol=symbol, position_side=position_side)
            orders_to_cancel.extend(stoploss_orders)
            trailing_tp_order = self.exchange_state.open_trailing_tp_order(symbol=symbol, position_side=position_side)
            if trailing_tp_order is not None:
                orders_to_cancel.append(trailing_tp_order)
            open_wiggle_increase_order = self.exchange_state.open_wiggle_increase_order(symbol=symbol,
                                                                                        position_side=position_side)
            if open_wiggle_increase_order is not None:
                orders_to_cancel.append(open_wiggle_increase_order)

            self.order_executor.cancel_orders(orders_to_cancel)

        if self.mode_processor.get_mode(symbol=symbol, position_side=position_side) == Mode.WIGGLE and \
                self.wiggle_config.mode_after_closing is not None:
            user_log.info(f'{symbol} {position_side.name}: Setting mode from {Mode.WIGGLE.name} to '
                          f'{self.wiggle_config.mode_after_closing.name} after position was closed')
            self.mode_processor.set_mode(symbol=symbol,
                                         position_side=position_side,
                                         mode=self.wiggle_config.mode_after_closing)

        self.enforce_autoreduce(symbol=symbol,
                                position_side=self.position_side,
                                position=position,
                                symbol_information=symbol_information,
                                current_price=current_price)

    def on_tp_order_filled(self,
                           symbol: str,
                           position: Position,
                           symbol_information: SymbolInformation,
                           wallet_balance: float,
                           current_price: float):
        self.enforce_tp_refill(symbol=symbol,
                               position=position,
                               symbol_information=symbol_information,
                               current_price=current_price)

        dcas_changed = self.enforce_dca_grid(symbol=symbol,
                                             position=position,
                                             symbol_information=symbol_information,
                                             wallet_balance=wallet_balance,
                                             current_price=current_price)
        self.check_wiggle_mode_exit(symbol=symbol,
                                    position=position,
                                    wiggle_config=self.wiggle_config,
                                    dcas_changed=dcas_changed)

        self.enforce_wiggle(symbol=symbol,
                            position=position,
                            symbol_information=symbol_information,
                            current_price=current_price)

        self.enforce_autoreduce(symbol=symbol,
                                position_side=position.position_side,
                                position=position,
                                symbol_information=symbol_information,
                                current_price=current_price)

    def check_wiggle_mode_exit(self,
                               symbol: str,
                               position: Position,
                               wiggle_config: WiggleConfig,
                               dcas_changed: bool = True):
        position_side = position.position_side
        if self.exchange_state.has_open_position(symbol=symbol, position_side=position_side) \
                and dcas_changed \
                and self.exchange_state.has_open_dca_orders(symbol=symbol, position_side=position.position_side) \
                and self.mode_processor.get_mode(symbol=symbol, position_side=position_side) == Mode.WIGGLE:
            if wiggle_config.mode_after_closing is not None:
                new_mode = wiggle_config.mode_after_closing
            else:
                new_mode = Mode.NORMAL
            logger.info(f'{symbol} {position_side.name}: New DCA order freed while WIGGLE mode was active, switching '
                        f'back to mode {new_mode}')
            self.mode_processor.set_mode(symbol=symbol, position_side=position_side, mode=new_mode)

    def on_periodic_check(self,
                          symbol: str,
                          position: Position,
                          symbol_information: SymbolInformation,
                          wallet_balance: float,
                          current_price: float):
        position_side = self.position_side
        if not self.exchange_state.has_open_position(symbol=symbol, position_side=position_side):
            return

        dcas_changed = self.enforce_dca_grid(symbol=symbol,
                                             position=position,
                                             symbol_information=symbol_information,
                                             wallet_balance=wallet_balance,
                                             current_price=current_price)

        self.enforce_tp_refill(symbol=symbol,
                               position=position,
                               symbol_information=symbol_information,
                               current_price=current_price)

        if self.enforce_tp_grid(position=position,
                                symbol_information=symbol_information,
                                symbol=symbol,
                                current_price=current_price,
                                wiggle_config=self.wiggle_config):
            user_log.info(f"{symbol} {position_side.name}: Changed TP orders on the exchange on open position "
                          f"during periodic check", __name__, )

        self.enforce_stoploss(symbol=symbol,
                              position=position,
                              position_side=self.position_side,
                              symbol_information=symbol_information,
                              current_price=current_price)

        self.enforce_autoreduce(symbol=symbol,
                                position_side=position.position_side,
                                position=position,
                                symbol_information=symbol_information,
                                current_price=current_price)

        if self.exchange_state.has_open_position(symbol=symbol, position_side=position_side) \
                and not dcas_changed \
                and self.wiggle_config.enabled \
                and self.wiggle_config.activate_on_stuck \
                and self.exchange_state.no_dca_orders_on_exchange(symbol=symbol, position_side=position.position_side) \
                and self.mode_processor.get_mode(symbol=symbol, position_side=position_side) == Mode.NORMAL:
            logger.info(f'{symbol} {position_side.name}: Last DCA order filled, activating mode WIGGLE because '
                        f'parameter \'activate_on_stuck\' is {self.wiggle_config.activate_on_stuck}')
            self.mode_processor.set_mode(symbol=symbol, position_side=position_side, mode=Mode.WIGGLE)
        else:
            self.check_wiggle_mode_exit(symbol=symbol,
                                        position=position,
                                        wiggle_config=self.wiggle_config,
                                        dcas_changed=dcas_changed)

        self.enforce_wiggle(symbol=symbol,
                            position=position,
                            symbol_information=symbol_information,
                            current_price=current_price)

    def on_position_on_startup(self,
                               symbol: str,
                               position: Position,
                               symbol_information: SymbolInformation,
                               wallet_balance: float,
                               current_price: float):
        dcas_changed = self.enforce_dca_grid(symbol=symbol,
                                             position=position,
                                             symbol_information=symbol_information,
                                             wallet_balance=wallet_balance,
                                             current_price=current_price)
        self.enforce_tp_grid(position=position,
                             symbol_information=symbol_information,
                             symbol=symbol,
                             current_price=current_price,
                             wiggle_config=self.wiggle_config)
        self.enforce_stoploss(symbol=symbol,
                              position=position,
                              position_side=self.position_side,
                              symbol_information=symbol_information,
                              current_price=current_price)

        position_side = position.position_side
        if self.exchange_state.has_open_position(symbol=symbol, position_side=position_side) \
                and self.wiggle_config.enabled \
                and self.wiggle_config.activate_on_stuck \
                and dcas_changed is False \
                and self.exchange_state.no_dca_orders_on_exchange(symbol=symbol,
                                                                  position_side=position.position_side) \
                and self.mode_processor.get_mode(symbol=symbol, position_side=position_side) == Mode.NORMAL:
            logger.info(f'{symbol} {position_side.name}: Last DCA order filled, activating mode WIGGLE because '
                        f'parameter \'activate_on_stuck\' is {self.wiggle_config.activate_on_stuck}')
            self.mode_processor.set_mode(symbol=symbol, position_side=position_side, mode=Mode.WIGGLE)
        else:
            self.check_wiggle_mode_exit(symbol=symbol,
                                        position=position,
                                        wiggle_config=self.wiggle_config)

        self.enforce_wiggle(symbol=symbol,
                            position=position,
                            symbol_information=symbol_information,
                            current_price=current_price)

    def on_mode_changed(self,
                        symbol: str,
                        position: Position,
                        symbol_information: SymbolInformation,
                        wallet_balance: float,
                        current_price: float,
                        new_mode: Mode):
        if new_mode == Mode.WIGGLE:
            logger.info(f'{symbol} {self.position_side.name}: Wiggle mode activated')
        self.enforce_wiggle(symbol=symbol,
                            position=position,
                            symbol_information=symbol_information,
                            current_price=current_price)

    def on_wiggle_increase_filled(self,
                                  symbol: str,
                                  position: Position,
                                  symbol_information: SymbolInformation,
                                  wallet_balance: float,
                                  current_price: float):
        self.enforce_wiggle(symbol=symbol,
                            position=position,
                            symbol_information=symbol_information,
                            current_price=current_price)

    def on_wiggle_decrease_filled(self,
                                  symbol: str,
                                  position: Position,
                                  symbol_information: SymbolInformation,
                                  wallet_balance: float,
                                  current_price: float):
        dcas_changed = self.enforce_dca_grid(symbol=symbol,
                                             position=position,
                                             symbol_information=symbol_information,
                                             wallet_balance=wallet_balance,
                                             current_price=current_price)
        self.check_wiggle_mode_exit(symbol=symbol,
                                    position=position,
                                    wiggle_config=self.wiggle_config,
                                    dcas_changed=dcas_changed)

        self.enforce_wiggle(symbol=symbol,
                            position=position,
                            symbol_information=symbol_information,
                            current_price=current_price)

    def on_stoploss_filled(self,
                           symbol: str,
                           position: Position,
                           symbol_information: SymbolInformation,
                           wallet_balance: float,
                           current_price: float):
        if self.stoploss_config.post_stoploss_mode is not None and \
                position.no_position():
            self.mode_processor.set_mode(symbol=symbol,
                                         position_side=self.position_side,
                                         mode=self.stoploss_config.post_stoploss_mode)

    def on_reduce_order_filled(self,
                               symbol: str,
                               position: Position,
                               symbol_information: SymbolInformation,
                               wallet_balance: float,
                               current_price: float):
        self.autoreduce_plugin.reset_last_processed_income_timestamp(symbol=symbol,
                                                                     position_side=position.position_side,
                                                                     autoreduce_config=self.autoreduce_config)
        # Also resetting the last processed timestamp on the opposite position side
        self.autoreduce_plugin.reset_last_processed_income_timestamp(symbol=symbol,
                                                                     position_side=position.position_side.inverse(),
                                                                     autoreduce_config=self.autoreduce_config)

    def on_unknown_filled(self,
                          symbol: str,
                          position: Position,
                          symbol_information: SymbolInformation,
                          wallet_balance: float,
                          current_price: float):
        self.enforce_tp_grid(position=position,
                             symbol_information=symbol_information,
                             symbol=symbol,
                             current_price=current_price,
                             wiggle_config=self.wiggle_config)
        self.enforce_stoploss(symbol=symbol,
                              position=position,
                              position_side=self.position_side,
                              symbol_information=symbol_information,
                              current_price=current_price)

    def enforce_wiggle(self,
                       symbol: str,
                       position: Position,
                       symbol_information: SymbolInformation,
                       current_price: float):
        if self.mode_processor.get_mode(symbol=symbol, position_side=position.position_side) == Mode.WIGGLE:
            wallet_exposure = self.calc_wallet_exposure_ratio()
            new_wiggle_orders = self.wiggle_plugin.calculate_wiggle_orders(symbol=symbol,
                                                                           position_side=self.position_side,
                                                                           position=position,
                                                                           symbol_information=symbol_information,
                                                                           wiggle_config=self.wiggle_config,
                                                                           current_price=current_price,
                                                                           wallet_exposure=wallet_exposure)
            open_wiggle_orders = self.exchange_state.open_wiggle_orders(symbol=symbol,
                                                                        position_side=position.position_side)
            return self.enforce_grid(new_orders=new_wiggle_orders, exchange_orders=open_wiggle_orders,
                                     lowest_price_first=True)
        else:
            open_wiggle_orders = self.exchange_state.open_wiggle_orders(symbol=symbol,
                                                                        position_side=position.position_side)
            self.order_executor.cancel_orders(open_wiggle_orders)

    def enforce_dca_grid(self,
                         symbol: str,
                         position: Position,
                         symbol_information: SymbolInformation,
                         wallet_balance: float,
                         current_price: float) -> bool:
        if self.mode_processor.get_mode(symbol=symbol, position_side=position.position_side) in [Mode.PANIC,
                                                                                                 Mode.EXIT_ONLY,
                                                                                                 Mode.MANUAL]:
            return False

        if self.dca_config.enabled is False:
            return False

        position_side = position.position_side
        wallet_exposure = self.calc_wallet_exposure_ratio()
        if self.exchange_state.has_open_position(symbol=symbol, position_side=position_side) and \
                not self.dca_plugin.grid_initialized(symbol=symbol,
                                                     position_side=position_side,
                                                     dca_config=self.dca_config):
            logger.info(f'{symbol} {position_side.name}: No initialized DCA grid detected, reinitializing DCA grid '
                        f'from current price {current_price} and position price {position.entry_price}')
            self.dca_plugin.erase_grid(symbol=symbol, position_side=position_side, dca_config=self.dca_config)
            self.dca_plugin.initialize_unlimited_grid(symbol=symbol,
                                                      position_side=position_side,
                                                      symbol_information=symbol_information,
                                                      current_price=current_price,
                                                      dca_config=self.dca_config,
                                                      wallet_exposure=self.calc_wallet_exposure_ratio(),
                                                      enforce_nr_clusters=False)

        new_dca_orders = self.dca_plugin.calculate_dca_grid(symbol=symbol,
                                                            position=position,
                                                            symbol_information=symbol_information,
                                                            wallet_balance=wallet_balance,
                                                            wallet_exposure=wallet_exposure,
                                                            current_price=current_price,
                                                            dca_config=self.dca_config)

        open_dca_orders = self.exchange_state.open_dca_orders(symbol=symbol, position_side=position.position_side)
        return self.enforce_grid(new_orders=new_dca_orders, exchange_orders=open_dca_orders, lowest_price_first=False)

    def enforce_stoploss(self, symbol: str,
                         position: Position,
                         position_side: PositionSide,
                         symbol_information: SymbolInformation,
                         current_price: float,
                         custom_trigger_price: float = None):
        wallet_exposure = self.calc_wallet_exposure_ratio()
        wallet_balance = self.exchange_state.symbol_balance(symbol)
        exposed_balance = wallet_balance * wallet_exposure

        new_stoploss_orders = self.stoplosses_plugin.calculate_stoploss_orders(
            position=position,
            position_side=position_side,
            symbol_information=symbol_information,
            current_price=current_price,
            wallet_balance=wallet_balance,
            exposed_balance=exposed_balance,
            wallet_exposure=wallet_exposure,
            stoplosses_config=self.stoplosses_config,
            custom_trigger_price=custom_trigger_price)

        original_new_stoploss_orders = self.stoploss_plugin.calculate_stoploss_orders(
            position=position,
            position_side=position_side,
            symbol_information=symbol_information,
            current_price=current_price,
            wallet_balance=wallet_balance,
            exposed_balance=exposed_balance,
            wallet_exposure=wallet_exposure,
            stoploss_config=self.stoploss_config,
            custom_trigger_price=custom_trigger_price)

        new_stoploss_orders.extend(original_new_stoploss_orders)
        open_stoploss_orders = self.exchange_state.open_stoploss_orders(symbol=symbol, position_side=position_side)

        exchange_changed = self.enforce_grid(new_orders=new_stoploss_orders,
                                             exchange_orders=open_stoploss_orders,
                                             lowest_price_first=True,
                                             cancel_before_create=False)
        if exchange_changed:
            logger.info(f'{symbol} {position_side.name}: Set stoploss order(s)')
            if all([o.order_type_identifier == OrderTypeIdentifier.TRAILING_TP for o in new_stoploss_orders]):
                # cancel any open entry orders once the trailing kicked in
                self.order_executor.cancel_orders(self.exchange_state.open_entry_orders(symbol=symbol, position_side=position_side))

    def enforce_autoreduce(self,
                           symbol: str,
                           position_side: PositionSide,
                           position: Position,
                           symbol_information: SymbolInformation,
                           current_price: float):
        if self.autoreduce_config.enabled is False:
            return

        new_autoreduce_orders = self.autoreduce_plugin.calculate_autoreduce_orders(
            symbol=symbol,
            position_side=position_side,
            position=position,
            autoreduce_config=self.autoreduce_config,
            current_price=current_price,
            symbol_information=symbol_information)

        open_autoreduce_orders = self.exchange_state.open_reduce_orders(symbol=symbol, position_side=position_side)
        exchange_changed = self.enforce_grid(new_orders=new_autoreduce_orders,
                                             exchange_orders=open_autoreduce_orders,
                                             lowest_price_first=True)
        if exchange_changed:
            logger.info(f'{symbol} {position_side.name}: Set autoreduce order(s)')

    def enforce_tp_grid(self,
                        position: Position,
                        symbol_information: SymbolInformation,
                        symbol: str,
                        current_price: float,
                        wiggle_config: WiggleConfig) -> bool:
        if self.mode_processor.get_mode(symbol=symbol, position_side=self.position_side) == Mode.WIGGLE:
            if position.position_side == PositionSide.LONG \
                    and current_price > position.entry_price \
                    and wiggle_config.tp_on_profit:
                logger.info(f'{symbol} {self.position_side.name}: Placing TP orders as current price {current_price} '
                            f'is above position entry price {position.entry_price}')
            elif position.position_side == PositionSide.SHORT \
                    and current_price < position.entry_price \
                    and wiggle_config.tp_on_profit:
                logger.info(f'{symbol} {self.position_side.name}: Placing TP orders as current price {current_price} '
                            f'is below position entry price {position.entry_price}')
            else:
                logger.info(f'{symbol} {self.position_side.name}: Ignoring TP orders because mode WIGGLE is active, '
                            f'tp_on_profit = {wiggle_config.tp_on_profit}, current price = {current_price}, '
                            f'position price = {position.entry_price}')
                return False

        if position.no_position():
            return False

        # see if the grid needs to be updated
        new_tp_orders = None
        if self.hedge_config.tp_config.enabled is True \
                and self.hedge_plugin.is_hedge_applicable(symbol=symbol, position_side=self.position_side, hedge_config=self.hedge_config):
            new_tp_orders = self.tp_plugin.calculate_tp_orders(position=position,
                                                               position_side=self.position_side,
                                                               symbol_information=symbol_information,
                                                               current_price=current_price,
                                                               tp_config=self.hedge_config.tp_config)
        elif self.tp_config.enabled is True:
            new_tp_orders = self.tp_plugin.calculate_tp_orders(position=position,
                                                               position_side=self.position_side,
                                                               symbol_information=symbol_information,
                                                               current_price=current_price,
                                                               tp_config=self.tp_config)
        elif self.obtp_config.enabled is True:
            new_tp_orders = self.obtp_plugin.calculate_tp_orders(position=position,
                                                                 position_side=self.position_side,
                                                                 symbol_information=symbol_information,
                                                                 obtp_config=self.obtp_config)
        if new_tp_orders is not None:
            open_tp_orders = self.exchange_state.open_tp_orders(symbol=symbol, position_side=self.position_side)
            open_trailing_tp_orders = self.exchange_state.open_trailing_tp_orders(symbol=symbol, position_side=self.position_side)
            # when there's a trailing TP involved, create the new trailing TP before cancelling the old one
            cancel_before_create = not any([o.order_type_identifier == OrderTypeIdentifier.TRAILING_TP for o in new_tp_orders])
            open_tp_orders.extend(open_trailing_tp_orders)

            orders_changed = self.enforce_grid(new_orders=new_tp_orders,
                                               exchange_orders=open_tp_orders,
                                               lowest_price_first=True,
                                               cancel_before_create=cancel_before_create)
            if orders_changed is True:
                logger.info(f'{symbol} {self.position_side.name}: TP orders enforced, new TP orders: {new_tp_orders}, exchange_orders: {open_tp_orders}')
            return orders_changed
        else:
            logger.info(f'{symbol} {self.position_side.name}: No TP orders to be created according to plugin')

    def enforce_tp_refill(self,
                          symbol: str,
                          position: Position,
                          symbol_information: SymbolInformation,
                          current_price: float):
        if self.tp_refill_plugin.can_create_tp_refill(position=position,
                                                      symbol=symbol,
                                                      symbol_information=symbol_information,
                                                      tp_refill_config=self.tp_refill_config):
            self.tp_refill_plugin.create_tp_refill(current_price=current_price,
                                                   position=position,
                                                   symbol=symbol,
                                                   symbol_information=symbol_information)

    def shift_tp_grid_needed(self, symbol: str, position_side: PositionSide, current_price: float) -> bool:
        if not self.exchange_state.position_initialized(symbol=symbol, position_side=position_side):
            logger.info(f'{symbol} {position_side.name}: Position not initialized, not updating TP grid')
            return False
        if self.exchange_state.has_no_open_position(symbol=symbol, position_side=position_side):
            logger.debug(f'{symbol} {position_side.name}: No open position, so not refreshing TP grid')
            return False

        if self.obtp_config is not None:
            return True

        if position_side == PositionSide.LONG:
            highest = self.exchange_state.lowest_tp_price_on_exchange(symbol=symbol, position_side=PositionSide.LONG)
            if highest is None:
                logger.debug(f'{symbol} {position_side.name}: No TP orders currently set on the exchange, '
                             f'updating TP grid')
                return True
            entry_price = self.exchange_state.position(symbol=symbol, position_side=position_side).entry_price
            lower_tp_crossed_threshold = highest - (2 * (entry_price * self.tp_config.tp_interval))
            if current_price <= lower_tp_crossed_threshold:
                logger.debug(f'{symbol} {position_side.name}: Current price of {current_price} is at or below '
                             f'threshold of {lower_tp_crossed_threshold}, shifting TP grid down if needed')
                return True
            else:
                logger.debug(f'{symbol} {position_side.name}: Current price of {current_price} is above threshold '
                             f'{lower_tp_crossed_threshold}')
                return False
        elif position_side == PositionSide.SHORT:
            highest = self.exchange_state.highest_tp_price_on_exchange(symbol=symbol, position_side=PositionSide.SHORT)
            if highest is None:
                logger.debug(f'{symbol} {position_side.name}: No TP orders currently set on the exchange, '
                             f'updating TP grid')
                return True
            entry_price = self.exchange_state.position(symbol=symbol, position_side=position_side).entry_price
            higher_tp_crossed_threshold = highest + (2 * (entry_price * self.tp_config.tp_interval))
            if current_price >= higher_tp_crossed_threshold:
                logger.debug(f'{symbol} {position_side.name}: Current price of {current_price} is at or above '
                             f'threshold of {higher_tp_crossed_threshold}, shifting TP grid up if needed')
                return True
            else:
                logger.debug(f'{symbol} {position_side.name}: Current price of {current_price} is below threshold '
                             f'{higher_tp_crossed_threshold}')
                return False

    def price_outside_boundaries(self, symbol: str, position_side: PositionSide, current_price: float) -> bool:
        if self.no_entry_above is not None and current_price > self.no_entry_above:
            if self.mode_on_price_outside_boundaries is not None:
                self.mode_processor.set_mode(symbol=symbol, position_side=position_side,
                                             mode=self.mode_on_price_outside_boundaries)
                logger.info(f'{symbol} {position_side.name}: Activating mode '
                            f'{self.mode_on_price_outside_boundaries.name} because the current price {current_price} '
                            f'is above the allowed entry price boundary {self.no_entry_above}')
            else:
                logger.info(f"{symbol} {position_side.name}: The current price {current_price} is above the allowed "
                            f"entry price boundary {self.no_entry_above}")
            return True
        if self.no_entry_below is not None and current_price < self.no_entry_below:
            if self.mode_on_price_outside_boundaries is not None:
                self.mode_processor.set_mode(symbol=symbol, position_side=position_side,
                                             mode=self.mode_on_price_outside_boundaries)
                logger.info(f'{symbol} {position_side.name}: Activating mode '
                            f'{self.mode_on_price_outside_boundaries.name} because the current price {current_price} '
                            f'is below the allowed entry price boundary {self.no_entry_below}')
            else:
                logger.info(f"{symbol} {position_side.name}: The current price {current_price} is below the allowed "
                            f"entry price boundary {self.no_entry_below}")
            return True

        return False
