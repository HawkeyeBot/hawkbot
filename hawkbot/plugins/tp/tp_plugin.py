import logging
from dataclasses import dataclass, field
from typing import List, Dict

from hawkbot.core.config.bot_config import BotConfig
from hawkbot.core.data_classes import ExchangeState
from hawkbot.core.model import Position, SymbolInformation, Order, LimitOrder, OrderTypeIdentifier, Side, PositionSide, \
    OrderStatus, TimeInForce, StopLimitOrder, calculate_exit_price_at_pnl
from hawkbot.exceptions import InvalidConfigurationException, UnsupportedParameterException
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.utils import round_, round_dn, calc_min_qty, round_up, fill_optional_parameters

logger = logging.getLogger(__name__)


@dataclass
class StaticTpConfig:
    minimum_tp: float = field(default=None)
    maximum_tp_orders: int = field(default=None)
    tp_interval: float = field(default=None)


@dataclass
class TpConfig:
    enabled: bool = field(default_factory=lambda: True)
    # static TP grid
    minimum_tp: float = field(default=None)
    maximum_tp_orders: int = 1
    tp_interval: float = field(default=None)

    # exposure based static TP grid
    tp_when_wallet_exposure_at_pct: Dict[float, StaticTpConfig] = field(default=None)

    # UPNL based single TP order
    tp_at_upnl_pct: float = field(default=None)

    # trailing TP
    trailing_enabled: bool = field(default_factory=lambda: False)

    # price in pnl pct
    trailing_activation_upnl_pct: float = field(default=None)
    trailing_trigger_distance_upnl_pct: float = field(default=None)
    trailing_shift_threshold_upnl_pct: float = field(default=None)

    # distance in ratio from position price before starting trailing stop limit
    trailing_activation_distance_from_position_price: float = field(default_factory=lambda: None)
    # the distance from the current price at which to place the trigger price
    trailing_trigger_distance_from_current_price: float = field(default=None)
    # the distance in price steps from the trigger price to the execution price
    trailing_execution_distance_price_steps: int = field(default=None)
    # the difference between current price & trigger price that needs to be crossed before the order is shifted closed
    # to the current price (trailing)
    trailing_shift_threshold: float = field(default=None)

    allow_move_away: bool = field(default_factory=lambda: False)


class TpPlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange_state: ExchangeState = None  # Injected by framework
        self.config: BotConfig = None  # Injected by framework

    def parse_config(self, tp_dict: Dict) -> TpConfig:
        tp_config = TpConfig()
        if len(tp_dict.keys()) == 0:
            tp_config.enabled = False
            return tp_config

        optional_parameters = ['enabled',
                               'minimum_tp',
                               'maximum_tp_orders',
                               'tp_interval',
                               'tp_at_upnl_pct',
                               'trailing_activation_upnl_pct',
                               'trailing_trigger_distance_upnl_pct',
                               'trailing_shift_threshold_upnl_pct',
                               'trailing_activation_distance_from_position_price',
                               'trailing_trigger_distance_from_current_price',
                               'trailing_execution_distance_price_steps',
                               'trailing_shift_threshold',
                               'allow_move_away']

        fill_optional_parameters(target=tp_config, config=tp_dict, optional_parameters=optional_parameters)

        if 'tp_when_wallet_exposure_at_pct' in tp_dict:
            tp_config.tp_when_wallet_exposure_at_pct = {}
            tp_when_wallet_exposure_at_pct = tp_dict['tp_when_wallet_exposure_at_pct']
            for exposure_threshold, settings in tp_when_wallet_exposure_at_pct.items():
                tp_definition = StaticTpConfig()
                if 'minimum_tp' in settings:
                    tp_definition.minimum_tp = settings['minimum_tp']
                else:
                    raise InvalidConfigurationException('The parameter \'minimum_tp\' is mandatory in each '
                                                        '\'tp_when_wallet_exposure_at_pct\' definition')

                if 'maximum_tp_orders' in settings:
                    tp_definition.maximum_tp_orders = settings['maximum_tp_orders']
                else:
                    raise InvalidConfigurationException('The parameter \'maximum_tp_orders\' is mandatory in each '
                                                        '\'tp_when_wallet_exposure_at_pct\' definition')

                if 'tp_interval' in settings:
                    tp_definition.tp_interval = settings['tp_interval']
                else:
                    raise InvalidConfigurationException('The parameter \'tp_interval\' is mandatory in each '
                                                        '\'tp_when_wallet_exposure_at_pct\' definition')

                tp_config.tp_when_wallet_exposure_at_pct[float(exposure_threshold)] = tp_definition

        if 'trailing_enabled' in tp_dict:
            tp_config.trailing_enabled = tp_dict['trailing_enabled']
        else:
            tp_config.trailing_enabled = any(
                x is not None for x in [tp_config.trailing_activation_upnl_pct,
                                        tp_config.trailing_trigger_distance_upnl_pct,
                                        tp_config.trailing_shift_threshold_upnl_pct,
                                        tp_config.trailing_activation_distance_from_position_price,
                                        tp_config.trailing_trigger_distance_from_current_price,
                                        tp_config.trailing_execution_distance_price_steps,
                                        tp_config.trailing_shift_threshold])

        if tp_config.trailing_enabled is True:
            if tp_config.trailing_activation_distance_from_position_price is None and tp_config.trailing_activation_upnl_pct is None:
                raise InvalidConfigurationException(
                    'One of the parameters \"trailing_activation_distance_from_position_price\" or '
                    '\"trailing_activation_upnl_pct\" is missing from the TP configuration')
            if tp_config.trailing_trigger_distance_from_current_price is None and tp_config.trailing_trigger_distance_upnl_pct is None:
                raise InvalidConfigurationException('One of the parameters '
                                                    '\"trailing_trigger_distance_from_current_price\" or '
                                                    '\"trailing_trigger_distance_upnl_pct\" is missing from the TP '
                                                    'configuration')
            if tp_config.trailing_shift_threshold is None and tp_config.trailing_shift_threshold_upnl_pct is None:
                raise InvalidConfigurationException('One of the parameters \"trailing_shift_threshold\" or '
                                                    '\"trailing_shift_threshold_upnl_pct\" is missing from the TP '
                                                    'configuration')
            if tp_config.trailing_execution_distance_price_steps is None:
                raise InvalidConfigurationException('The parameter \"trailing_execution_distance_price_steps\" is '
                                                    'missing from the TP configuration')

        if tp_config.trailing_activation_distance_from_position_price is not None and \
                tp_config.trailing_activation_upnl_pct is not None:
            raise InvalidConfigurationException('Both parameters \"trailing_activation_distance_from_position_price\" '
                                                'and \"trailing_activation_upnl_pct\" are set, but the '
                                                'TP plugin does not support both parameters simultaneously. Please fix '
                                                'this by removing one of the two config sections.')
        if tp_config.trailing_trigger_distance_from_current_price is not None and \
                tp_config.trailing_trigger_distance_upnl_pct is not None:
            raise InvalidConfigurationException('Both parameters \"trailing_trigger_distance_from_current_price\" '
                                                'and \"trailing_trigger_distance_upnl_pct\" are set, but the '
                                                'TP plugin does not support both parameters simultaneously. Please fix '
                                                'this by removing one of the two config sections.')
        if tp_config.trailing_shift_threshold is not None and \
                tp_config.trailing_shift_threshold_upnl_pct is not None:
            raise InvalidConfigurationException('Both parameters \"trailing_shift_threshold\" and '
                                                '\"trailing_shift_threshold_upnl_pct\" are set, but the TP plugin does '
                                                'not support both parameters simultaneously. Please fix this by '
                                                'removing one of the two config sections.')

        if tp_config.tp_at_upnl_pct is not None and tp_config.minimum_tp is not None:
            raise InvalidConfigurationException(
                'Both parameters \"tp_at_upnl_pct\" and \"minimum_tp\" are set, but the '
                'TP plugin does not support both parameters simultaneously. Please fix '
                'this by removing one of the two config sections.')

        return tp_config

    def calculate_tp_orders(self,
                            position: Position,
                            position_side: PositionSide,
                            symbol_information: SymbolInformation,
                            current_price: float,
                            tp_config: TpConfig) -> List[Order]:
        if tp_config.enabled is False:
            return []
        if position.no_position():
            return []

        symbol = position.symbol

        all_tp_orders = []
        if tp_config.trailing_enabled is True:
            trailing_tp_order = self.calculate_trailing_tp_order(symbol=position.symbol,
                                                                 position_side=position_side,
                                                                 position=position,
                                                                 symbol_information=symbol_information,
                                                                 current_price=current_price,
                                                                 tp_config=tp_config)
            if trailing_tp_order is not None:
                all_tp_orders.append(trailing_tp_order)

        if len(all_tp_orders) > 0:
            return all_tp_orders

        if tp_config.tp_at_upnl_pct is not None:
            upnl_tp_order = self.calculate_upnl_tp_order(symbol=symbol,
                                                         position_side=position_side,
                                                         position=position,
                                                         symbol_information=symbol_information,
                                                         current_price=current_price,
                                                         tp_config=tp_config)
            if upnl_tp_order is not None:
                all_tp_orders.append(upnl_tp_order)
        else:
            static_tp_orders = self.calculate_normal_tp_orders(position=position,
                                                               position_side=position_side,
                                                               symbol_information=symbol_information,
                                                               current_price=current_price,
                                                               tp_config=tp_config)
            all_tp_orders.extend(static_tp_orders)

        return all_tp_orders

    def calculate_upnl_tp_order(self,
                                symbol: str,
                                position_side: PositionSide,
                                position: Position,
                                symbol_information: SymbolInformation,
                                current_price: float,
                                tp_config: TpConfig) -> Order:
        leverage = self.config.find_symbol_config(symbol).exchange_leverage
        tp_price = calculate_exit_price_at_pnl(position_size=position.position_size,
                                               leverage=leverage,
                                               entry_price=position.entry_price,
                                               target_pnl_pct=tp_config.tp_at_upnl_pct,
                                               is_long=position.is_long)

        if position.position_side == PositionSide.LONG:
            tp_price = max(tp_price, current_price)
        else:
            tp_price = min(tp_price, current_price)

        tp_price = round_(tp_price, symbol_information.price_step)

        return LimitOrder(order_type_identifier=OrderTypeIdentifier.TP,
                          symbol=symbol_information.symbol,
                          quantity=position.position_size,
                          side=position_side.decrease_side(),
                          position_side=position_side,
                          status=OrderStatus.NEW,
                          price=tp_price,
                          reduce_only=True,
                          initial_entry=False,
                          time_in_force=TimeInForce.GOOD_TILL_CANCELED)

    def calculate_trailing_tp_order(self,
                                    symbol: str,
                                    position_side: PositionSide,
                                    position: Position,
                                    symbol_information: SymbolInformation,
                                    current_price: float,
                                    tp_config: TpConfig) -> Order:
        open_order = self.exchange_state.open_trailing_tp_order(symbol=symbol, position_side=position_side)
        leverage = self.config.find_symbol_config(symbol).exchange_leverage
        if open_order is None:
            if position.position_side == PositionSide.LONG:
                if tp_config.trailing_activation_distance_from_position_price is not None:
                    activation_price = position.entry_price * (
                            1 + tp_config.trailing_activation_distance_from_position_price)
                else:
                    activation_price = calculate_exit_price_at_pnl(position_size=position.position_size,
                                                                   leverage=leverage,
                                                                   entry_price=position.entry_price,
                                                                   target_pnl_pct=tp_config.trailing_activation_upnl_pct,
                                                                   is_long=position.is_long)
                activation_price = round_(activation_price, symbol_information.price_step)
                if current_price <= activation_price:
                    logger.debug(
                        f'{symbol} {position_side.name}: Not placing trailing TP order because the current price '
                        f'{current_price} is below activation price {activation_price}')
                    return None
                price = activation_price - tp_config.trailing_execution_distance_price_steps * symbol_information.price_step
            else:
                if tp_config.trailing_activation_distance_from_position_price is not None:
                    activation_price = position.entry_price * (
                            1 - tp_config.trailing_activation_distance_from_position_price)
                else:
                    activation_price = calculate_exit_price_at_pnl(position_size=position.position_size,
                                                                   leverage=leverage,
                                                                   entry_price=position.entry_price,
                                                                   target_pnl_pct=tp_config.trailing_activation_upnl_pct,
                                                                   is_long=position.is_long)
                activation_price = round_(activation_price, symbol_information.price_step)
                if current_price >= activation_price:
                    logger.debug(
                        f'{symbol} {position_side.name}: Not placing trailing TP order because the current price '
                        f'{current_price} is above activation price {activation_price}')
                    return None
                price = activation_price - tp_config.trailing_execution_distance_price_steps * symbol_information.price_step

            if position_side == PositionSide.LONG:
                if tp_config.trailing_trigger_distance_upnl_pct is not None:
                    current_pnl = position.calculate_pnl_pct(price=current_price, leverage=leverage)
                    trigger_pnl = current_pnl - tp_config.trailing_activation_upnl_pct
                    trigger_price = calculate_exit_price_at_pnl(position_size=position.position_size,
                                                                leverage=leverage,
                                                                entry_price=position.entry_price,
                                                                target_pnl_pct=trigger_pnl,
                                                                is_long=position.is_long)

                else:
                    trigger_price = current_price * (1 - tp_config.trailing_trigger_distance_from_current_price)
                price = trigger_price - tp_config.trailing_execution_distance_price_steps * symbol_information.price_step
            else:
                if tp_config.trailing_trigger_distance_upnl_pct is not None:
                    current_pnl = position.calculate_pnl_pct(price=current_price, leverage=leverage)
                    trigger_pnl = current_pnl - tp_config.trailing_activation_upnl_pct
                    trigger_price = calculate_exit_price_at_pnl(position_size=position.position_size,
                                                                leverage=leverage,
                                                                entry_price=position.entry_price,
                                                                target_pnl_pct=trigger_pnl,
                                                                is_long=position.is_long)
                else:
                    trigger_price = current_price * (1 + tp_config.trailing_trigger_distance_from_current_price)
                    price = trigger_price + tp_config.trailing_execution_distance_price_steps * symbol_information.price_step
        else:
            if isinstance(open_order, LimitOrder):
                logger.info(
                    f'{symbol} {position_side.name}: A limit order of type TRAILING_TP was found, which means the trigger price has been hit. Return the placed limit order.')
                return open_order
            existing_trigger_price = open_order.stop_price
            if position_side == PositionSide.LONG:
                if tp_config.trailing_trigger_distance_upnl_pct is not None:
                    current_pnl = position.calculate_pnl_pct(price=current_price, leverage=leverage)
                    trigger_pnl = current_pnl - tp_config.trailing_trigger_distance_upnl_pct + tp_config.trailing_shift_threshold_upnl_pct
                    trigger_price = calculate_exit_price_at_pnl(position_size=position.position_size,
                                                                leverage=leverage,
                                                                entry_price=position.entry_price,
                                                                target_pnl_pct=trigger_pnl,
                                                                is_long=position.is_long)
                else:
                    trigger_price = current_price * (1 - tp_config.trailing_shift_threshold)
                if existing_trigger_price >= trigger_price:
                    logger.debug(f'{symbol} {position_side.name}: Maintaining existing trailing TP order because the '
                                 f'existing trigger price {existing_trigger_price} is equal or higher than the new '
                                 f'trigger price {trigger_price}')
                    return open_order
                price = trigger_price - tp_config.trailing_execution_distance_price_steps * symbol_information.price_step
            else:
                if tp_config.trailing_trigger_distance_upnl_pct is not None:
                    current_pnl = position.calculate_pnl_pct(price=current_price, leverage=leverage)
                    trigger_pnl = current_pnl - tp_config.trailing_trigger_distance_upnl_pct + tp_config.trailing_shift_threshold_upnl_pct
                    trigger_price = calculate_exit_price_at_pnl(position_size=position.position_size,
                                                                leverage=leverage,
                                                                entry_price=position.entry_price,
                                                                target_pnl_pct=trigger_pnl,
                                                                is_long=position.is_long)
                else:
                    trigger_price = current_price * (1 + tp_config.trailing_shift_threshold)
                if existing_trigger_price <= trigger_price:
                    logger.debug(f'{symbol} {position_side.name}: Maintaining existing trailing TP order because the '
                                 f'existing trigger price {existing_trigger_price} is equal or lower than the new '
                                 f'trigger price {trigger_price}')
                    return open_order
                price = trigger_price + tp_config.trailing_execution_distance_price_steps * symbol_information.price_step

        trigger_price = round_(number=trigger_price, step=symbol_information.price_step)
        price = round_(number=price, step=symbol_information.price_step)

        logger.info(f'{symbol} {position_side.name}: Placing trailing TP order triggering at {trigger_price} with '
                    f'price {price}, current price is {current_price}, position entry price is {position.entry_price}')

        return StopLimitOrder(order_type_identifier=OrderTypeIdentifier.TRAILING_TP,
                              symbol=symbol,
                              quantity=position.position_size,
                              side=position.decrease_side,
                              position_side=position_side,
                              status=OrderStatus.NEW,
                              price=price,
                              stop_price=trigger_price,
                              initial_entry=False,
                              time_in_force=TimeInForce.GOOD_TILL_CANCELED)

    def calculate_normal_tp_orders(self,
                                   position: Position,
                                   position_side: PositionSide,
                                   symbol_information: SymbolInformation,
                                   current_price: float,
                                   tp_config: TpConfig) -> List[Order]:
        minimum_tp = tp_config.minimum_tp
        maximum_tp_orders = tp_config.maximum_tp_orders
        tp_interval = tp_config.tp_interval

        if tp_config.tp_when_wallet_exposure_at_pct is not None:
            current_exposure_pct = self.calculate_exposure_of_total_exposure(symbol=position.symbol,
                                                                             position=position,
                                                                             position_side=position_side)
            candidate_levels = [level for level in tp_config.tp_when_wallet_exposure_at_pct if level <= current_exposure_pct]
            if len(candidate_levels) > 0:
                # find the highest applicable level to define the TP config
                level = max(candidate_levels)
                applicable_config = tp_config.tp_when_wallet_exposure_at_pct[level]
                logger.debug(f'{position.symbol} {position.position_side.name}: Based on current exposure percentage '
                             f'{current_exposure_pct} results in level specification {level}, which has TP config '
                             f'{applicable_config}')
                minimum_tp = applicable_config.minimum_tp
                maximum_tp_orders = applicable_config.maximum_tp_orders
                tp_interval = applicable_config.tp_interval
            else:
                logger.debug(f'{position.symbol} {position.position_side.name}: Current exposure percentage '
                             f'{current_exposure_pct} does not result in a level override, using default config')

        symbol = position.symbol
        logger.debug(f'{symbol} {position_side.name}: Current position price = {position.entry_price}, quantity = {position.position_size}, current price = {current_price}')

        orders = []
        if position.position_side == PositionSide.LONG:
            starting_price = position.entry_price * (1 + minimum_tp)
        elif position.position_side == PositionSide.SHORT:
            starting_price = position.entry_price * (1 - minimum_tp)
        else:
            raise UnsupportedParameterException(f'{symbol} {position_side.name}: Only position sides LONG and SHORT '
                                                f'are currently supported')
        starting_price = round_(number=starting_price, step=symbol_information.price_step)
        logger.debug(f'{symbol} {position_side.name}: Initial starting price = {starting_price}')

        starting_price = self.guarded_price(symbol=symbol, position_side=position_side, intended_price=starting_price, tp_config=tp_config)

        logger.debug(f'{symbol} {position_side.name}: Final starting price = {starting_price}')

        remaining_quantity = position.position_size

        tp_prices = []
        if (position.position_side == PositionSide.LONG and starting_price > current_price) or \
                (position.position_side == PositionSide.SHORT and starting_price < current_price):
            tp_prices = [starting_price]

        for i in range(1, maximum_tp_orders):
            logger.debug(f'{symbol} {position_side.name}: Calculating TP price {i}, current price = {current_price}')
            if position.position_side == PositionSide.LONG:
                target_price = starting_price * (1 + (i * tp_interval))
            else:
                target_price = starting_price * (1 - (i * tp_interval))
            rounded_price = round_(number=target_price, step=symbol_information.price_step)
            logger.debug(f'{symbol} {position_side.name}: Rounded price = {rounded_price}')

            if position.position_side == PositionSide.LONG and rounded_price > current_price \
                    and rounded_price <= symbol_information.highest_allowed_price(current_price):
                logger.debug(f'{symbol} {position_side.name}: Added TP price')
                tp_prices.append(rounded_price)
            if position.position_side == PositionSide.SHORT and rounded_price < current_price \
                    and rounded_price >= symbol_information.lowest_allowed_price(current_price):
                tp_prices.append(rounded_price)
                logger.debug(f'{symbol} {position_side.name}: Added TP price')

        if len(tp_prices) == 0:
            # This situation can occur if the bot has been off for a period and the TPs were cancelled manually.
            # In this case the current price is above any TP that would normally have been placed; in that case,
            # simply place 1 sell order at the current price
            single_tp_price = round_(number=current_price, step=symbol_information.price_step)
            logger.debug(f'{symbol} {position_side.name}: Adding TP at current price {current_price} because no TP price was added so far')
            single_tp_price = self.guarded_price(symbol=symbol, position_side=position_side, intended_price=single_tp_price, tp_config=tp_config)
            tp_prices.append(single_tp_price)

        qty_per_tp = round_dn(position.position_size / len(tp_prices), symbol_information.quantity_step)
        for tp_price in tp_prices:
            if remaining_quantity == 0.0:
                break
            min_tp_qty = calc_min_qty(price=tp_price,
                                      inverse=False,
                                      qty_step=symbol_information.quantity_step,
                                      min_qty=symbol_information.minimum_quantity,
                                      min_cost=symbol_information.minimal_sell_cost)
            tp_qty = max(qty_per_tp, min_tp_qty)
            if remaining_quantity < tp_qty:
                # in case the tp_qty is more than the remaining quantity, use the remaining quantity instead
                break
            new_order = LimitOrder(order_type_identifier=OrderTypeIdentifier.TP,
                                   symbol=symbol_information.symbol,
                                   quantity=tp_qty,
                                   side=position.decrease_side,
                                   position_side=position_side,
                                   status=OrderStatus.NEW,
                                   price=tp_price,
                                   reduce_only=True,
                                   initial_entry=False,
                                   time_in_force=TimeInForce.GOOD_TILL_CANCELED)
            orders.append(new_order)
            remaining_quantity -= tp_qty

        if remaining_quantity > 0.0:
            if len(orders) == 0:
                if position.position_side == PositionSide.LONG:
                    tp_price = min(tp_prices)
                else:
                    tp_price = max(tp_prices)
                logger.debug(f'{symbol} {position_side.name}: Detected partial TP, posting reduce-only order with '
                             f'remaining quantity {remaining_quantity} at price {tp_price}')

                new_order = LimitOrder(order_type_identifier=OrderTypeIdentifier.TP,
                                       symbol=symbol_information.symbol,
                                       quantity=remaining_quantity,
                                       side=position.decrease_side,
                                       position_side=position_side,
                                       status=OrderStatus.NEW,
                                       price=tp_price,
                                       reduce_only=True,
                                       initial_entry=False,
                                       time_in_force=TimeInForce.GOOD_TILL_CANCELED)
                orders.append(new_order)
            else:
                if position.position_side == PositionSide.LONG:
                    orders[0].quantity += remaining_quantity
                    orders[0].quantity = round_dn(orders[0].quantity, symbol_information.quantity_step)
                else:
                    orders[0].quantity += remaining_quantity
                    orders[0].quantity = round_up(orders[0].quantity, symbol_information.quantity_step)
        return orders

    def guarded_price(self, symbol: str, position_side: PositionSide, intended_price: float, tp_config: TpConfig):
        guarded_price = intended_price
        if tp_config.allow_move_away is False:
            if position_side == PositionSide.LONG:
                closest_tp_price = self.exchange_state.highest_tp_price_on_exchange(symbol=symbol, position_side=position_side)
                if closest_tp_price is not None:
                    guarded_price = min(intended_price, closest_tp_price)
                    logger.debug(f'{symbol} {position_side.name}: Closest TP price currently on the exchange is {closest_tp_price}')
            elif position_side == PositionSide.SHORT:
                closest_tp_price = self.exchange_state.lowest_tp_price_on_exchange(symbol=symbol, position_side=position_side)
                if closest_tp_price is not None:
                    guarded_price = max(intended_price, closest_tp_price)
                    logger.debug(f'{symbol} {position_side.name}: Closest TP price currently on the exchange is {closest_tp_price}')
        return guarded_price

    def calculate_exposure_of_total_exposure(self,
                                             symbol: str,
                                             position: Position,
                                             position_side: PositionSide):
        open_cost = self.exchange_state.position(symbol=symbol, position_side=position.position_side).cost

        total_balance = self.exchange_state.symbol_balance(symbol)
        position_side_config = self.config.find_position_side_config(symbol=symbol, position_side=position_side)
        wallet_exposure = position_side_config.wallet_exposure
        wallet_exposure_ratio = position_side_config.wallet_exposure_ratio
        configured_wallet_exposure = self.exchange_state.calculate_wallet_exposure_ratio(symbol=symbol,
                                                                                         wallet_exposure=wallet_exposure,
                                                                                         wallet_exposure_ratio=wallet_exposure_ratio)
        exposed_balance = total_balance * configured_wallet_exposure

        cost_pct_of_total_exposure = open_cost / (exposed_balance / 100)
        return cost_pct_of_total_exposure
