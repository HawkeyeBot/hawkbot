import logging
from typing import List
from pandas import DataFrame

from hawkbot.core.candlestore.candlestore import Candlestore
from hawkbot.core.data_classes import Candle
from hawkbot.core.model import Timeframe
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.core.time_provider import TimeProvider
from hawkbot.utils import period_as_ms
import ta.trend

logger = logging.getLogger(__name__)


class PluginExample(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.candlestore: Candlestore = None  # automatically injected by framework
        self.time_provider: TimeProvider = None  # automatically injected by framework

        """
        The following field names can be automatically injected:
                'candlestore'
                'exchange'
                'exchange_name'
                'orderbook'
                'tick_store'
                'exchange_state'
                'time_provider'
                'entry_manager'
                'order_executor'
                'config'
                'mode_processor'
                'redis_port'
        """

    def doSomething(self, symbol: str, timeframe: Timeframe):
        last_ten_candles: List[Candle] = self.candlestore.get_last_candles(symbol=symbol, timeframe=timeframe, amount=10)
        last_ten_candles_df: DataFrame = DataFrame(last_ten_candles)
        ema = ta.trend.ema_indicator(close=last_ten_candles_df["close"], window=9)

        now = self.time_provider.get_utc_now_timestamp()
        twenty_days_ms = period_as_ms('20D')
        start_date = now - twenty_days_ms
        candles_last_twenty_days = self.candlestore.get_candles_in_range(symbol=symbol, timeframe=Timeframe.parse('1H'), start_date=start_date, end_date=now)

