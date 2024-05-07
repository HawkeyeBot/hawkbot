import logging
import os
import threading
from typing import List

from redis import Redis

from hawkbot.core.config.bot_config import BotConfig
from hawkbot.core.data_classes import ExchangeState, Trigger
from hawkbot.core.model import Order, Position, BotStatus, LimitOrder, OrderTypeIdentifier, PositionSide, TimeInForce
from hawkbot.core.order_executor import OrderExecutor
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.core.redis_keys import TRIGGER_SYMBOL_POSITIONSIDE
from hawkbot.core.time_provider import TimeProvider
from hawkbot.exceptions import InvalidConfigurationException, NoResultException
from hawkbot.exchange.exchange import Exchange
from hawkbot.redis_utils import handle_redis_exception
from hawkbot.utils import readable, fill_optional_parameters, fill_required_parameters, readable_pct, period_as_s, period_as_ms, round_dn, round_

logger = logging.getLogger(__name__)


class MultiAutoreducePlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.time_provider: TimeProvider = None  # Injected by pluginloader
        self.exchange_state: ExchangeState = None  # Injected by plugin loader
        self.config: BotConfig = None  # Injected by plugin loader
        self.exchange: Exchange = None  # Injected by plugin loader
        self.order_executor: OrderExecutor = None  # Injected by plugin loader
        self.last_reduce_processing_timestamp: int = 0
        self.status: BotStatus = BotStatus.NEW
        self.trigger_event: threading.Event = threading.Event()
        self.enabled: bool = True
        self.reduce_interval: str = '1m'
        self.reduce_interval_s: float = None
        self.profit_percentage_used_for_reduction: float = None
        self.activate_size_above_exposed_balance_pct: float = None
        self.last_processed_income_file: str = './data/multi_autoreduce_last_processed_income'
        self.activate_above_upnl_pct: float = None
        self.max_age_income_ms: int = period_as_ms('3D')

        self.redis = Redis(host="127.0.0.1", port=self.redis_port, decode_responses=True)
        self.pubsub = self.redis.pubsub()
        self.init(plugin_config)

    def init(self, plugin_config):
        required_parameters = ['reduce_interval', 'profit_percentage_used_for_reduction']
        optional_parameters = ['enabled', 'activate_above_upnl_pct', 'activate_size_above_exposed_balance_pct']

        fill_required_parameters(target=self, config=plugin_config, required_parameters=required_parameters)
        fill_optional_parameters(target=self, config=plugin_config, optional_parameters=optional_parameters)

        if self.activate_above_upnl_pct is None and self.activate_size_above_exposed_balance_pct is None:
            raise InvalidConfigurationException('At least one of the parameters "activate_above_upnl_pct" or "activate_size_above_exposed_balance_pct" is required')

        if self.activate_above_upnl_pct is not None:
            self.activate_above_upnl_pct = -1 * (abs(self.activate_above_upnl_pct))

        if 'max_age_income' in plugin_config:
            self.max_age_income_ms = period_as_ms(plugin_config['max_age_income'])

        if self.profit_percentage_used_for_reduction > 1:
            raise InvalidConfigurationException(f"The value provided for \"profit_percentage_used_for_reduction\" is {self.profit_percentage_used_for_reduction}, which is more "
                                                f"than 1. Setting it to a value greater than 1 will make it reduce with more cost than what it's gaining.")

        self.reduce_interval_s = period_as_s(self.reduce_interval)

    def start(self):
        self.status = BotStatus.STARTING
        reducing_thread = threading.Thread(name=f'multi_autoreduce_plugin',
                                           target=self.process_schedule,
                                           daemon=True)
        reducing_thread.start()

        self.pubsub.psubscribe(**{f'{TRIGGER_SYMBOL_POSITIONSIDE}*': self._push_trigger})
        self.pubsub.run_in_thread(sleep_time=0.005, daemon=True, exception_handler=handle_redis_exception)

    def stop(self):
        self.status = BotStatus.STOPPING
        self.trigger_event.set()

        try:
            self.pubsub.close()
        except:
            pass

        try:
            self.redis.close()
        except:
            pass

    def process_schedule(self):
        self.status = BotStatus.RUNNING
        while self.status == BotStatus.RUNNING:
            if self.enabled:
                try:
                    self.reduce_stuck_positions()
                except:
                    logger.exception('Failed to determine/place reduce order')

            self.trigger_event.wait(self.reduce_interval_s)
        self.status = BotStatus.STOPPED

    def stop(self):
        self.redis.close()

    def reduce_stuck_positions(self) -> List[Order]:
        if self.enabled is False:
            return []

        incomes = self.exchange.fetch_incomes(start_time=self.get_last_processed_income_timestamp())
        total_realized_pnl = sum([income.income for income in incomes])
        available_pnl_for_reduce = total_realized_pnl * self.profit_percentage_used_for_reduction
        logger.info(f'Total realized PNL since {readable(self.get_last_processed_income_timestamp())} = {total_realized_pnl}, available for reducing stuck positions = '
                    f'{available_pnl_for_reduce}')

        # get new incomes since last processed timestamp
        if total_realized_pnl > 0:
            # if there is an existing reduce order, check if it needs to be moved closer to a moving price
            open_positions = self.exchange_state.get_all_open_positions()
            logger.debug(f"Open positions = {open_positions}")
            position_eligible_for_reduction = self.determine_position_to_reduce(open_positions)
            if position_eligible_for_reduction is None:
                logger.debug('No position was found eligible for reducing')
                return
            logger.info(f'Position chosen for reduction: {position_eligible_for_reduction}')
            self.place_reduce_order(position_eligible_for_reduction, available_pnl_for_reduce)

    def _push_trigger(self, message):
        triggers = [Trigger[triggerName] for triggerName in message['data'].split(',')]
        logger.debug(f'---------Message received: {message}')
        if any([x in triggers for x in [Trigger.POSITION_REDUCED, Trigger.REDUCE_FILLED]]):
            logger.debug(f'Received trigger reduce, updating last processed income timestamp to current time')
            self.set_last_processed_income_timestamp(self.time_provider.get_utc_now_timestamp())

    def place_reduce_order(self, position_to_reduce: Position, income_to_reduce: float):
        symbol = position_to_reduce.symbol
        position_side = position_to_reduce.position_side
        symbol_information = self.exchange_state.get_symbol_information(symbol)
        current_price = self.exchange_state.last_tick_price(symbol)
        if income_to_reduce > 0:
            reduce_price = current_price
            if position_side == PositionSide.LONG:
                reduce_price = round_(current_price - (1 * symbol_information.price_step), symbol_information.price_step)
            elif position_side == PositionSide.SHORT:
                reduce_price = round_(current_price + (1 * symbol_information.price_step), symbol_information.price_step)

            quantity_to_close = income_to_reduce / reduce_price
            quantity_to_close = round_dn(quantity_to_close, symbol_information.quantity_step)

            if quantity_to_close == 0:
                logger.info(f'{symbol} {position_side.name}: Not placing reduce order because the quantity would be 0')
                return

            reduce_order = LimitOrder(
                order_type_identifier=OrderTypeIdentifier.REDUCE,
                symbol=symbol_information.symbol,
                quantity=quantity_to_close,
                side=position_side.decrease_side(),  # placed on reverse position side
                position_side=position_side,
                initial_entry=False,
                reduce_only=True,
                time_in_force=TimeInForce.GOOD_TILL_CANCELED,
                price=reduce_price)

            logger.info(f'{symbol} {position_side.name}: Reducing position with {quantity_to_close} units at price {reduce_price} based on available income '
                        f'{income_to_reduce}, current price = {current_price}')
            self.order_executor.create_order(reduce_order)

    def determine_position_to_reduce(self, open_positions: List[Position]) -> Position:
        eligible_positions = [position for position in open_positions if self.position_needs_reducing(position)]
        selected_position = None
        biggest_drawdown = 0
        for position in eligible_positions:
            position_drawdown = position.calculate_pnl(self.exchange_state.last_tick_price(position.symbol))
            if position_drawdown < biggest_drawdown:
                logger.debug(f'{position.symbol} {position.position_side.name}: Drawdown {position_drawdown} is bigger than previously detected drawdown {biggest_drawdown}')
                selected_position = position
                biggest_drawdown = position_drawdown

        return selected_position

    def set_last_processed_income_timestamp(self, last_processed_income_timestamp: int):
        if self.enabled is False:
            return

        with open(self.last_processed_income_file, 'w') as f:
            f.write(f'{last_processed_income_timestamp}')
        logger.debug(f'Set last processed income timestamp to {readable(last_processed_income_timestamp)}')

    def get_last_processed_income_timestamp(self) -> int:
        # get the total profit gained since the last processed income
        try:
            now = self.time_provider.get_utc_now_timestamp()
            if not os.path.exists(self.last_processed_income_file):
                self.set_last_processed_income_timestamp(now - self.max_age_income_ms)

            with open(self.last_processed_income_file, 'r') as file:
                last_processed_income_timestamp = int(file.readline())

            oldest_income_timestamp_to_use = now - self.max_age_income_ms
            if last_processed_income_timestamp < oldest_income_timestamp_to_use:
                logger.info(f'Last processed income timestamp to use {readable(last_processed_income_timestamp)} is older than {self.max_age_income_ms}ms, setting last '
                            f'processed income timestamp to {readable(oldest_income_timestamp_to_use)}')
                self.set_last_processed_income_timestamp(oldest_income_timestamp_to_use)
                return oldest_income_timestamp_to_use
            return last_processed_income_timestamp
        except:
            logger.exception(f"Failed to read last income timestamp from file {self.last_processed_income_file}, expecting this to be an IO race condition")
            return 0

    def position_needs_reducing(self, position: Position) -> bool:
        symbol = position.symbol
        position_side = position.position_side

        try:
            if not self.config.find_position_side_config(symbol=symbol, position_side=position_side):
                logger.debug(f'{symbol} {position_side.name}: No configuration found for open position, ignoring position')
                return False
        except NoResultException:
            logger.debug(f'{symbol} {position_side.name}: Ignoring open position because it\'s not part of the configuration')
            return False
        if not self.exchange_state.is_initialized(symbol):
            logger.debug(f'{symbol} {position_side.name}: Ignoring symbol, since it\'s not initialized yet')
            return False

        total_balance = self.exchange_state.symbol_balance(symbol)
        position_side_config = self.config.find_position_side_config(symbol=symbol, position_side=position_side)
        wallet_exposure = position_side_config.wallet_exposure
        wallet_exposure_ratio = position_side_config.wallet_exposure_ratio
        configured_wallet_exposure = self.exchange_state.calculate_wallet_exposure_ratio(symbol=symbol,
                                                                                         wallet_exposure=wallet_exposure,
                                                                                         wallet_exposure_ratio=wallet_exposure_ratio)
        exposed_balance = total_balance * configured_wallet_exposure

        if self.activate_size_above_exposed_balance_pct is not None:
            current_exposure = position.cost / (exposed_balance / 100)
            if current_exposure >= self.activate_size_above_exposed_balance_pct:
                logger.info(f'{symbol} {position_side.name}: REDUCE ALLOWED because there is a LONG position with an exposure of '
                            f'{current_exposure:.2f}%, which exceeds the set hedging threshold of '
                            f'{readable_pct(self.activate_size_above_exposed_balance_pct, 2)}')
                return True
            else:
                logger.debug(f'{symbol} {position_side.name}: REDUCE NOT ALLOWED because there is a LONG position with an exposure of '
                             f'{current_exposure:.2f}%, which is less than the set hedging threshold of '
                             f'{readable_pct(self.activate_size_above_exposed_balance_pct, 2)}')

        if self.activate_above_upnl_pct is not None:
            current_price = self.exchange_state.get_last_price(symbol)
            current_upnl = position.calculate_pnl_pct(price=current_price, leverage=self._symbol_leverage(symbol))

            if current_upnl < self.activate_above_upnl_pct:
                logger.info(f'{symbol} {position_side.name}: REDUCE ALLOWED as there is a LONG position with a upnl percentage of '
                            f'{current_upnl:.2f}%, which exceeds the set UPNL threshold of {self.activate_above_upnl_pct:.2f}%')
                return True
            else:
                logger.info(f'{symbol} {position_side.name}: REDUCE NOT ALLOWED as there is a LONG position with a upnl percentage of '
                            f'{current_upnl:.2f}%, which is less than the set UPNL threshold of {self.activate_above_upnl_pct:.2f}%')

        return False

    def _symbol_leverage(self, symbol: str):
        leverage = self.config.find_symbol_config(symbol).exchange_leverage
        if leverage == "MAX":
            leverage = self.exchange_state.get_symbol_information(symbol).max_leverage
        return leverage
