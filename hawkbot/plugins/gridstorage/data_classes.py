from dataclasses import dataclass

from hawkbot.core.data_classes import PositionSide
from hawkbot.core.model import Timeframe


@dataclass
class QuantityRecord:
    position_side: PositionSide
    quantity: float
    accumulated_quantity: float
    raw_quantity: float

    @property
    def max_position_size(self):
        return self.accumulated_quantity - self.quantity


@dataclass
class PriceRecord:
    position_side: PositionSide
    price: float
