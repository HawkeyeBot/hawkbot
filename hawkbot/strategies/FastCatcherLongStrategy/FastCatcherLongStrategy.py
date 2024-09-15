import logging

from hawkbot.core.data_classes import Trigger
from hawkbot.core.model import Position, SymbolInformation, LimitOrder, OrderStatus, PositionSide, Side, OrderTypeIdentifier, MarketOrder
from hawkbot.core.tickstore.tickstore import Tickstore
from hawkbot.core.time_provider import now_timestamp
from hawkbot.exceptions import FunctionNotImplementedException, InvalidConfigurationException
from hawkbot.strategies.abstract_base_strategy import AbstractBaseStrategy
from hawkbot.utils import fill_required_parameters, period_as_ms, calc_min_qty, fill_optional_parameters

logger = logging.getLogger(__name__)


class FastCatcherLongStrategy(AbstractBaseStrategy):
    def __init__(self):
        super().__init__()
        self.tick_store: Tickstore = None
        self.minimum_nr_ticks_threshold: int = None
        self.ticks_lookback_period: str = None
        self.price_diff_pct_threshold: float = None
        self._ticks_lookback_period_ms: int = None
        self.minimum_time_in_period_threshold: int = None
        self.signal_valid_for: str = None
        self.execute_orders_enabled: bool = None
        self.entry_order_type: str = None
        self.override_insufficient_grid_funds: bool = False
        self._signal_valid_for_ms: int = None
        self._timestamp_flag_raised: int = None

    def init_config(self):
        super().init_config()
        fill_required_parameters(target=self,
                                 config=self.strategy_config,
                                 required_parameters=['minimum_nr_ticks_threshold',
                                                      'price_diff_pct_threshold',
                                                      'ticks_lookback_period',
                                                      'minimum_time_in_period_threshold',
                                                      'signal_valid_for',
                                                      'execute_orders_enabled',
                                                      'entry_order_type'])
        if self.entry_order_type not in ['MARKET', 'LIMIT']:
            raise InvalidConfigurationException('The parameter \'entry_order_type\' must be either \'MARKET\' or \'LIMIIT\'')
        self._ticks_lookback_period_ms = period_as_ms(self.ticks_lookback_period)
        self._signal_valid_for_ms = period_as_ms(self.signal_valid_for)

        fill_optional_parameters(target=self,
                                 config=self.strategy_config,
                                 optional_parameters=['override_insufficient_grid_funds'])

    def on_pulse(self,
                 symbol: str,
                 position: Position,
                 symbol_information: SymbolInformation,
                 wallet_balance: float,
                 current_price: float):
        curr_ts = now_timestamp()
        try:
            ticks = self.tick_store.get_ticks(symbol=self.symbol, start_timestamp=curr_ts - self._ticks_lookback_period_ms, end_timestamp=curr_ts)
        except FunctionNotImplementedException:
            logger.info("bybit fetch ticks isn't available, so at first it can fail which is ok")
            return

        if self._timestamp_flag_raised is None:
            if position.no_position() and self.entry_allowed(ticks):
                self._timestamp_flag_raised = now_timestamp()
                self.place_grid(symbol=symbol,
                                symbol_information=symbol_information,
                                current_price=current_price,
                                wallet_balance=wallet_balance)
        else:
            if curr_ts - self._timestamp_flag_raised > self._signal_valid_for_ms:
                # cancel signal
                self._signal_valid_for_ms = None
                self.dca_plugin.erase_grid(symbol=self.symbol, position_side=self.position_side, dca_config=self.dca_config)

    def place_grid(self,
                   symbol: str,
                   symbol_information: SymbolInformation,
                   current_price: float,
                   wallet_balance: float):
        self.dca_plugin.initialize_unlimited_grid(symbol=symbol,
                                                  position_side=self.position_side,
                                                  symbol_information=symbol_information,
                                                  current_price=current_price,
                                                  dca_config=self.dca_config,
                                                  wallet_exposure=self.calc_wallet_exposure_ratio())
        all_prices = self.gridstorage_plugin.get_prices(symbol=symbol, position_side=self.position_side)
        allowed_prices = [price for price in all_prices if price < current_price]
        allowed_prices.sort(reverse=True)
        logger.info(f'{symbol} {self.position_side.name}: Selected price below current price {current_price}: '
                    f'{allowed_prices}')
        dca_quantities = self.gridstorage_plugin.get_quantities(symbol=symbol, position_side=self.position_side)

        wallet_exposure = self.calc_wallet_exposure_ratio()
        exposed_balance = wallet_balance * wallet_exposure

        price_index = 0
        limit_orders = []
        orders_cost = 0
        for i, dca_quantity_record in enumerate(dca_quantities):
            if i >= len(allowed_prices):
                # no more prices available, break it off
                break
            dca_price = allowed_prices[price_index]
            dca_quantity = dca_quantity_record.quantity
            min_entry_qty = calc_min_qty(price=dca_price,
                                         inverse=False,
                                         qty_step=symbol_information.quantity_step,
                                         min_qty=symbol_information.minimum_quantity,
                                         min_cost=symbol_information.minimal_buy_cost)
            if dca_quantity < min_entry_qty:
                if not self.override_insufficient_grid_funds:
                    raw_quantity = dca_quantity_record.raw_quantity
                    required_balance = exposed_balance * (min_entry_qty / raw_quantity)
                    logger.warning(f'{symbol} {self.position_side.name}: The entry at price {dca_price} with quantity '
                                   f'{dca_quantity} ({raw_quantity}) does not meet minimum quantity {min_entry_qty}. The quantities are '
                                   f'based on exposed balance {exposed_balance}. In order to make the bot enter, either '
                                   f'1) increase the exposed balance to (roughly) a minimum of {required_balance} by having a bigger wallet_exposure_ratio, or adding equity if '
                                   f'you want to maintain the same settings, 2) reduce the number of clusters, 3) reduce the DCA strength (ratio power, quantity multiplier or '
                                   f'desired position distance), 4) force the bot to run with an incomplete grid by setting \'override_insufficient_grid_funds\' to true')
                    return

            if self.entry_order_type == 'MARKET' and price_index == 0:
                order = MarketOrder(order_type_identifier=OrderTypeIdentifier.INITIAL_ENTRY,
                                    symbol=symbol,
                                    quantity=max(min_entry_qty, dca_quantity),
                                    side=Side.BUY,
                                    position_side=PositionSide.LONG,
                                    initial_entry=True,
                                    status=OrderStatus.NEW)
                price_index += 1
            else:
                order = LimitOrder(
                    order_type_identifier=OrderTypeIdentifier.INITIAL_ENTRY if price_index == 0 else OrderTypeIdentifier.DCA,
                    symbol=symbol_information.symbol,
                    quantity=dca_quantity,
                    side=Side.BUY,
                    position_side=PositionSide.LONG,
                    initial_entry=False,
                    price=dca_price)
                price_index += 1
            if orders_cost + order.cost > exposed_balance:
                break
            orders_cost += order.cost
            limit_orders.append(order)

        if len(limit_orders) == 0:
            return

        if self.execute_orders_enabled is True:
            existing_orders = self.exchange_state.open_entry_orders(symbol=symbol, position_side=self.position_side)
            self.enforce_grid(new_orders=limit_orders, exchange_orders=existing_orders, lowest_price_first=False)
            logger.info(f'{symbol} {self.position_side.name}: Finished placing orders')
        elif len(limit_orders) > 0:
            logger.info(f'{symbol} {self.position_side.name}: Order execution is explicitly disabled in the config')

    def on_position_closed(self,
                           symbol: str,
                           position: Position,
                           symbol_information: SymbolInformation,
                           wallet_balance: float,
                           current_price: float):
        super().on_position_closed(symbol=symbol,
                                   position=position,
                                   symbol_information=symbol_information,
                                   wallet_balance=wallet_balance,
                                   current_price=current_price)
        self._signal_valid_for_ms = None
        self.dca_plugin.erase_grid(symbol=self.symbol, position_side=self.position_side, dca_config=self.dca_config)

    def entry_allowed(self, ticks) -> bool:
        if len(ticks) > 1:
            oldest_tick_timestamp = min([t.timestamp for t in ticks])
            youngest_tick_timestamp = max([t.timestamp for t in ticks])
            diff = youngest_tick_timestamp - oldest_tick_timestamp
            oldest_price = [t.price for t in ticks if t.timestamp == oldest_tick_timestamp][0]
            youngest_price = [t.price for t in ticks if t.timestamp == youngest_tick_timestamp][0]
            price_diff = youngest_price - oldest_price
            price_diff_pct = price_diff / (oldest_price / 100)
            if diff > 0 and oldest_price != youngest_price:
                if diff >= self.minimum_time_in_period_threshold and len(ticks) > self.minimum_nr_ticks_threshold and self._price_diff_past_threshold(price_diff_pct):
                    logger.info(
                        f"ENTER: time diff = {diff}, "
                        f"# ticks = {len(ticks)}, "
                        f"oldest price = {oldest_price}, "
                        f"youngest price = {youngest_price}, "
                        f"price diff pct = {price_diff_pct:.6f}")
                    return True
        return False

    def _price_diff_past_threshold(self, price_diff_pct: float) -> bool:
        if self.price_diff_pct_threshold > 0:
            return price_diff_pct >= self.price_diff_pct_threshold
        else:
            return price_diff_pct <= self.price_diff_pct_threshold

    def log_trigger(self, trigger: Trigger) -> bool:
        return trigger in []
