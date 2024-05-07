import logging

from hawkbot.core.data_classes import OrderStatus, SymbolInformation, Side, PositionSide, OrderTypeIdentifier, Position
from hawkbot.core.model import MarketOrder
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.logging import user_log
from hawkbot.strategies.abstract_base_strategy import AbstractBaseStrategy
from hawkbot.utils import round_, cost_to_quantity, calc_min_qty

logger = logging.getLogger(__name__)


class BasicShortStrategy(AbstractBaseStrategy):
    def __init__(self):
        super().__init__()
        self.initial_cost: float = None

    def init_config(self):
        super().init_config()

        if 'initial_cost' in self.strategy_config:
            self.initial_cost = self.strategy_config['initial_cost']
        else:
            raise InvalidConfigurationException(f'{self.symbol} {self.position_side.name}: The field \'initial_cost\' '
                                                f'is not defined in the config')

    def on_position_on_startup(
            self,
            symbol: str,
            position: Position,
            symbol_information: SymbolInformation,
            wallet_balance: float,
            current_price: float,
    ):
        position_side = position.position_side
        wallet_exposure = self.calc_wallet_exposure_ratio()
        if self.exchange_state.has_open_dca_orders(symbol=symbol, position_side=position_side):
            if self.dca_config.check_dca_against_wallet:
                initial_cost = wallet_balance * wallet_exposure * self.initial_cost
                initial_entry_price = self.exchange_state.initial_entry_price(symbol=symbol,
                                                                              position_side=position_side)
                min_entry_qty = calc_min_qty(price=initial_entry_price,
                                             inverse=False,
                                             qty_step=symbol_information.quantity_step,
                                             min_qty=symbol_information.minimum_quantity,
                                             min_cost=symbol_information.minimal_buy_cost)
                max_entry_qty = round_(cost_to_quantity(cost=initial_cost, price=initial_entry_price, inverse=False),
                                       step=symbol_information.quantity_step)
                initial_entry_quantity_on_new_cost = max(min_entry_qty, max_entry_qty)

                current_initial_entry_quantity = self.exchange_state. \
                    initial_entry_quantity(symbol=symbol, position_side=position_side)
                if self.exchange_state.initial_entry_quantity(symbol=symbol, position_side=position_side) \
                        != initial_entry_quantity_on_new_cost:
                    logger.info(f'A position is open when starting, but the set initial cost ({initial_cost}) results '
                                f'in a different initial entry quantity of {initial_entry_quantity_on_new_cost} than '
                                f'the original initial entry quantity of {current_initial_entry_quantity}. '
                                f'Recreating the DCA grid accordingly.')
                    self.dca_plugin.initialize_unlimited_grid(symbol=symbol,
                                                              position_side=position_side,
                                                              symbol_information=symbol_information,
                                                              current_price=initial_entry_price,
                                                              dca_config=self.dca_config,
                                                              initial_cost=self.initial_cost,
                                                              wallet_exposure=wallet_exposure)

        self.enforce_dca_grid(symbol=symbol,
                              position=position,
                              symbol_information=symbol_information,
                              wallet_balance=wallet_balance,
                              current_price=current_price)

        self.enforce_tp_refill(symbol=symbol,
                               position=position,
                               symbol_information=symbol_information,
                               current_price=current_price)

        if not self.exchange_state.has_open_tp_orders(symbol=symbol, position_side=position_side):
            if self.enforce_tp_grid(position=position,
                                    symbol_information=symbol_information,
                                    symbol=symbol,
                                    current_price=current_price,
                                    wiggle_config=self.wiggle_config):
                user_log.info(
                    f"{symbol} {position_side.name}: No TP orders on the exchange on open position at startup, "
                    f"creating TP orders", __name__)

    def on_no_open_position(self,
                            symbol: str,
                            position: Position,
                            symbol_information: SymbolInformation,
                            wallet_balance: float,
                            current_price: float):
        position_side = position.position_side
        if self.exchange_state.has_any_open_order(symbol=symbol, position_side=position_side):
            user_log.info(f'{symbol} {position_side.name}: Found open orders while no position is open, cancelling '
                          f'all open orders: '
                          f'{self.exchange_state.all_open_orders(symbol=symbol, position_side=position_side)}',
                          __name__)
            [self.order_executor.cancel_order(order)
             for order in self.exchange_state.all_open_orders(symbol=symbol, position_side=position_side)]
        self.gridstorage_plugin.reset(symbol=symbol, position_side=position_side)

        if self.price_outside_boundaries(symbol=symbol, position_side=position_side, current_price=current_price):
            return

        if not self.specified_resistances_available_for_all_timeframes(symbol=symbol,
                                                                       position_side=position_side,
                                                                       current_price=current_price):
            if self.dca_config.override_insufficient_levels_available:
                user_log.info(f"{symbol} {position_side.name}: Entering a position while there are insufficient "
                              f"resistance prices available to meet the configuration's minimum number of supports, "
                              f"but the configuration option 'override_insufficient_resistances_available' is set "
                              f"to true", __name__)
            else:
                return

        wallet_exposure = self.calc_wallet_exposure_ratio()
        entry_order = self.create_initial_entry_order(current_price=current_price,
                                                      symbol=symbol,
                                                      symbol_information=symbol_information,
                                                      wallet_balance=wallet_balance,
                                                      wallet_exposure=wallet_exposure)
        self.order_executor.create_order(entry_order)
        user_log.info(f'{symbol} {position_side.name}: No position currently open, creating new entry order with '
                      f'quantity {entry_order.quantity} based on a wallet exposure of {wallet_exposure} '
                      f'at a wallet balance of {wallet_balance:.2f}', __name__)

    def specified_resistances_available_for_all_timeframes(self,
                                                           symbol: str,
                                                           position_side: PositionSide,
                                                           current_price: float):
        # check the minimum number of supports specified
        minimum_number_resistances = self.minimum_number_of_available_dcas

        # calculate all the support prices
        number_available_resistance_prices = len(
            self.dca_plugin.calculate_resistance_prices(symbol=symbol,
                                                        position_side=position_side,
                                                        minimum_price=current_price,
                                                        dca_config=self.dca_config))

        if number_available_resistance_prices < minimum_number_resistances:
            if not self.dca_config.override_insufficient_levels_available:
                logger.warning(f"{symbol} {position_side.name}: Based on the history of {symbol}, there are "
                               f"{number_available_resistance_prices} resistances, which is less than the minimum "
                               f"number of resistances ({minimum_number_resistances}) specified in the config. If you "
                               f"want the bot to enter a position despite this warning, please set the field "
                               f"'override_insufficient_levels_available' to true in the configuration file, or "
                               f"specify a different minimum required number of supports using "
                               f"'minimum_number_of_available_dcas'.")
            return False
        else:
            logger.debug(f'{symbol} {position_side.name}: Based on the history, there are '
                         f'{number_available_resistance_prices}, which is at least the minimum number of supports '
                         f'({minimum_number_resistances}) specified in the config')
            return True

    def create_initial_entry_order(self,
                                   current_price: float,
                                   symbol: str,
                                   symbol_information: SymbolInformation,
                                   wallet_balance: float,
                                   wallet_exposure: float):
        lowest_ask = self.orderbook.get_lowest_ask(symbol=symbol, current_price=current_price)
        min_entry_qty = calc_min_qty(price=lowest_ask,
                                     inverse=False,
                                     qty_step=symbol_information.quantity_step,
                                     min_qty=symbol_information.minimum_quantity,
                                     min_cost=symbol_information.minimal_buy_cost)
        max_entry_qty = round_(cost_to_quantity(cost=wallet_balance * wallet_exposure * self.initial_cost,
                                                price=lowest_ask, inverse=False),
                               step=symbol_information.quantity_step)
        entry_order = MarketOrder(order_type_identifier=OrderTypeIdentifier.INITIAL_ENTRY,
                                  symbol=symbol,
                                  quantity=max(min_entry_qty, max_entry_qty),
                                  side=Side.SELL,
                                  position_side=PositionSide.SHORT,
                                  initial_entry=True,
                                  status=OrderStatus.NEW)
        return entry_order

    def on_initial_entry_order_filled(self,
                                      symbol: str,
                                      position: Position,
                                      symbol_information: SymbolInformation,
                                      wallet_balance: float,
                                      current_price: float):
        # Create the DCA orders first to prevent the TP order coming in first before all the
        # DCA orders are in the exchange_state
        position_side = position.position_side
        self.dca_plugin.initialize_unlimited_grid(symbol=symbol,
                                                  position_side=position_side,
                                                  symbol_information=symbol_information,
                                                  current_price=current_price,
                                                  dca_config=self.dca_config,
                                                  initial_cost=self.initial_cost,
                                                  wallet_exposure=self.calc_wallet_exposure_ratio())
        if self.enforce_dca_grid(symbol=symbol,
                                 position=position,
                                 symbol_information=symbol_information,
                                 wallet_balance=wallet_balance,
                                 current_price=current_price):
            user_log.info(f'{symbol} {position_side.name}: Initial order filled, created DCA orders')

        if self.enforce_tp_grid(position=position,
                                symbol_information=symbol_information,
                                symbol=symbol,
                                current_price=current_price,
                                wiggle_config=self.wiggle_config):
            user_log.info(f'{symbol} {position_side.name}: Initial order filled, created TP orders', __name__)

    def on_tp_refill_order_filled(self,
                                  symbol: str,
                                  position: Position,
                                  symbol_information: SymbolInformation,
                                  wallet_balance: float,
                                  current_price: float):
        position_side = position.position_side

        # check if used entry price is less than the current position price (TP_REFILL will trigger this)
        used_root_price = self.gridstorage_plugin.get_root_price(symbol=symbol, position_side=position_side)
        rounded_root_price = round_(used_root_price, symbol_information.price_step)

        current_position_price = self.exchange_state.position(symbol=symbol,
                                                              position_side=position_side).entry_price
        rounded_position_price = round_(current_position_price, symbol_information.price_step)
        if used_root_price is not None and rounded_position_price < rounded_root_price:
            user_log.info(f"{symbol} {position_side.name}: Updating DCA grid because the current position price "
                          f"{rounded_position_price} is below than the used root price of {rounded_root_price}")
            self.dca_plugin.initialize_unlimited_grid(symbol=symbol,
                                                      position_side=position_side,
                                                      symbol_information=symbol_information,
                                                      current_price=current_position_price,
                                                      dca_config=self.dca_config,
                                                      initial_cost=self.initial_cost,
                                                      wallet_exposure=self.calc_wallet_exposure_ratio(),
                                                      reset_quantities=False)

        self.enforce_dca_grid(symbol=symbol,
                              position=position,
                              symbol_information=symbol_information,
                              wallet_balance=wallet_balance,
                              current_price=current_price)

        if self.enforce_tp_grid(position=position,
                                symbol_information=symbol_information,
                                symbol=symbol,
                                current_price=current_price,
                                wiggle_config=self.wiggle_config):
            user_log.info(f"{symbol} {position_side.name}: Recreating TP grid because TP_REFILL order was filled",
                          __name__)
