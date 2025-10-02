import logging
from typing import List

from hawkbot.core.data_classes import Trigger
from hawkbot.core.model import Position, SymbolInformation, LimitOrder, OrderTypeIdentifier, Side, PositionSide, Order
from hawkbot.strategies.abstract_base_strategy import AbstractBaseStrategy
from hawkbot.utils import round_, round_dn

logger = logging.getLogger(__name__)


class NewMultiPositionLongStrategy(AbstractBaseStrategy):
    def __init__(self):
        super().__init__()
        self.cancel_orders_on_position_close = False
        self.cancel_no_position_open_orders_on_shutdown = False

        self.step_size = 0.00025

    def on_new_filled_orders(self,
                             symbol: str,
                             symbol_information: SymbolInformation,
                             new_filled_orders: List[Order]):
        logger.info(f"{symbol}: New orders filled: {new_filled_orders}")
        orders_to_add = []
        for filled_order in [o for o in new_filled_orders if o.position_side == self.position_side]:
            if filled_order.side == self.position_side.increase_side():
                filled_price = filled_order.price
                price = round_(number=filled_price + self.step_size, step=symbol_information.price_step) # for long, TP price is higher
                order = LimitOrder(
                    order_type_identifier=OrderTypeIdentifier.TP,
                    symbol=symbol_information.symbol,
                    quantity=filled_order.quantity,
                    side=self.position_side.decrease_side(),
                    position_side=self.position_side,
                    price=price,
                    reduce_only=True)
                orders_to_add.append(order)
            else:
                filled_price = filled_order.price
                price = round_(number=filled_price - self.step_size, step=symbol_information.price_step) # for LONG, DCA price is lower
                order = LimitOrder(
                    order_type_identifier=OrderTypeIdentifier.DCA,
                    symbol=symbol_information.symbol,
                    quantity=filled_order.quantity,
                    side=self.position_side.increase_side(),
                    position_side=self.position_side,
                    price=price)
                orders_to_add.append(order)

        logger.info(f'{symbol} {self.position_side.name}: Creating orders {orders_to_add}')
        self.order_executor.create_orders(orders_to_add)

    def on_periodic_check(self,
                          symbol: str,
                          position: Position,
                          symbol_information: SymbolInformation,
                          wallet_balance: float,
                          current_price: float):

        # check if a new entry order needs to be placed

        open_entry_orders = self.exchange_state.open_entry_orders(symbol=symbol, position_side=self.position_side)
        xrp_balance = self.exchange_state.asset_balance('XRP')
        usdt_balance = self.exchange_state.asset_balance('USDT')
        # logger.info(f'{symbol} LONG: XRP balance = {xrp_balance}, USDT balance = {usdt_balance}')
        # if xrp_balance < 1:
        #     # place 1 entry order when there's no order at all on the exchange
        #     # entry price = round current_price down to closest step size
        #     entry_price = round_dn(current_price, self.step_size)
        #
        #     entry_order = LimitOrder(
        #         order_type_identifier=OrderTypeIdentifier.ENTRY,
        #         symbol=symbol_information.symbol,
        #         quantity=1,
        #         side=Side.BUY,
        #         position_side=PositionSide.LONG,
        #         initial_entry=False,
        #         price=entry_price)
        #     self.enforce_grid(new_orders=[entry_order], exchange_orders=open_entry_orders)
        # else:
        #     # we've got at least 1 order to be present, now we need to
        #     pass

    def on_entry_order_filled(self,
                              symbol: str,
                              position: Position,
                              symbol_information: SymbolInformation,
                              wallet_balance: float,
                              current_price: float):
        logger.info(f'{symbol} LONG: Entry order filled, placing backing TP order')
        # place TP order against it
        last_filled_price = self.exchange_state.last_filled_price(symbol=symbol,
                                                                  position_side=PositionSide.LONG,
                                                                  order_type_identifiers=OrderTypeIdentifier.ENTRY)
        # place TP order at the next interval up from the filled price
        tp_price = last_filled_price + self.step_size
        order = LimitOrder(
            order_type_identifier=OrderTypeIdentifier.TP,
            symbol=symbol_information.symbol,
            quantity=1,
            side=Side.SELL,
            position_side=PositionSide.LONG,
            initial_entry=False,
            price=tp_price,
            reduce_only=True)

        # self.order_executor.create_orders([order])
        logger.info(f'{symbol} LONG: Placed TP order {order.quantity}@{order.price}')

    def log_trigger(self, trigger: Trigger) -> bool:
        return trigger not in [Trigger.PULSE, Trigger.WALLET_CHANGED, Trigger.PERIODIC_CHECK]
