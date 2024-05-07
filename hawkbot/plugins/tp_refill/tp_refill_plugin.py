import logging
from dataclasses import dataclass
from typing import Dict

from hawkbot.core.model import SymbolInformation, Order, LimitOrder, OrderTypeIdentifier, Side, PositionSide, \
    OrderStatus, TimeInForce, Position
from hawkbot.logging import user_log
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.utils import calc_min_qty, round_dn, round_, round_up

logger = logging.getLogger(__name__)


@dataclass
class TpRefillConfig:
    enabled: bool = False


class TpRefillPlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange_state = None  # Injected by framework
        self.order_executor = None  # Injected by framework
        self.orderbook = None  # Injected by framework

    def parse_config(self, tp_refill_dict: Dict) -> TpRefillConfig:
        tp_refill_config = TpRefillConfig()
        if 'enabled' in tp_refill_dict:
            tp_refill_config.enabled = tp_refill_dict['enabled']

        return tp_refill_config

    def _calc_tp_refill(self,
                        position_side: PositionSide,
                        current_price: float,
                        position_size: float,
                        symbol: str,
                        symbol_information: SymbolInformation,
                        initial_entry_quantity: float) -> Order:
        if position_side == PositionSide.LONG:
            refill_price = self.orderbook.get_highest_bid(symbol=symbol, current_price=current_price)
        elif position_size == PositionSide.SHORT:
            refill_price = self.orderbook.get_lowest_ask(symbol=symbol, current_price=current_price)
        min_entry_qty = calc_min_qty(price=refill_price,
                                     inverse=False,
                                     qty_step=symbol_information.quantity_step,
                                     min_qty=symbol_information.minimum_quantity,
                                     min_cost=symbol_information.minimal_buy_cost)
        addition_to_initial_qty = round_dn(number=initial_entry_quantity - position_size,
                                           step=symbol_information.quantity_step)

        return LimitOrder(order_type_identifier=OrderTypeIdentifier.TP_REFILL,
                          symbol=symbol,
                          quantity=max(min_entry_qty, addition_to_initial_qty),
                          price=round_(refill_price, step=symbol_information.price_step),
                          side=Side.BUY if position_side == PositionSide.LONG else Side.SELL,
                          position_side=position_side,
                          reduce_only=False,
                          initial_entry=False,
                          status=OrderStatus.NEW,
                          time_in_force=TimeInForce.GOOD_TILL_CANCELED)

    def can_create_tp_refill(self,
                             position: Position,
                             symbol: str,
                             symbol_information: SymbolInformation,
                             tp_refill_config: TpRefillConfig,
                             log_negative: bool = False) -> bool:
        if tp_refill_config.enabled is False:
            return False

        position_side = position.position_side
        if self.exchange_state.has_tp_refill_order(symbol=symbol, position_side=position_side):
            logger.info(f'{symbol} {position_side.name}: There is already a TP_REFILL order on the exchange, not '
                        f'allowed to create another one')
            return False

        initial_quantity = self.exchange_state.initial_entry_quantity(symbol=symbol, position_side=position_side)
        rebuy_threshold = round_up(number=initial_quantity / 2, step=symbol_information.quantity_step)

        if position.position_size <= rebuy_threshold \
                and not self.exchange_state.has_tp_refill_order(symbol=symbol, position_side=position_side) \
                and self.exchange_state.has_open_position(symbol=symbol, position_side=position_side):
            logger.info(f'{symbol} {position_side.name}: Creating TP_REFILL order because current position size '
                        f'{position.position_size} is less than the rebuy threshold of {rebuy_threshold}, which is a '
                        f'result of the initial quantity of {initial_quantity} / 2')
            return True
        else:
            if log_negative:
                logger.info(f'{symbol} {position_side.name}: Not creating TP_REFILL order because current position '
                            f'size {position.position_size} is bigger than the rebuy threshold of {rebuy_threshold}, '
                            f'which is a result of the initial quantity of {initial_quantity} / 2')
            return False

    def create_tp_refill(self,
                         current_price: float,
                         position: Position,
                         symbol: str,
                         symbol_information: SymbolInformation):
        position_side = position.position_side
        position_size = position.position_size
        initial_entry_quantity = self.exchange_state.initial_entry_quantity(symbol=symbol,
                                                                            position_side=position_side)
        refill_order = self._calc_tp_refill(position_side=position_side,
                                            current_price=current_price,
                                            position_size=position_size,
                                            symbol=symbol,
                                            symbol_information=symbol_information,
                                            initial_entry_quantity=initial_entry_quantity)
        user_log.info(f'{symbol} {position_side.name}: Adding TP refill order with a quantity of '
                      f'{refill_order.quantity} because position size {position_size} <= {initial_entry_quantity} / 2',
                      __name__)
        self.order_executor.create_order(refill_order)
