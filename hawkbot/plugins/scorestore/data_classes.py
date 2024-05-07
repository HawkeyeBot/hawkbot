from dataclasses import dataclass


@dataclass
class ScorePower:
    timestamp: int
    price: float
    score: float
    power: float
    nr_bins: int
    depth: int
