from dataclasses import dataclass, field
from typing import List

from hawkbot.utils import calc_diff


@dataclass
class Level:
    price: float = field(default_factory=lambda: None)
    quantity: float = field(default_factory=lambda: None)


@dataclass
class Bids:
    levels: List[Level] = field(default_factory=lambda: [])

    @property
    def prices(self) -> List[float]:
        return [level.price for level in self.levels]

    def append(self, price: float, quantity: float):
        self.levels.append(Level(price=price, quantity=quantity))

    def closest_level(self) -> Level:
        max_price = max([level.price for level in self.levels])
        for level in self.levels:
            if level.price == max_price:
                return level
        return None

    @property
    def closest_price(self) -> float:
        return self.closest_level().price

    @property
    def strongest_price(self) -> float:
        max_level: Level = None
        for level in self.levels:
            if max_level is None:
                max_level = level
            elif level.quantity > max_level.quantity:
                max_level = level

        return max_level.price

    @property
    def strongest_quantity(self) -> float:
        max_level: Level = None
        for level in self.levels:
            if max_level is None:
                max_level = level
            elif level.quantity > max_level.quantity:
                max_level = level

        return max_level.quantity

    @property
    def strongest_prices(self) -> List[float]:
        sorted_levels = sorted(self.levels, key=lambda level: level.quantity, reverse=True)
        return [level.price for level in sorted_levels]

    def sum(self, price_below: float = None) -> float:
        return sum([level.quantity for level in self.levels if price_below is None or level.price <= price_below])


@dataclass
class Asks:
    levels: List[Level] = field(default_factory=lambda: [])

    @property
    def prices(self) -> List[float]:
        return [level.price for level in self.levels]

    def append(self, price: float, quantity: float):
        self.levels.append(Level(price=price, quantity=quantity))

    def closest_level(self) -> Level:
        min_price = min([level.price for level in self.levels])
        for level in self.levels:
            if level.price == min_price:
                return level
        return None

    @property
    def closest_price(self) -> float:
        return self.closest_level().price

    @property
    def strongest_price(self) -> float:
        max_level: Level = None
        for level in self.levels:
            if max_level is None:
                max_level = level
            elif level.quantity > max_level.quantity:
                max_level = level

        return max_level.price

    @property
    def strongest_quantity(self) -> float:
        max_level: Level = None
        for level in self.levels:
            if max_level is None:
                max_level = level
            elif level.quantity > max_level.quantity:
                max_level = level

        return max_level.quantity

    @property
    def strongest_prices(self) -> List[float]:
        sorted_levels = sorted(self.levels, key=lambda level: level.quantity, reverse=True)
        return [level.price for level in sorted_levels]

    def sum(self, price_above: float = None) -> float:
        return sum([level.quantity for level in self.levels if price_above is None or level.price >= price_above])


@dataclass
class ScorePower:
    price: float
    score: float
    power: float


@dataclass
class SupportResistance:
    supports: Bids = field(default_factory=lambda: Bids())
    resistances: Asks = field(default_factory=lambda: Asks())

    def distance_to_strongest_bid(self, current_price: float) -> float:
        strongest_bid = self.supports.strongest_price
        return calc_diff(strongest_bid, current_price)

    def distance_to_strongest_ask(self, current_price: float) -> float:
        strongest_ask = self.resistances.strongest_price
        return calc_diff(strongest_ask, current_price)

    def swing_score_power(self, current_price) -> ScorePower:
        support_mean = 0.0
        support_quantity = 0.0
        for support in self.supports.levels:
            support_mean += support.price * support.quantity
            support_quantity += support.quantity
        support_mean = support_mean / support_quantity

        resistance_mean = 0.0
        resistance_quantity = 0.0
        for resistance in self.resistances.levels:
            resistance_mean += resistance.price * resistance.quantity
            resistance_quantity += resistance.quantity
        resistance_mean = resistance_mean / resistance_quantity

        score = ((resistance_mean - current_price) * support_quantity) - ((current_price - support_mean) * resistance_quantity)
        power = (resistance_mean - current_price) / (resistance_mean - support_mean)
        return ScorePower(price=current_price, score=score, power=power)
