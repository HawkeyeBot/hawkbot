import logging

from hawkbot.core.model import Position, SymbolInformation
from hawkbot.strategies.abstract_base_strategy import AbstractBaseStrategy
from hawkbot.utils import fill_required_parameters

logger = logging.getLogger(__name__)


class FastCatcherLongStrategy(AbstractBaseStrategy):
    def __init__(self):
        super().__init__()

    def init_config(self):
        super().init_config()
        fill_required_parameters(target=self,
                                 config=self.strategy_config,
                                 required_parameters=[])

    def on_pulse(self,
                 symbol: str,
                 position: Position,
                 symbol_information: SymbolInformation,
                 wallet_balance: float,
                 current_price: float):
        logger.info("Pulse")
