from dataclasses import dataclass, field
from typing import Dict

from fastenum import fastenum

from hawkbot.core.data_classes import Timeframe


class LevelType(fastenum.Enum):
    PEAK = "PEAK"
    TROUGH = "TROUGH"


@dataclass
class SupportResistance:
    supports: Dict[float, LevelType] = field(default_factory=dict)
    resistances: Dict[float, LevelType] = field(default_factory=dict)


@dataclass
class TimeframeCache:
    symbol: str
    timeframe: Timeframe
    last_candle_close_date: int = 0
    support_resistance: SupportResistance = field(default_factory=SupportResistance)

    @property
    def any_level_found(self):
        return len(list(self.support_resistance.supports.keys())) > 0 or \
               len(list(self.support_resistance.resistances.keys())) > 0