import logging
from typing import List

from hawkbot.core.data_classes import Trigger
from hawkbot.core.model import Position, SymbolInformation, LimitOrder, OrderTypeIdentifier, OrderStatus, Order
from hawkbot.core.time_provider import now_timestamp
from hawkbot.exchange.exchange import Exchange
from hawkbot.strategies.abstract_base_strategy import AbstractBaseStrategy
from hawkbot.utils import round_, calc_min_qty, fill_required_parameters

logger = logging.getLogger(__name__)


class NewMultiPositionLongStrategy(AbstractBaseStrategy):
    exchange: Exchange = None

    def __init__(self):
        super().__init__()
        self.cancel_orders_on_position_close = False
        self.cancel_no_position_open_orders_on_shutdown = False

        self.order_distance: float = None
        self.nr_buy_orders_on_exchange: int = None
        self.nr_sell_orders_on_exchange: int = None

    def init_config(self):
        super().init_config()
        required_parameters = ['order_distance', 'nr_buy_orders_on_exchange', 'nr_sell_orders_on_exchange']
        fill_required_parameters(target=self, config=self.strategy_config, required_parameters=required_parameters)

    def on_new_filled_orders(self,
                             symbol: str,
                             symbol_information: SymbolInformation,
                             new_filled_orders: List[Order]):
        logger.info(f"{symbol}: New orders filled: {new_filled_orders}")
        orders_to_add = []
        for filled_order in [o for o in new_filled_orders if o.position_side == self.position_side]:
            if filled_order.side == self.position_side.increase_side():
                filled_price = filled_order.price
                price = round_(number=filled_price * (1 + self.order_distance), step=symbol_information.price_step) # for long, TP price is higher
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
                # TODO: check if current price already passed it by now
                filled_price = filled_order.price
                buy_price = filled_price / (1 + self.order_distance)
                price = round_(number=buy_price, step=symbol_information.price_step) # for LONG, DCA price is lower
                quantity = calc_min_qty(price=price,
                                        inverse=False,
                                        qty_step=symbol_information.quantity_step,
                                        min_qty=symbol_information.minimum_quantity,
                                        min_cost=symbol_information.minimal_buy_cost)
                # TODO: check if the wallet exposure has enough funds available to place a new order
                price = min(price, self.exchange_state.get_last_price(symbol) - symbol_information.price_step)

                order = LimitOrder(
                    order_type_identifier=OrderTypeIdentifier.DCA,
                    symbol=symbol_information.symbol,
                    quantity=quantity,
                    side=self.position_side.increase_side(),
                    position_side=self.position_side,
                    price=price)
                orders_to_add.append(order)


        # TODO: check if we need to add update the orders at the top or bottom

        logger.info(f'{symbol} {self.position_side.name}: Creating orders {orders_to_add}')
        self.order_executor.create_orders(orders_to_add)

    def on_periodic_check(self,
                          symbol: str,
                          position: Position,
                          symbol_information: SymbolInformation,
                          wallet_balance: float,
                          current_price: float):
        open_orders = self.exchange_state.all_open_orders(symbol=symbol, position_side=self.position_side)
        latest_filled_orders = self.order_executor.exchange.fetch_orders(symbol=symbol, end_time=now_timestamp(), status=OrderStatus.FILLED)
        last_timestamp = max([o.event_time for o in latest_filled_orders])
        last_filled_order = [o for o in latest_filled_orders if o.event_time == last_timestamp][0]
        logger.info(f'{symbol} {self.position_side.name}: Last filled order price = {last_filled_order.price}')

        new_orders = []
        next_buy_price = last_filled_order.price
        # last filled order was a buy, so the first next buy order should be a step below last filled price
        for i in range(1, self.nr_buy_orders_on_exchange + 1):
            next_buy_price = next_buy_price / (1 + self.order_distance)
            next_buy_price = round_(number=next_buy_price, step=symbol_information.price_step)
            quantity = calc_min_qty(price=next_buy_price,
                                    inverse=False,
                                    qty_step=symbol_information.quantity_step,
                                    min_qty=symbol_information.minimum_quantity,
                                    min_cost=symbol_information.minimal_buy_cost)
            # final_buy_price = min(next_buy_price, self.exchange_state.get_last_price(symbol) - symbol_information.price_step)
            # TODO: what if the price has already passed the point where the order should be placed?
                # place the order at the current price - 1
                # aka min(current price -1, intended price)
            # TODO: check if the wallet exposure has enough funds available to place a new order
            new_orders.append(LimitOrder(
                order_type_identifier=OrderTypeIdentifier.DCA,
                symbol=symbol_information.symbol,
                quantity=quantity,
                side=self.position_side.increase_side(),
                position_side=self.position_side,
                price=float(f'{next_buy_price:f}')))
            logger.debug(f'{symbol} {self.position_side.name}: Should place BUY order {quantity}@{next_buy_price:f}')

        # last filled order was a buy, so the first next sell order should be a step above last filled price
        next_sell_price = last_filled_order.price
        for i in range(1, self.nr_sell_orders_on_exchange + 1):
            next_sell_price = next_sell_price * (1 + self.order_distance)
            next_sell_price = round_(number=next_sell_price, step=symbol_information.price_step)
            corresponding_buy_price = (next_sell_price / (1 + self.order_distance)) / (1 + self.order_distance)
            corresponding_buy_price = round_(number=corresponding_buy_price, step=symbol_information.price_step)
            quantity = calc_min_qty(price=corresponding_buy_price,
                                                      inverse=False,
                                                      qty_step=symbol_information.quantity_step,
                                                      min_qty=symbol_information.minimum_quantity,
                                                      min_cost=symbol_information.minimal_buy_cost)
            new_orders.append(LimitOrder(
                order_type_identifier=OrderTypeIdentifier.TP,
                symbol=symbol_information.symbol,
                quantity=quantity,
                side=self.position_side.decrease_side(),
                position_side=self.position_side,
                price=float(f'{next_sell_price:f}'),
                reduce_only=True))
            logger.debug(f'{symbol} {self.position_side.name}: Should place SELL order {quantity}@{next_sell_price:f}')

        self.enforce_grid(new_orders=new_orders, exchange_orders=open_orders)

    def log_trigger(self, trigger: Trigger) -> bool:
        return trigger not in [Trigger.PULSE, Trigger.WALLET_CHANGED, Trigger.PERIODIC_CHECK]
