from dataclasses import field, dataclass
from typing import List

from hawkbot.core.model import Mode, OrderType


@dataclass
class Condition:
    upnl_exposed_wallet_above: float = field(default=None)
    upnl_total_wallet_above: float = field(default=None)
    relative_wallet_above: float = field(default=None)
    wallet_exposure_above: float = field(default=None)


@dataclass
class Placement:
    stoploss_price: float = field(default=None)
    position_trigger_distance: float = field(default=None)
    last_entry_trigger_distance: float = field(default=None)
    stoploss_sell_distance: float = 0.002
    grid_range: float = field(default=None)
    nr_orders: int = 1


@dataclass
class StoplossConfig:
    conditions: Condition = field(default=None)
    placement: Placement = field(default=None)
    custom_trigger_price_enabled: bool = field(default=False)
    order_type: OrderType = field(default=None)
    trailing_enabled: bool = field(default=False)
    trailing_distance: float = field(default=None)


@dataclass
class StoplossesConfig:
    enabled: bool = field(default=True)
    stoplosses: List[StoplossConfig] = field(default_factory=lambda: [])
    post_stoploss_mode: Mode = field(default=None)
