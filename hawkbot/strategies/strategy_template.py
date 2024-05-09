import logging

from hawkbot.core.model import Position, SymbolInformation
from hawkbot.strategies.abstract_base_strategy import AbstractBaseStrategy

logger = logging.getLogger(__name__)


class StrategyTemplate(AbstractBaseStrategy):
    def on_no_open_position(self,
                            symbol: str,
                            position: Position,
                            symbol_information: SymbolInformation,
                            wallet_balance: float,
                            current_price: float):
        # Add code here for placing an order when not in position
        pass