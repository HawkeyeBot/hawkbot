import logging

from hawkbot.core.candlestore.candlestore import Candlestore
from hawkbot.core.model import Position, SymbolInformation, Timeframe
from hawkbot.strategies.abstract_base_strategy import AbstractBaseStrategy

logger = logging.getLogger(__name__)


class StrategyTemplate(AbstractBaseStrategy):
    candlestore: Candlestore = None  # injected automatically by HB

    def on_periodic_check(self,
                            symbol: str,
                            position: Position,
                            symbol_information: SymbolInformation,
                            wallet_balance: float,
                            current_price: float):
        # Add code here for placing an order when not in position
        candles = self.candlestore.get_last_candles(symbol=symbol, timeframe=Timeframe.FIVE_MINUTES, amount=2500)
        last_low = candles[-1].low