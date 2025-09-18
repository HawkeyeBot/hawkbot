import logging
import os
import signal

from pynput import keyboard

from hawkbot.core.data_classes import Trigger
from hawkbot.core.model import Position, SymbolInformation, LimitOrder, OrderTypeIdentifier, TimeInForce, Side, StopLimitOrder, PositionSide
from hawkbot.core.orderbook.orderbook import OrderBook
from hawkbot.plugins.tp.tp_plugin import TpConfig
from hawkbot.strategies.abstract_base_strategy import AbstractBaseStrategy
from hawkbot.utils import calc_min_qty, round_, fill_required_parameters

logger = logging.getLogger(__name__)


class ManualHedgedWiggleStrategy(AbstractBaseStrategy):
    def __init__(self):
        super().__init__()
        self.listener: keyboard.Listener = keyboard.Listener(on_press=self.on_press)
        self.key_enter: str = None
        self.key_cancel_entry: str = None
        self.key_quit: str = None
        self.key_pause: str = None
        self.ctrlc = str(chr(ord("C") - 64))
        self.paused: bool = False

        self.entry_size_long: float = None
        self.entry_size_short: float = None
        self.chunk_size_long: float = None
        self.chunk_size_short: float = None
        self.original_position_size_long: float = None
        self.original_position_price_long: float = None
        self.original_position_size_short: float = None
        self.original_position_price_short: float = None
        self.tp_distance: float = None
        self.custom_tp_config: TpConfig = TpConfig()

        self.key_mapping = {}

    def init(self):
        super().init()
        self.order_executor.exchange.ping()

        required_parameters = ['entry_size_long',
                               'entry_size_short',
                               'chunk_size_long',
                               'chunk_size_short',
                               'key_enter',
                               'key_cancel_entry',
                               'key_quit',
                               'key_pause',
                               'original_position_size_long',
                               'original_position_size_short',
                               'original_position_price_long',
                               'original_position_price_short',
                               'tp_distance']
        fill_required_parameters(target=self, config=self.strategy_config, required_parameters=required_parameters)
        self.key_mapping[self.key_enter] = self._start_hedged_entry
        self.key_mapping[self.key_cancel_entry] = self._cancel_entry_orders
        self.key_mapping[self.key_pause] = self._pause

        self.custom_tp_config.allow_move_away = True
        self.custom_tp_config.minimum_tp = self.tp_distance

        self.listener.start()

    def on_press(self, key):
        if not hasattr(key, 'char'):
            return

        if key.char == self.key_quit:
            os.kill(os.getpid(), signal.SIGTERM)

        try:
            key_pressed = key.char
            if self.paused is True and key.char != self.key_pause:
                logger.info(f'{self.symbol} {self.position_side.name}: Ignoring key {key.char} because execution is paused')
                return

            logger.info(f'{self.symbol} {self.position_side.name}: Key(s) {key_pressed} pressed')
            if key_pressed in self.key_mapping:
                self.key_mapping[key_pressed](key_pressed)
            else:
                logger.debug(f'{self.symbol} {self.position_side.name}: Non-mapped key {key_pressed} pressed')
        except:
            logger.exception(f'Error handling key press {key}')

    def _start_hedged_entry(self, key_pressed):
        logger.info(f'{self.symbol} {self.position_side.name}: Placing entry order')
        entry_orders = []

        symbol_information = self.exchange_state.get_symbol_information(self.symbol)
        min_quantity = calc_min_qty(price=self.exchange_state.get_last_price(self.symbol),
                                    inverse=False,
                                    qty_step=symbol_information.quantity_step,
                                    min_qty=symbol_information.minimum_quantity,
                                    min_cost=symbol_information.minimal_buy_cost)

        # if current position size is bigger than original position size, do nothing
        long_position = self.exchange_state.position(symbol=self.symbol, position_side=PositionSide.LONG)
        short_position = self.exchange_state.position(symbol=self.symbol, position_side=PositionSide.SHORT)
        if long_position.position_size <= self.original_position_size_long:
            lowest_ask = self.orderbook.get_lowest_ask(symbol=self.symbol)
            logger.info(f'{self.symbol}: Lowest ask = {lowest_ask}')

            desired_quantity = self.entry_size_long + self.chunk_size_long
            # place entry long order
            quantity_long = max(desired_quantity, min_quantity)
            long_entry_order = LimitOrder(order_type_identifier=OrderTypeIdentifier.ENTRY,
                                          symbol=self.symbol,
                                          quantity=quantity_long,
                                          side=Side.BUY,
                                          position_side=PositionSide.LONG,
                                          price=lowest_ask)
            logger.info(f"{self.symbol}: Placing long buy order {long_entry_order.quantity}@{long_entry_order.price}")
            entry_orders.append(long_entry_order)
            self._write_used_price(symbol=self.symbol, position_side=PositionSide.LONG, used_price=long_entry_order.price)
        else:
            logger.info(
                f"{self.symbol}: Not placing LONG entry order because current position size {long_position.position_size} > original position size {self.original_position_size_long}")

        if short_position.position_size <= self.original_position_size_short:
            highest_bid = self.orderbook.get_highest_bid(symbol=self.symbol)
            logger.info(f'{self.symbol}: Highest bid = {highest_bid}')

            desired_quantity = self.entry_size_short + self.chunk_size_short
            # place entry short order
            quantity_short = max(desired_quantity, min_quantity)
            short_entry_order = LimitOrder(order_type_identifier=OrderTypeIdentifier.ENTRY,
                                           symbol=self.symbol,
                                           quantity=quantity_short,
                                           side=Side.SELL,
                                           position_side=PositionSide.SHORT,
                                           price=highest_bid)
            logger.info(f"{self.symbol}: Placing short sell order {short_entry_order.quantity}@{short_entry_order.price}")
            entry_orders.append(short_entry_order)
            self._write_used_price(symbol=self.symbol, position_side=PositionSide.SHORT, used_price=short_entry_order.price)

        open_entry_orders = self.exchange_state.open_entry_orders(symbol=self.symbol, position_side=self.position_side)
        # self.enforce_grid(new_orders=entry_orders, exchange_orders=open_entry_orders, lowest_price_first=True)

    def on_pulse(self,
                 symbol: str,
                 position: Position,
                 symbol_information: SymbolInformation,
                 wallet_balance: float,
                 current_price: float):
        self.custom_tp_config.fixed_tp_price = None
        tp_orders = []

        # only place TP order if position size is bigger than original position size
        long_position = self.exchange_state.position(symbol=symbol, position_side=PositionSide.LONG)
        if long_position.position_size > self.original_position_size_long:
            # TP long quantity = entry size + chunk size
            long_entry_price = self._read_used_price(symbol=symbol, position_side=PositionSide.LONG)
            tp_long_qty = self.entry_size_long + self.chunk_size_long
            tp_long_price = (self.chunk_size_long * self.original_position_price_long) + (self.entry_size_long * long_entry_price) / tp_long_qty
            tp_long_price = tp_long_price * (1 + self.tp_config.minimum_tp)
            self.custom_tp_config.fixed_tp_price = tp_long_price
            tp_order = self.tp_plugin.calculate_tp_orders(position=long_position,
                                                          position_side=PositionSide.LONG,
                                                          symbol_information=symbol_information,
                                                          current_price=current_price,
                                                          tp_config=self.custom_tp_config)[0]
            logger.info(f'{symbol} LONG: Placing TP order {tp_order.quantity}@{tp_order.price}')
            tp_orders.append(tp_order)
        else:
            logger.debug(f'{symbol} LONG: Not placing TP order for long side because original position size has not been exceeded')

        short_position = self.exchange_state.position(symbol=symbol, position_side=PositionSide.SHORT)
        if short_position.position_size > self.original_position_size_long:
            # TP quantity = entry size + chunk size
            short_entry_price = self._read_used_price(symbol=symbol, position_side=PositionSide.SHORT)
            tp_short_qty = self.entry_size_short + self.chunk_size_short
            tp_short_price = (self.chunk_size_short * self.original_position_price_short) + (self.entry_size_short * short_entry_price) / tp_short_qty
            tp_short_price = tp_short_price * (1 - self.tp_config.minimum_tp)
            self.custom_tp_config.fixed_tp_price = tp_short_price
            tp_order = self.tp_plugin.calculate_tp_orders(position=short_position,
                                                          position_side=PositionSide.SHORT,
                                                          symbol_information=symbol_information,
                                                          current_price=current_price,
                                                          tp_config=self.custom_tp_config)
            logger.info(f'{symbol} SHORT: Placing TP order {tp_order.quantity}@{tp_order.price}')
            tp_orders.append(tp_order)
        else:
            logger.debug(f'{symbol} LONG: Not placing TP order for long side because original position size has not been exceeded')

        self.custom_tp_config.fixed_tp_price = None

        open_tp_orders = self.exchange_state.open_tp_orders(symbol=self.symbol, position_side=self.position_side)
        # self.enforce_grid(new_orders=tp_orders, exchange_orders=open_tp_orders, lowest_price_first=True)

    def _write_used_price(self, symbol: str, position_side: PositionSide, used_price: float):
        with open(f'data/used_price_{symbol}_{position_side.name}.txt', 'w') as f:
            logger.info(f"{symbol} {position_side.name}: writing used price = {used_price}")
            f.write(f'{used_price}')

    def _read_used_price(self, symbol: str, position_side: PositionSide) -> float:
        with open(f'data/used_price_{symbol}_{position_side.name}.txt', 'r') as f:
            used_price = float(f.readline())
            logger.info(f"{symbol} {position_side.name}: read used price = {used_price}")
            return used_price

    def _cancel_entry_orders(self, key_pressed):
        symbol = self.symbol
        position_side = self.position_side

        logger.info(f'{symbol} {position_side.name}: Cancelling all open entry orders')
        open_orders = self.exchange_state.open_entry_orders(symbol=symbol, position_side=self.position_side)
        self.order_executor.cancel_orders(open_orders)

    def _pause(self, key_pressed):
        if self.paused is False:
            self.paused = True
            logging.info(f'{self.symbol} {self.position_side.name}: Execution paused')
        else:
            self.paused = False
            logging.info(f'{self.symbol} {self.position_side.name}: Execution resumed')

    def on_shutdown(self,
                    symbol: str,
                    position: Position,
                    symbol_information: SymbolInformation,
                    wallet_balance: float,
                    current_price: float):
        super().on_shutdown(symbol=symbol,
                            position=position,
                            symbol_information=symbol_information,
                            wallet_balance=wallet_balance,
                            current_price=current_price)
        try:
            self.listener.stop()
        except:
            logger.exception(f"{symbol} {self.position_side.name}: Failed to stop keyboard listener")

    def log_trigger(self, trigger: Trigger) -> bool:
        return trigger not in [Trigger.NO_OPEN_POSITION, Trigger.PERIODIC_CHECK, Trigger.PULSE]
