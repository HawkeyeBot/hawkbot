import logging
from dataclasses import dataclass, field
from typing import Dict

from hawkbot.core.config.bot_config import BotConfig
from hawkbot.core.data_classes import ExchangeState
from hawkbot.core.mode_processor import ModeProcessor
from hawkbot.core.model import PositionSide, Mode, OrderType, Position, Side, LimitOrder, OrderTypeIdentifier, \
    TimeInForce, OrderStatus, MarketOrder
from hawkbot.core.order_executor import OrderExecutor
from hawkbot.core.time_provider import TimeProvider
from hawkbot.exceptions import InvalidConfigurationException, UnsupportedParameterException
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.utils import calc_min_qty, round_dn, readable, get_percentage_difference, readable_pct, safe_round

logger = logging.getLogger(__name__)


@dataclass
class PositionSizeBased:
    initial_position_size_multipliedby_trigger: float = field(default=None)
    upnl_pct_threshold: float = field(default=None)


@dataclass
class GtfoConfig:
    enabled: bool = field(default=True)
    upnl_absolute_loss_threshold: float = field(default=None)
    upnl_pct_threshold: float = field(default=None)
    upnl_total_wallet_threshold: float = field(default=None)
    upnl_exposed_wallet_threshold: float = field(default=None)
    post_gtfo_mode: Mode = field(default=None)
    order_type: OrderType = field(default=None)
    position_reduce_order_size: float = field(default=None)
    position_size_based: PositionSizeBased = field(default=None)
    gtfo_execution_interval_ms: int = field(default=2000)


class GtfoPlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange_state: ExchangeState = None  # Injected by plugin loader
        self.config: BotConfig = None  # Injected by plugin loader
        self.order_executor: OrderExecutor = None  # Injected by plugin loader
        self.last_execution_time: Dict[str, Dict[PositionSide, int]] = {}
        self.time_provider: TimeProvider = None  # Injected by plugin loader
        self.mode_processor: ModeProcessor = None  # Injected by plugin loader

    def parse_config(self, gtfo_dict: Dict) -> GtfoConfig:
        gtfo_config = GtfoConfig()

        if len(gtfo_dict.keys()) == 0:
            gtfo_config.enabled = False
            return gtfo_config

        if 'enabled' in gtfo_dict:
            gtfo_config.enabled = gtfo_dict['enabled']

        if 'gtfo_execution_interval_ms' in gtfo_dict:
            gtfo_config.gtfo_execution_interval_ms = gtfo_dict['gtfo_execution_interval_ms']

        if 'upnl_absolute_loss_threshold' in gtfo_dict:
            gtfo_config.upnl_absolute_loss_threshold = gtfo_dict['upnl_absolute_loss_threshold']
            gtfo_config.upnl_absolute_loss_threshold = -abs(gtfo_config.upnl_absolute_loss_threshold)

        if 'upnl_pct_threshold' in gtfo_dict:
            gtfo_config.upnl_pct_threshold = gtfo_dict['upnl_pct_threshold']
            gtfo_config.upnl_pct_threshold = -abs(gtfo_config.upnl_pct_threshold)

        if 'upnl_exposed_wallet_threshold' in gtfo_dict:
            gtfo_config.upnl_exposed_wallet_threshold = gtfo_dict['upnl_exposed_wallet_threshold']
            gtfo_config.upnl_exposed_wallet_threshold = -abs(gtfo_config.upnl_exposed_wallet_threshold)

        if 'upnl_total_wallet_threshold' in gtfo_dict:
            gtfo_config.upnl_total_wallet_threshold = gtfo_dict['upnl_total_wallet_threshold']
            gtfo_config.upnl_total_wallet_threshold = -abs(gtfo_config.upnl_total_wallet_threshold)

        if 'order_type' in gtfo_dict:
            gtfo_config.order_type = OrderType[gtfo_dict['order_type']]
        if gtfo_config.order_type not in [OrderType.LIMIT, OrderType.MARKET]:
            raise InvalidConfigurationException('The parameter \'order_type\' is mandatory when specifying the gtfo '
                                                'plugin. Supported values are either \'LIMIT\' or \'MARKET\'')

        if 'post_gtfo_mode' in gtfo_dict:
            gtfo_config.post_gtfo_mode = Mode(gtfo_dict['post_gtfo_mode'])

        if 'position_reduce_order_size' in gtfo_dict:
            gtfo_config.position_reduce_order_size = gtfo_dict['position_reduce_order_size']
        else:
            raise InvalidConfigurationException('The parameter \'position_reduce_order_size\' is mandatory')

        if 'position_size_based_threshold' in gtfo_dict:
            position_size_based_dict = gtfo_dict['position_size_based_threshold']

            position_size_based = PositionSizeBased()
            position_size_based.initial_position_size_multipliedby_trigger = \
                position_size_based_dict['initial_position_size_multipliedby_trigger']
            position_size_based.upnl_pct_threshold = -abs(position_size_based_dict['upnl_pct_threshold'])

            gtfo_config.position_size_based = position_size_based

        if gtfo_config.position_reduce_order_size < 0 or gtfo_config.position_reduce_order_size > 1:
            raise InvalidConfigurationException(f'The parameter \'position_reduce_order_size\' must have a value '
                                                f'between 0 and 1, but is currently configured with '
                                                f'{gtfo_config.position_reduce_order_size}')

        return gtfo_config

    def run_gtfo(self,
                 symbol: str,
                 current_price: float,
                 gtfo_config: GtfoConfig,
                 position: Position,
                 exposed_balance: float,
                 wallet_balance: float) -> bool:
        if gtfo_config.enabled is False:
            return False

        if position.no_position():
            return False

        position_side = position.position_side

        if self.mode_processor.get_mode(symbol=symbol, position_side=position_side) in [Mode.PANIC]:
            return False

        self.last_execution_time.setdefault(symbol, {}).setdefault(position_side, 0)

        last_execution_time = self.last_execution_time[symbol][position_side]
        now = self.time_provider.get_utc_now_timestamp()
        time_since_last_execution = now - last_execution_time
        if time_since_last_execution < gtfo_config.gtfo_execution_interval_ms:
            logger.debug(f'{symbol} {position_side.name}: Skipping GTFO execution because last execution time '
                         f'{readable(last_execution_time)} is more than the configuration GTFO execution interval '
                         f'of {gtfo_config.gtfo_execution_interval_ms}')
            return self.exchange_state.has_open_gtfo_orders(symbol=symbol, position_side=position_side)
        else:
            logger.debug(f'{symbol} {position_side.name}: Checking GTFO execution because time since last '
                         f'execution {time_since_last_execution} exceeds configured execution interval '
                         f'{gtfo_config.gtfo_execution_interval_ms}')

        execute_gtfo = False

        if gtfo_config.upnl_absolute_loss_threshold is not None:
            upnl = position.calculate_pnl(price=current_price)
            if upnl < gtfo_config.upnl_absolute_loss_threshold:
                logger.info(f'{symbol} {position_side.name}: UPNL {upnl:.3f} at current price {current_price} '
                            f'exceeds configured UPNL threshold '
                            f'{readable_pct(gtfo_config.upnl_absolute_loss_threshold, 2)}, GTFO execute')
                execute_gtfo = True
            else:
                logger.debug(f'{symbol} {position_side.name}: UPNL {upnl:.3f} at current price {current_price} '
                             f'does not exceed configured UPNL threshold '
                             f'{readable_pct(gtfo_config.upnl_absolute_loss_threshold, 2)}, GTFO ignore')

        if gtfo_config.upnl_exposed_wallet_threshold is not None:
            upnl = position.calculate_pnl(price=current_price)
            upnl_wallet_diff = get_percentage_difference(previous_price=exposed_balance,
                                                         new_price=exposed_balance + upnl)
            if upnl_wallet_diff < gtfo_config.upnl_exposed_wallet_threshold:
                logger.info(f'{symbol} {position_side.name}: UPNL {upnl:.3f} is {readable_pct(upnl_wallet_diff, 2)} of '
                            f'exposed balance {exposed_balance:.3f} at current price {current_price}, which exceeds '
                            f'configured UPNL exposed wallet threshold '
                            f'{readable_pct(gtfo_config.upnl_exposed_wallet_threshold, 2)}, GTFO execute')
                execute_gtfo = True
            else:
                logger.debug(f'{symbol} {position_side.name}: UPNL {upnl:.3f} is {readable_pct(upnl_wallet_diff, 2)} of '
                             f'exposed balance {exposed_balance:.3f} at current price {current_price}, which does not '
                             f'exceed configured UPNL exposed wallet threshold '
                             f'{readable_pct(gtfo_config.upnl_exposed_wallet_threshold, 2)}, GTFO ignore')

        if gtfo_config.upnl_total_wallet_threshold is not None:
            upnl = position.calculate_pnl(price=current_price)
            upnl_wallet_diff = get_percentage_difference(previous_price=wallet_balance,
                                                         new_price=wallet_balance + upnl)
            if upnl_wallet_diff < gtfo_config.upnl_total_wallet_threshold:
                logger.info(f'{symbol} {position_side.name}: UPNL {upnl:.3f} is {readable_pct(upnl_wallet_diff, 2)} of '
                            f'total wallet balance {wallet_balance:.3f} at current price {current_price}, which '
                            f'exceeds configured UPNL total wallet threshold '
                            f'{readable_pct(gtfo_config.upnl_total_wallet_threshold, 2)}, GTFO execute')
                execute_gtfo = True
            else:
                logger.debug(f'{symbol} {position_side.name}: UPNL {upnl:.3f} is {readable_pct(upnl_wallet_diff, 2)} '
                             f'of total wallet balance {wallet_balance:.3f} at current price {current_price} which does '
                             f'not exceed configured UPNL total wallet threshold '
                             f'{readable_pct(gtfo_config.upnl_total_wallet_threshold, 2)}, GTFO ignore')

        if gtfo_config.upnl_pct_threshold is not None:
            leverage = self.config.find_symbol_config(symbol).exchange_leverage
            upnl_pct = position.calculate_pnl_pct(price=current_price, leverage=leverage)
            if upnl_pct < gtfo_config.upnl_pct_threshold:
                logger.info(f'{symbol} {position_side.name}: UPNL pct {upnl_pct} at current price '
                            f'{current_price} exceeds configured UPNL pct threshold '
                            f'{readable_pct(gtfo_config.upnl_pct_threshold, 2)}, GTFO execute')
                execute_gtfo = True
            else:
                logger.debug(f'{symbol} {position_side.name}: UPNL pct {upnl_pct} at current price '
                             f'{current_price} does not exceeds configured UPNL pct threshold '
                             f'{readable_pct(gtfo_config.upnl_pct_threshold, 2)}, GTFO ignore')

        if gtfo_config.position_size_based is not None:
            initial_entry_size = self.exchange_state.initial_entry_quantity(symbol=symbol,
                                                                            position_side=position_side)
            position_size_to_trigger_reducing = initial_entry_size * gtfo_config.position_size_based.initial_position_size_multipliedby_trigger

            logger.debug(f'{symbol} {position_side.name}: '
                         f'Position size = {position.position_size}, '
                         f'initial entry size = {initial_entry_size}, '
                         f'size threshold = {gtfo_config.position_size_based.initial_position_size_multipliedby_trigger}, '
                         f'position_size_to_trigger_reducing = {position_size_to_trigger_reducing}')
            if position.position_size >= position_size_to_trigger_reducing:
                logger.info(f'{symbol} {position_side.name}: Position size {position.position_size} exceeds the '
                            f'target size to start reducing {position_size_to_trigger_reducing} because position size '
                            f'{position.position_size} is bigger than '
                            f'{gtfo_config.position_size_based.initial_position_size_multipliedby_trigger} * initial '
                            f'entry size {initial_entry_size}, initiating GTFO check')

                leverage = self.config.find_symbol_config(symbol).exchange_leverage
                upnl_pct = position.calculate_pnl_pct(price=current_price, leverage=leverage)
                logger.debug(f'{symbol} {position_side.name}: '
                             f'Leverage = {leverage}, '
                             f'UPNL pct = {upnl_pct}, '
                             f'UPNL pct threshold = {gtfo_config.position_size_based.upnl_pct_threshold}, '
                             f'Entry price = {position.entry_price}, '
                             f'Current price = {current_price}')

                if upnl_pct <= gtfo_config.position_size_based.upnl_pct_threshold:
                    logger.info(f'{symbol} {position_side.name}: Position UPNL pct {upnl_pct} (current price = '
                                f'{current_price}, position price {position.entry_price}, position size '
                                f'{position.position_size}) exceeds the configured threshold of '
                                f'{gtfo_config.position_size_based.upnl_pct_threshold}, GTFO execute')
                    execute_gtfo = True
                else:
                    logger.debug(f'{symbol} {position_side.name}: Position UPNL pct {upnl_pct} does not exceed the '
                                 f'configured threshold of {gtfo_config.position_size_based.upnl_pct_threshold}, GTFO '
                                 f'ignore')
            else:
                logger.debug(f'{symbol} {position_side.name}: Position size {position.position_size} does not '
                             f'exceed the target size of {position_size_to_trigger_reducing} to start reducing, GTFO '
                             f'ignore')

        if execute_gtfo is True:
            if gtfo_config.order_type == OrderType.MARKET:
                self.place_market_exit_order(position=position, current_price=current_price, gtfo_config=gtfo_config)
            elif gtfo_config.order_type == OrderType.LIMIT:
                self.place_limit_exit_order(position=position, current_price=current_price, gtfo_config=gtfo_config)
            else:
                raise InvalidConfigurationException(f'{symbol} {position_side.name}: Encountered unsupported '
                                                    f'order type {gtfo_config.order_type}')

            if gtfo_config.post_gtfo_mode is not None:
                self.bot.mode_processor.set_mode(symbol=symbol,
                                                 position_side=position_side,
                                                 mode=gtfo_config.post_gtfo_mode)

            self.last_execution_time[symbol][position_side] = now
        else:
            open_gtfo_orders = self.exchange_state.open_gtfo_orders(symbol=symbol, position_side=position_side)
            if len(open_gtfo_orders) > 0:
                # When aborting GTFO, give it a cool-off period to prevent fast looping
                self.last_execution_time[symbol][position_side] = now
                self.order_executor.cancel_orders(open_gtfo_orders)

        return execute_gtfo

    def place_market_exit_order(self, position: Position, current_price: float, gtfo_config: GtfoConfig):
        symbol = position.symbol
        position_side = position.position_side
        symbol_information = self.exchange_state.get_symbol_information(symbol)
        position_size = position.position_size * gtfo_config.position_reduce_order_size

        try:
            if position_side == PositionSide.LONG:
                min_cost = symbol_information.minimal_sell_cost
            elif position_side == PositionSide.SHORT:
                min_cost = symbol_information.minimal_buy_cost
            else:
                raise UnsupportedParameterException(f'{symbol}: Encountered unsupported position_side {position_side}')

            minimum_quantity = calc_min_qty(price=current_price,
                                            inverse=False,
                                            qty_step=symbol_information.quantity_step,
                                            min_qty=symbol_information.minimum_quantity,
                                            min_cost=min_cost)
            current_sell_quantity = round_dn(position_size, step=symbol_information.quantity_step)
            if current_sell_quantity < minimum_quantity:
                logger.debug(f'{symbol} {position_side.name}: Unable to sell quantity of {current_sell_quantity} '
                             f'because it is less than the minimum quantity of {minimum_quantity}')
            gtfo_order = MarketOrder(order_type_identifier=OrderTypeIdentifier.GTFO,
                                     symbol=symbol,
                                     quantity=current_sell_quantity,
                                     side=Side.SELL if position_side == PositionSide.LONG else Side.BUY,
                                     position_side=position_side,
                                     status=OrderStatus.NEW)
            self.order_executor.create_order(gtfo_order)
        except:
            logger.exception(f'{symbol} {position_side.name}: Failed to place market order to close existing position '
                             f'with size {position_size}')

    def place_limit_exit_order(self, position: Position, current_price: float, gtfo_config: GtfoConfig):
        symbol = position.symbol
        position_side = position.position_side
        logger.info(f'{symbol} {position_side.name}: Executing GTFO limit order with tick price {current_price}')

        symbol_information = self.exchange_state.get_symbol_information(symbol)
        position_size = position.position_size * gtfo_config.position_reduce_order_size
        if position_side == PositionSide.LONG:
            price = current_price
            price += 2 * symbol_information.price_step
        elif position_side == PositionSide.SHORT:
            price = current_price
            price -= 2 * symbol_information.price_step
        else:
            raise UnsupportedParameterException(f'{symbol}: Encountered unsupported position_side {position_side}')

        try:
            if position_side == PositionSide.LONG:
                min_cost = symbol_information.minimal_sell_cost
            elif position_side == PositionSide.SHORT:
                min_cost = symbol_information.minimal_buy_cost
            else:
                raise UnsupportedParameterException(f'{symbol}: Encountered unsupported position_side {position_side}')

            minimum_quantity = calc_min_qty(price=price,
                                            inverse=False,
                                            qty_step=symbol_information.quantity_step,
                                            min_qty=symbol_information.minimum_quantity,
                                            min_cost=min_cost)
            current_sell_quantity = round_dn(position_size, step=symbol_information.quantity_step)
            if current_sell_quantity < minimum_quantity:
                logger.debug(f'{symbol} {position_side.name}: Unable to sell quantity of {current_sell_quantity} '
                             f'because it is less than the minimum quantity of {minimum_quantity}')

            gtfo_order = LimitOrder(order_type_identifier=OrderTypeIdentifier.GTFO,
                                    symbol=symbol,
                                    quantity=current_sell_quantity,
                                    side=Side.SELL if position_side == PositionSide.LONG else Side.BUY,
                                    position_side=position_side,
                                    status=OrderStatus.NEW,
                                    price=safe_round(price),
                                    initial_entry=False,
                                    time_in_force=TimeInForce.POST_ONLY)

            open_gtfo_orders = self.exchange_state.open_gtfo_orders(symbol=symbol, position_side=position_side)
            if gtfo_order not in open_gtfo_orders:
                if len(open_gtfo_orders) > 0:
                    self.order_executor.cancel_orders(open_gtfo_orders)
                self.order_executor.create_order(gtfo_order)
        except:
            logger.exception(f'{symbol} {position_side.name}: Failed to place limit order to close existing position '
                             f'with size {position_size} at price {price}')
