import logging

from hawkbot.core.data_classes import SymbolInformation, Position
from hawkbot.core.model import Timeframe, StopLimitOrder, OrderTypeIdentifier, OrderStatus, TimeInForce
from hawkbot.strategies.abstract_base_strategy import AbstractBaseStrategy
from hawkbot.utils import fill_optional_parameters

logger = logging.getLogger(__name__)


class TrailingEntryLongStrategy(AbstractBaseStrategy):
    def __init__(self):
        super().__init__()

    def init_config(self):
        super().init_config()

        optional_parameters = []
        fill_optional_parameters(target=self, config=self.strategy_config, optional_parameters=optional_parameters)

    def on_no_open_position(self,
                            symbol: str,
                            position: Position,
                            symbol_information: SymbolInformation,
                            wallet_balance: float,
                            current_price: float):
        last_candle = self.candlestore_client.get_last_candles(symbol=symbol,
                                                               timeframe=Timeframe.ONE_MINUTE,
                                                               amount=1)[0]
        logger.info(f'{symbol} {self.position_side.name}: Last candle = {last_candle}')
        if last_candle.close <= last_candle.open:
            # last candle was a red candle
            trigger_price = current_price * 1.001
            price = trigger_price + symbol_information.price_step

            existing_entries = self.exchange_state.open_orders(symbol=symbol, position_side=self.position_side, order_type_identifiers=[OrderTypeIdentifier.TRAILING_ENTRY])

            if len(existing_entries) == 0:
                if trigger_price > last_candle.close:
                    return
            else:
                existing_trigger_price = existing_entries[0].stop_price
                if trigger_price >= existing_trigger_price:
                    # leave the existing order on the exchange
                    return

            order_to_place = StopLimitOrder(order_type_identifier=OrderTypeIdentifier.TRAILING_ENTRY,
                                            symbol=symbol,
                                            quantity=position.position_size,
                                            side=position.decrease_side,
                                            position_side=self.position_side,
                                            status=OrderStatus.NEW,
                                            price=price,
                                            stop_price=trigger_price,
                                            initial_entry=False,
                                            time_in_force=TimeInForce.GOOD_TILL_CANCELED)
            self.enforce_grid(new_orders=[order_to_place], exchange_orders=existing_entries)
        else:
            self.order_executor.cancel_orders(orders=self.exchange_state.all_open_orders(symbol=symbol, position_side=self.position_side))
