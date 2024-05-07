from dataclasses import dataclass, field
from typing import List

from hawkbot.core.model import PositionSide


@dataclass
class SupportResistance:
    supports: List[float] = field(default_factory=list)
    resistances: List[float] = field(default_factory=list)


@dataclass
class SupportResistanceCache:
    symbol: str
    position_side: PositionSide
    last_candle_close_date: int = 0
    support_resistance: SupportResistance = field(default_factory=SupportResistance)

    @property
    def any_level_found(self):
        return len(list(self.support_resistance.supports)) > 0 or \
               len(list(self.support_resistance.resistances)) > 0
