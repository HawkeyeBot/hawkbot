import logging
from typing import Dict, List

from hawkbot.core.model import PositionSide
from hawkbot.plugins.gridstorage.data_classes import QuantityRecord, PriceRecord

logger = logging.getLogger(__name__)


class MemoryRepository:
    def __init__(self):
        self.quantities: Dict[str, Dict[PositionSide, List[QuantityRecord]]] = {}
        self.prices: Dict[str, Dict[PositionSide, List[float]]] = {}
        self.root_price: Dict[str, Dict[PositionSide, float]] = {}

    def store_quantities(self, symbol: str, quantities: List[QuantityRecord]):
        if symbol not in self.quantities:
            self.quantities[symbol] = {}
        position_side = quantities[0].position_side
        self.quantities[symbol][position_side] = quantities

    def get_quantities(self, symbol: str, position_side: PositionSide) -> List[QuantityRecord]:
        try:
            return sorted(self.quantities[symbol][position_side], key=lambda x:x.quantity)
        except:
            return self.quantities.setdefault(symbol, {}).setdefault(position_side, [])

    def store_prices(self, symbol: str, prices_records: List[PriceRecord]):
        position_side = prices_records[0].position_side
        self.prices.setdefault(symbol, {}).setdefault(position_side, [])
        for price_record in prices_records:
            self.prices[symbol][position_side].append(price_record.price)

    def get_prices(self, symbol: str, position_side: PositionSide) -> List[float]:
        try:
            return self.prices[symbol][position_side]
        except KeyError:
            return self.prices.setdefault(symbol, {}).setdefault(position_side, [])

    def get_root_price(self, symbol: str, position_side: PositionSide) -> float:
        try:
            return self.root_price[symbol][position_side]
        except KeyError:
            return self.root_price.setdefault(symbol, {}).setdefault(position_side, None)

    def store_root_price(self, symbol: str, position_side: PositionSide, price: float):
        self.root_price.setdefault(symbol, {})
        self.root_price[symbol][position_side] = price

    def reset(self, symbol: str, position_side: PositionSide):
        logger.debug(f'Resetting price & quantities for symbol {symbol} for {position_side.name}')
        self.reset_quantities(symbol=symbol, position_side=position_side)
        self.reset_prices(symbol=symbol, position_side=position_side)
        self.reset_root_price(symbol=symbol, position_side=position_side)

    def reset_root_price(self, symbol: str, position_side: PositionSide):
        try:
            self.root_price[symbol][position_side]
        except KeyError:
            pass

    def reset_prices(self, symbol: str, position_side: PositionSide):
        try:
            self.prices[symbol][position_side].clear()
        except KeyError:
            pass

    def reset_quantities(self, symbol: str, position_side: PositionSide):
        try:
            self.quantities[symbol][position_side].clear()
        except KeyError:
            pass