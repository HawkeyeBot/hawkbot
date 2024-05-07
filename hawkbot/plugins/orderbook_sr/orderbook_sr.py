import logging

from hawkbot.core.model import PositionSide
from hawkbot.core.orderbook.orderbook import OrderBook
from hawkbot.plugins.orderbook_sr.data_classes import SupportResistance, Bids, Asks
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.utils import parse_histogram

logger = logging.getLogger(__name__)


class OrderbookSrPlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.orderbook: OrderBook = None  # Injected by framework

    def calculate_support_resistances(self,
                                      symbol: str,
                                      position_side: PositionSide,
                                      depth: int,
                                      nr_bins: int) -> SupportResistance:
        all_bids = self.orderbook.get_bids(symbol)
        bids = all_bids[:depth]
        all_asks = self.orderbook.get_asks(symbol)
        asks = all_asks[:depth]
        binned_asks = Asks()
        binned_bids = Bids()

        if len(bids) == 0 and len(asks) == 0:
            logger.warning(f'{symbol} {position_side.name}: There are 0 bids and 0 asks within depth {depth}, '
                           f'the total nr of bids is {len(all_bids)} and the total nr of asks is {len(all_asks)}')
        else:
            original_supports = parse_histogram(bids, nr_bins=nr_bins)
            original_supports.sort(key=lambda x: x[1], reverse=True)
            for price, quantity in original_supports:
                binned_bids.append(price=price, quantity=quantity)

            original_resistances = parse_histogram(asks, nr_bins=nr_bins)
            original_resistances.sort(key=lambda x: x[1], reverse=True)
            for price, quantity in original_resistances:
                binned_asks.append(price=price, quantity=quantity)

        support_resistance = SupportResistance(supports=binned_bids, resistances=binned_asks)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f'{symbol} {position_side.name}: Calculated supports are: \n'
                         f'{support_resistance.supports}\n'
                         f'Calculated resistances are: \n'
                         f'{support_resistance.resistances}')
        # logger.info(f'{symbol} {position_side.name}: Orderbook: \n'
        #             f'All bids:\n {all_bids}\n\n'
        #             f'All asks:\n {all_asks}')
        return support_resistance
