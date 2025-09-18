import logging

from hawkbot.core.data_classes import Trigger
from hawkbot.core.model import Position, SymbolInformation, LimitOrder, OrderTypeIdentifier, Side, PositionSide
from hawkbot.strategies.abstract_base_strategy import AbstractBaseStrategy

logger = logging.getLogger(__name__)


class MultiPositionLongStrategy(AbstractBaseStrategy):
    def __init__(self):
        super().__init__()
        self.cancel_orders_on_position_close = False
        self.cancel_no_position_open_orders_on_shutdown = False

        self.starting_price: float = 0.9950
        self.range_end_price: float = 1.0000 #0.9970
        self.single_entry_size: int = 2
        self.fee = 0.0001

    def on_periodic_check(self,
                          symbol: str,
                          position: Position,
                          symbol_information: SymbolInformation,
                          wallet_balance: float,
                          current_price: float):
        super().on_periodic_check(symbol=symbol,
                                  position=position,
                                  symbol_information=symbol_information,
                                  wallet_balance=wallet_balance,
                                  current_price=current_price)

        ob = self.order_executor.exchange.fetch_current_orderbook(symbol)
        best_ask = ob[0].asks[0][0]
        best_bid = ob[0].bids[0][0]
        logger.info(f'{symbol}: Best ask = {best_ask}, best bid = {best_bid}')

        if best_bid > self.starting_price:
            range_end_price = min(best_ask - symbol_information.price_step, self.range_end_price)
            nr_of_steps = int((range_end_price - self.starting_price) / symbol_information.price_step)
            logger.debug(f'{symbol} {self.position_side.name}: Nr of orders to place: {nr_of_steps + 1}')
            orders = []
            # for step in range(30):
            for step in range(nr_of_steps + 1):
                order_price = float(f'{self.starting_price + (step * symbol_information.price_step):.5f}')
                logger.debug(f'{symbol} {self.position_side.name}: Place order at {order_price}')
                order = LimitOrder(
                        order_type_identifier=OrderTypeIdentifier.ENTRY,
                        symbol=symbol_information.symbol,
                        quantity=self.single_entry_size,
                        side=Side.BUY,
                        position_side=PositionSide.LONG,
                        initial_entry=False,
                        price=order_price)
                orders.append(order)


            current_open_orders = self.exchange_state.open_entry_orders(symbol=symbol, position_side=self.position_side)
            if len(current_open_orders) != len(orders):
                new_orders = [o for o in orders if o not in current_open_orders]
                logger.info(f'{symbol}: Placing entry orders because best bid {best_bid} > {self.starting_price}')

            self.enforce_grid(new_orders=orders, exchange_orders=current_open_orders)

        self.place_tp_grid(best_bid=best_bid, symbol=symbol, symbol_information=symbol_information, best_ask=best_ask)

        def place_tp_grid(self, best_bid: float, symbol: str, symbol_information: SymbolInformation, best_ask: float):
            start_tp_from = best_ask
            desired_tp_orders = []
            # determine the nr of contracts
            # get the asset size
            quote_asset_size = self.exchange_state.free_asset_balance('USDC')
            if quote_asset_size < self.single_entry_size:
                logger.debug(f'{self.symbol}: Quote asset size {quote_asset_size} < {self.single_entry_size}, not placing new TP orders')
                return

            # for the 'free' usdc, start placing orders from the best ask upwards
            # for any remaining order, let it stay where it is

            nr_tp_orders = int(quote_asset_size / self.single_entry_size)
            for step in range(0, nr_tp_orders):
                order_price = float(f'{start_tp_from + (step * symbol_information.price_step)}')
                order_price = max(order_price, best_bid + symbol_information.price_step)

                order = LimitOrder(
                    order_type_identifier=OrderTypeIdentifier.TP,
                    symbol=symbol_information.symbol,
                    quantity=self.single_entry_size,
                    side=Side.SELL,
                    position_side=PositionSide.LONG,
                    initial_entry=False,
                    price=order_price,
                    reduce_only=True)
                desired_tp_orders.append(order)
                logger.info(f'{self.symbol}: Placing TP order {order}')

            self.order_executor.create_orders(desired_tp_orders)
            # current_open_tp_orders = self.exchange_state.open_tp_orders(symbol=symbol, position_side=self.position_side)
            # self.enforce_grid(new_orders=desired_tp_orders, exchange_orders=current_open_tp_orders)

    def log_trigger(self, trigger: Trigger) -> bool:
        return trigger not in [Trigger.PERIODIC_CHECK, Trigger.PULSE, Trigger.WALLET_CHANGED]
