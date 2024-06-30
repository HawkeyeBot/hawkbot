import logging

from hawkbot.core.model import Position, SymbolInformation, Timeframe
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.strategies.abstract_base_strategy import AbstractBaseStrategy
from hawkbot.utils import fill_required_parameters
import ta.trend
from pandas import DataFrame

logger = logging.getLogger(__name__)


class EmaFlipLongStrategy(AbstractBaseStrategy):
    def __init__(self):
        super().__init__()
        self.ema_timeframe: Timeframe = None
        self.ema_window: int = None

    def init_config(self):
        super().init_config()
        fill_required_parameters(target=self,
                                 config=self.strategy_config,
                                 required_parameters=['ema_window'])

        if 'ema_timeframe' in self.strategy_config:
            self.ema_timeframe = Timeframe.parse(self.strategy_config['ema_timeframe'])
        else:
            raise InvalidConfigurationException('The parameter \'ema_timeframe\' is mandatory')

    def on_no_open_position(self,
                            symbol: str,
                            position: Position,
                            symbol_information: SymbolInformation,
                            wallet_balance: float,
                            current_price: float):
        candles = self.candlestore_client.get_last_candles(symbol=symbol, timeframe=self.ema_timeframe, amount=self.ema_window + 1)
        ema = ta.trend.ema_indicator(close=DataFrame(candles)["close"], window=self.ema_window)
        if ema.iloc[-1] > ema.iloc[2]:
            logger.info(f'{symbol} {self.position_side.name}: last EMA {ema.iloc[-1]} is higher than previous EMA {ema.iloc[-2]}, '
                        f'indicating a potential trend reversal. Place order')
        else:
            logger.info(f'{symbol} {self.position_side.name}: last EMA {ema.iloc[-1]} is equal or less than previous EMA {ema.iloc[-2]}, '
                        f'not placing order')
