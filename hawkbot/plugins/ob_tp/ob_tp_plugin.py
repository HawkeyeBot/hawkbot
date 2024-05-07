import logging
from dataclasses import dataclass, field
from typing import List, Dict

from hawkbot.core.data_classes import ExchangeState
from hawkbot.core.model import Position, SymbolInformation, Order, LimitOrder, OrderTypeIdentifier, Side, PositionSide, \
    OrderStatus, TimeInForce
from hawkbot.core.orderbook.orderbook import OrderBook
from hawkbot.exceptions import UnsupportedParameterException
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.utils import round_, round_dn, calc_min_qty, round_up, parse_histogram

logger = logging.getLogger(__name__)


@dataclass
class ObTpConfig:
    enabled: bool = field(default_factory=lambda: True)
    minimum_tp_distance: float = field(default_factory=lambda: 0.0)
    number_tp_orders: int = field(default_factory=lambda: None)
    depth: int = field(default_factory=lambda: None)
    nr_bins: int = field(default_factory=lambda: None)
    order_repost_beyond_threshold: float = field(default_factory=lambda: 0.0)


class ObTpPlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.orderbook: OrderBook = None  # Injected by framework
        self.exchange_state: ExchangeState = None  # Injected by framework

    def parse_config(self, obtp_dict: Dict) -> ObTpConfig:
        obtp_config = ObTpConfig()
        if len(obtp_dict.keys()) == 0:
            obtp_config.enabled = False
            return obtp_config

        if "enabled" in obtp_dict:
            obtp_config.enabled = obtp_dict["enabled"]
        if "minimum_tp_distance" in obtp_dict:
            obtp_config.minimum_tp_distance = obtp_dict["minimum_tp_distance"]
        if "number_tp_orders" in obtp_dict:
            obtp_config.number_tp_orders = obtp_dict['number_tp_orders']
        if "depth" in obtp_dict:
            obtp_config.depth = obtp_dict["depth"]
        if "nr_bins" in obtp_dict:
            obtp_config.nr_bins = obtp_dict["nr_bins"]
        if "order_repost_beyond_threshold" in obtp_dict:
            obtp_config.order_repost_beyond_threshold = obtp_dict["order_repost_beyond_threshold"]

        return obtp_config

    def calculate_tp_orders(self,
                            position: Position,
                            position_side: PositionSide,
                            symbol_information: SymbolInformation,
                            obtp_config: ObTpConfig) -> List[Order]:
        if obtp_config.enabled is False:
            return []

        symbol = position.symbol
        orders = []
        if position_side == PositionSide.LONG:
            bottom_price = position.entry_price * (1 + obtp_config.minimum_tp_distance)
        else:
            bottom_price = position.entry_price * (1 - obtp_config.minimum_tp_distance)
        remaining_quantity = position.position_size

        tp_prices = self.get_prices(symbol=symbol,
                                    position_side=position_side,
                                    obtp_config=obtp_config,
                                    bottom_price=bottom_price,
                                    symbol_information=symbol_information)

        if len(tp_prices) == 0:
            return orders

        qty_per_tp = round_dn(position.position_size / len(tp_prices), symbol_information.quantity_step)
        for tp_price in tp_prices:
            if remaining_quantity == 0.0:
                break
            min_tp_qty = calc_min_qty(price=tp_price,
                                      inverse=False,
                                      qty_step=symbol_information.quantity_step,
                                      min_qty=symbol_information.minimum_quantity,
                                      min_cost=symbol_information.minimal_sell_cost)
            tp_qty = max(qty_per_tp, min_tp_qty)
            if remaining_quantity < tp_qty:
                # in case the tp_qty is more than the remaining quantity, use the remaining quantity instead
                break
            new_order = LimitOrder(order_type_identifier=OrderTypeIdentifier.TP,
                                   symbol=symbol_information.symbol,
                                   quantity=tp_qty,
                                   side=Side.SELL if position_side == PositionSide.LONG else Side.BUY,
                                   position_side=position_side,
                                   status=OrderStatus.NEW,
                                   price=tp_price,
                                   reduce_only=True,
                                   initial_entry=False,
                                   time_in_force=TimeInForce.GOOD_TILL_CANCELED)
            orders.append(new_order)
            remaining_quantity -= tp_qty

        if remaining_quantity > 0.0:
            if len(orders) == 0:
                if position_side == PositionSide.LONG:
                    tp_price = min(tp_prices)
                else:
                    tp_price = max(tp_prices)
                logger.info(f'{symbol} {position_side.name}: Detected partial TP, posting reduce-only order with '
                            f'remaining quantity {remaining_quantity} at price {tp_price}')

                new_order = LimitOrder(order_type_identifier=OrderTypeIdentifier.TP,
                                       symbol=symbol_information.symbol,
                                       quantity=remaining_quantity,
                                       side=Side.SELL if position_side == PositionSide.LONG else Side.BUY,
                                       position_side=position_side,
                                       status=OrderStatus.NEW,
                                       price=tp_price,
                                       reduce_only=True,
                                       initial_entry=False,
                                       time_in_force=TimeInForce.GOOD_TILL_CANCELED)
                orders.append(new_order)
            else:
                if position_side == PositionSide.LONG:
                    orders[0].quantity += round_dn(remaining_quantity, symbol_information.quantity_step)
                else:
                    orders[0].quantity += round_up(remaining_quantity, symbol_information.quantity_step)
        return orders

    def get_prices(self,
                   symbol: str,
                   position_side: PositionSide,
                   obtp_config: ObTpConfig,
                   bottom_price: float,
                   symbol_information: SymbolInformation) -> List[float]:
        if position_side == PositionSide.LONG:
            bids = self.orderbook.get_bids(symbol)[:obtp_config.depth]
            levels = parse_histogram(bids, nr_bins=obtp_config.nr_bins)
            levels.sort(key=lambda x: x[1], reverse=True)
            tp_prices = [entry[0] for entry in levels]
            tp_prices = [price for price in tp_prices if price >= bottom_price]
            if len(tp_prices) > obtp_config.number_tp_orders:
                tp_prices = tp_prices[0:obtp_config.number_tp_orders]
        elif position_side == PositionSide.SHORT:
            asks = self.orderbook.get_asks(symbol)[:obtp_config.depth]
            levels = parse_histogram(asks, nr_bins=obtp_config.nr_bins)
            levels.sort(key=lambda x: x[1], reverse=True)
            tp_prices = [entry[0] for entry in levels]
            tp_prices = [price for price in tp_prices if price <= bottom_price]
            if len(tp_prices) > obtp_config.number_tp_orders:
                tp_prices = tp_prices[0:obtp_config.number_tp_orders]
        else:
            raise UnsupportedParameterException(f'{symbol}: Received unsupported position side {position_side}')

        tp_prices = self.filter_reissue_threshold(symbol=symbol,
                                                  position_side=position_side,
                                                  all_tp_prices=tp_prices,
                                                  max_nr_levels=obtp_config.number_tp_orders,
                                                  order_repost_threshold=obtp_config.order_repost_beyond_threshold)
        tp_prices = [round_(price, symbol_information.price_step) for price in tp_prices]

        logger.info(f'{symbol} {position_side.name}: Calculated TP prices: {tp_prices} based on bottom price '
                    f'{bottom_price}')

        return list(set(tp_prices))  # remove duplicates

    def filter_reissue_threshold(self,
                                 symbol: str,
                                 position_side: PositionSide,
                                 all_tp_prices: List[float],
                                 max_nr_levels: int,
                                 order_repost_threshold: float) -> List[float]:
        tp_prices = []
        existing_tp_prices = [o.price for o in self.exchange_state.open_tp_orders(symbol=symbol,
                                                                                  position_side=position_side)]
        for tp_price in all_tp_prices:
            if len(tp_prices) == max_nr_levels:
                break

            lower_reissue_threshold = tp_price * (1 - order_repost_threshold)
            upper_reissue_threshold = tp_price * (1 + order_repost_threshold)
            overlapping_existing_prices = [p for p in existing_tp_prices if p >= lower_reissue_threshold and p <= upper_reissue_threshold]
            if len(overlapping_existing_prices) > 0:
                tp_price_to_use = overlapping_existing_prices[0]
                logger.info(f'{symbol} {position_side.name}: Using existing overlapping TP price {tp_price_to_use} '
                            f'instead of {tp_price} based on order repost threshold {order_repost_threshold}')
                tp_prices.append(tp_price_to_use)
            else:
                tp_prices.append(tp_price)

        return tp_prices
