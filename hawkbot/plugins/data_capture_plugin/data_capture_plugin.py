import time

import os

from typing import Dict, List

import logging

from hawkbot.core.config.active_config_manager import ActiveConfigManager
from hawkbot.core.data_classes import Tick, Candle
from hawkbot.core.model import PositionSide, Timeframe
from hawkbot.core.tick_listener import TickListener
from hawkbot.core.tickstore.tickstore import Tickstore
from hawkbot.core.time_provider import TimeProvider
from hawkbot.exceptions import BanPreventionException
from hawkbot.plugins.orderbook_sr.data_classes import SupportResistance
from hawkbot.plugins.orderbook_sr.orderbook_sr import OrderbookSrPlugin
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.utils import period_as_ms

logger = logging.getLogger(__name__)


class DataCapturePlugin(Plugin, TickListener):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.config = ActiveConfigManager(redis_host=redis_host, redis_port=redis_port)
        self.time_provider: TimeProvider = None
        self.orderbook_sr_plugin: OrderbookSrPlugin = None
        self.tick_store: Tickstore = None
        self.current_tps_timestamp: Dict[str, int] = {}
        self.current_tps_count: Dict[str, int] = {}
        self.initialized_ob_file_symbols: List[str] = []
        self.initialized_tps_file_symbols: List[str] = []
        self.initialized_tick_symbols: List[str] = []
        self.current_candle: Dict[str, Candle] = {}
        self.nr_of_trades_in_current_candle: Dict[str, int] = {}
        self.candle_tick_size: int = 300
        self.last_write_current_candle: Dict[str, int] = {}

    def start(self):
        if self.config.tickstore_used is False:
            return

        # self.tick_processor.register_tick_listener(self)
        self.orderbook_sr_plugin = self.plugin_loader.get_plugin(OrderbookSrPlugin.plugin_name())

        init_tick_history_period = '3H'
        for symbol in self.config.symbols:
            filename = f'{symbol}_candles.csv'
            if os.path.exists(filename):
                os.remove(filename)
            with open(filename, 'w') as csv_file:
                csv_file.write('timestamp,open,high,low,close,symbol\n')

            now = self.time_provider.get_utc_now_timestamp()
            self.tick_store.purge_ticks_older_than(symbol=symbol, period=init_tick_history_period)
            passed = False
            while passed is False:
                try:
                    ticks = self.tick_store.get_ticks(symbol=symbol,
                                                      start_timestamp=now - period_as_ms(init_tick_history_period),
                                                      end_timestamp=now)
                    [self.on_new_tick(tick) for tick in ticks]
                    passed = True
                except BanPreventionException:
                    time.sleep(60)

    def capture_initial_entry_orderbook(self, symbol: str, position_side: PositionSide,
                                        support_resistance: SupportResistance):
        filename = f'{symbol}_{position_side.name}_inital_entry_orderbook_strength.csv'
        if symbol not in self.initialized_ob_file_symbols:
            if os.path.exists(filename):
                os.remove(filename)
            with open(filename, 'a') as csv_file:
                csv_file.write('timestamp,strongest_bid,strongest_ask,strongest_bid_strength,strongest_ask_strength,'
                               'bid_total_strength,ask_total_strength\n')
            self.initialized_ob_file_symbols.append(symbol)

        with open(filename, 'a') as csv_file:
            now = self.time_provider.get_utc_now_timestamp()
            strongest_bid = support_resistance.supports.strongest_price
            strongest_ask = support_resistance.resistances.strongest_price
            strongest_bid_strength = support_resistance.supports.strongest_quantity
            strongest_ask_strength = support_resistance.resistances.strongest_quantity
            bid_total_strength = support_resistance.supports.sum()
            ask_total_strength = support_resistance.resistances.sum()
            csv_file.write(f'{now},{strongest_bid},{strongest_ask},{strongest_bid_strength},{strongest_ask_strength},'
                           f'{bid_total_strength},{ask_total_strength}\n')

    def on_new_tick(self, tick: Tick):
        symbol = tick.symbol

        if symbol not in self.initialized_tick_symbols:
            filename = f'{symbol}_current_candle.csv'
            if os.path.exists(filename):
                os.remove(filename)
            with open(filename, 'a') as csv_file:
                csv_file.write('timestamp,open,high,low,close,symbol\n')
            self.initialized_tick_symbols.append(symbol)

        filename = f'{tick.symbol}_tps.csv'
        if symbol not in self.initialized_tps_file_symbols:
            if os.path.exists(filename):
                os.remove(filename)
            with open(filename, 'a') as csv_file:
                csv_file.write('timestamp,tps\n')
            self.initialized_tps_file_symbols.append(symbol)

        self.last_write_current_candle.setdefault(symbol, 0)
        self.nr_of_trades_in_current_candle.setdefault(symbol, 0)
        self._process_tick_in_candle(tick)

        self.current_tps_timestamp.setdefault(symbol, 0)
        self.current_tps_count.setdefault(symbol, 0)

        nr_trades = (tick.last_trade_id - tick.first_trade_id) + 1
        timestamp_s = int(tick.timestamp / 1000) * 1000
        if timestamp_s == self.current_tps_timestamp[symbol]:
            self.current_tps_count[symbol] += nr_trades
        else:
            if self.current_tps_count[symbol] > 0:
                with open(filename, 'a') as csv_file:
                    tps = self.current_tps_count[symbol]
                    csv_file.write(f'{self.current_tps_timestamp[symbol]},{tps}\n')

            self.current_tps_timestamp[symbol] = timestamp_s
            self.current_tps_count[symbol] = 0

    def _process_tick_in_candle(self, tick: Tick):
        symbol = tick.symbol
        tick_trade_processed = False

        for i, trade_id in enumerate(range(tick.first_trade_id, tick.last_trade_id + 1)):
            if symbol not in self.current_candle:
                self.current_candle[symbol] = Candle(symbol=tick.symbol,
                                                     timeframe=Timeframe.THREE_HUNDRED_TICKS,
                                                     open=tick.price,
                                                     high=tick.price,
                                                     low=tick.price,
                                                     close=tick.price,
                                                     volume=tick.qty * tick.price,
                                                     quote_volume=tick.qty,
                                                     start_date=tick.timestamp,
                                                     close_date=tick.timestamp)
            else:
                if self.nr_of_trades_in_current_candle[symbol] == self.candle_tick_size:
                    candle = self.current_candle[symbol]
                    with open(f'{symbol}_candles.csv', 'a') as csv_file:
                        csv_file.write(
                            f'{candle.start_date},{candle.open},{candle.high},{candle.low},{candle.close},{candle.symbol}\n')

                    self.current_candle[symbol] = Candle(symbol=tick.symbol,
                                                         timeframe=Timeframe.THREE_HUNDRED_TICKS,
                                                         open=tick.price,
                                                         high=tick.price,
                                                         low=tick.price,
                                                         close=tick.price,
                                                         volume=tick.qty * tick.price,
                                                         quote_volume=tick.qty,
                                                         start_date=tick.timestamp,
                                                         close_date=tick.timestamp)
                    self.nr_of_trades_in_current_candle[symbol] = 0
                else:
                    candle = self.current_candle[symbol]
                    candle.high = max(candle.high, tick.price)
                    candle.low = min(candle.low, tick.price)
                    candle.close = tick.price
                    candle.close_date = tick.timestamp
                    if tick_trade_processed is False:
                        candle.volume += tick.qty * tick.price
                        candle.quote_volume += tick.qty
                        tick_trade_processed = True

            self.nr_of_trades_in_current_candle[symbol] += 1

        # dashboard stuff
        if self.last_write_current_candle[symbol] + 1000 < self.time_provider.get_utc_now_timestamp():
            candle = self.current_candle[symbol]
            with open(f'{symbol}_current_candle.csv', 'w') as csv_file:
                csv_file.write('timestamp,open,high,low,close,symbol\n')
                csv_file.write(
                    f'{candle.start_date},{candle.open},{candle.high},{candle.low},{candle.close},{candle.symbol}')
            self.last_write_current_candle[symbol] = self.time_provider.get_utc_now_timestamp()
