import logging
from dataclasses import field, dataclass
from typing import List, Dict

from hawkbot.core.data_classes import ExchangeState
from hawkbot.core.model import Position, SymbolInformation, Order, StopLimitOrder, OrderTypeIdentifier, Side, \
    PositionSide, Mode, OrderType, StopLossMarketOrder, TimeInForce
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.utils import round_, round_dn, calc_min_qty, round_up

logger = logging.getLogger(__name__)


@dataclass
class StoplossConfig:
    enabled: bool = field(default=True)
    upnl_exposed_wallet_trigger_threshold: float = field(default=None)
    upnl_total_wallet_trigger_threshold: float = field(default=None)
    stoploss_price: float = field(default=None)
    position_trigger_distance: float = field(default=None)
    last_entry_trigger_distance: float = field(default=None)
    wallet_exposure_threshold: float = field(default=None)
    relative_wallet_exposure_threshold: float = field(default=None)
    stoploss_at_inverse_tp: bool = field(default=None)
    stoploss_sell_distance_price_steps: int = 3
    grid_range: float = field(default=None)
    nr_orders: int = 1
    post_stoploss_mode: Mode = field(default=None)
    custom_trigger_price_enabled: bool = field(default=False)
    order_type: OrderType = field(default=None)
    trailing_enabled: bool = field(default=False)
    trailing_distance: float = field(default=None)
    trailing_threshold: float = field(default=None)


class StoplossPlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange_state: ExchangeState = None  # Injected by loader

    def parse_config(self, stoploss_dict: Dict) -> StoplossConfig:
        stoploss_config = StoplossConfig()

        if len(stoploss_dict.keys()) == 0:
            stoploss_config.enabled = False
            return stoploss_config

        optional_parameters = ['enabled',
                               'stoploss_price',
                               'position_trigger_distance',
                               'stoploss_sell_distance_price_steps',
                               'grid_range',
                               'nr_orders',
                               'post_stoploss_mode',
                               'custom_trigger_price_enabled',
                               'last_entry_trigger_distance',
                               'wallet_exposure_threshold',
                               'relative_wallet_exposure_threshold',
                               'stoploss_at_inverse_tp',
                               'trailing_enabled',
                               'trailing_distance',
                               'trailing_threshold']
        for optional_parameter in optional_parameters:
            if optional_parameter in stoploss_dict:
                setattr(stoploss_config, optional_parameter, stoploss_dict[optional_parameter])

        if 'upnl_exposed_wallet_trigger_threshold' in stoploss_dict:
            stoploss_config.upnl_exposed_wallet_trigger_threshold = abs(
                stoploss_dict['upnl_exposed_wallet_trigger_threshold'])

        if 'upnl_total_wallet_trigger_threshold' in stoploss_dict:
            stoploss_config.upnl_total_wallet_trigger_threshold = abs(
                stoploss_dict['upnl_total_wallet_trigger_threshold'])

        if 'order_type' in stoploss_dict:
            stoploss_config.order_type = OrderType[stoploss_dict['order_type']]
            if stoploss_config.order_type not in [OrderType.STOP, OrderType.STOP_MARKET]:
                raise InvalidConfigurationException(f'The stoploss order_type {stoploss_dict["order_type"]} is not '
                                                    f'supported; only the values \'STOP\' (limit order) and '
                                                    f'\'STOP_MARKET\' (market order) are supported')
        else:
            raise InvalidConfigurationException('The required parameter \'order_type\' is not specified. Please '
                                                'specify the parameter with either \'STOP\' or \'STOP_MARKET\'')

        if stoploss_config.nr_orders <= 0:
            raise InvalidConfigurationException("The parameter 'nr_orders' has to be a number bigger than 0. If you "
                                                "intend to disable the stoploss functionality, please set the "
                                                "parameter \'enabled\' to false for the stoploss plugin")

        if stoploss_config.stoploss_price is None \
                and stoploss_config.upnl_exposed_wallet_trigger_threshold is None \
                and stoploss_config.upnl_total_wallet_trigger_threshold is None \
                and stoploss_config.grid_range is None \
                and stoploss_config.position_trigger_distance is None \
                and stoploss_config.last_entry_trigger_distance is None \
                and stoploss_config.stoploss_at_inverse_tp is None \
                and stoploss_config.custom_trigger_price_enabled is False:
            raise InvalidConfigurationException(
                "None of the parameters 'stoploss_price', "
                "'upnl_exposed_wallet_trigger_threshold', 'upnl_total_wallet_trigger_threshold', "
                "'position_trigger_distance', 'last_entry_trigger_distance', 'stoploss_at_inverse_tp' "
                "and 'grid_range' are not set; one of these is required when using the stoploss plugin, "
                "or the parameter \'custom_trigger_price_enabled\' needs to be set to "
                "true to allow the strategy to provide a custom trigger price")

        if stoploss_config.stoploss_price is not None \
                and stoploss_config.upnl_exposed_wallet_trigger_threshold is not None:
            raise InvalidConfigurationException("The parameter 'stoploss_price' and the parameter "
                                                "'upnl_exposed_wallet_trigger_threshold' are both set; only one of "
                                                "these is allowed")

        if stoploss_config.stoploss_price is not None \
                and stoploss_config.upnl_total_wallet_trigger_threshold is not None:
            raise InvalidConfigurationException("The parameter 'stoploss_price' and the parameter "
                                                "'upnl_total_wallet_trigger_threshold' are both set; only one of these "
                                                "is allowed")

        if stoploss_config.upnl_exposed_wallet_trigger_threshold is not None \
                and stoploss_config.upnl_total_wallet_trigger_threshold is not None:
            raise InvalidConfigurationException(
                "The parameter 'upnl_exposed_wallet_trigger_threshold' and the parameter "
                "'upnl_total_wallet_trigger_threshold' are both set; only one of these is "
                "allowed")

        return stoploss_config

    def calculate_stoploss_orders(self,
                                  position: Position,
                                  position_side: PositionSide,
                                  symbol_information: SymbolInformation,
                                  current_price: float,
                                  wallet_balance: float,
                                  exposed_balance: float,
                                  wallet_exposure: float,
                                  stoploss_config: StoplossConfig,
                                  custom_trigger_price: float = None) -> List[Order]:
        symbol = symbol_information.symbol
        if stoploss_config.enabled is False:
            return []
        if position.no_position():
            return []

        existing_stoploss_orders = self.exchange_state.open_stoploss_orders(symbol=symbol,
                                                                            position_side=position.position_side)
        calculate_trailing_price = self._should_calculate_trailing_price(symbol=symbol,
                                                                         position_side=position_side,
                                                                         position=position,
                                                                         stoploss_config=stoploss_config,
                                                                         existing_stoploss_orders=existing_stoploss_orders)
        if calculate_trailing_price:
            first_trigger_price = self._calculate_first_trailing_trigger_price(position_side=position.position_side,
                                                                               current_price=current_price,
                                                                               trigger_distance=stoploss_config.trailing_distance,
                                                                               symbol_information=symbol_information,
                                                                               existing_stoploss_orders=existing_stoploss_orders)
        elif stoploss_config.stoploss_at_inverse_tp is not None and self.exchange_state.has_open_position(symbol=symbol, position_side=position_side.inverse()):
            open_tp_orders = self.exchange_state.open_tp_orders(symbol=symbol, position_side=position_side.inverse())
            if len(open_tp_orders) > 0:
                if position_side == PositionSide.LONG:
                    # inverse will be short orders, so first TP order is max of TP orders
                    raw_sl_price = max([order.price for order in open_tp_orders])
                    first_trigger_price = round_(number=raw_sl_price - symbol_information.price_step, step=symbol_information.price_step)  # trigger at TP price - 1 unit
                elif position_side == PositionSide.SHORT:
                    # inverse will be long orders, so first TP order is min of TP orders
                    raw_sl_price = min([order.price for order in open_tp_orders])
                    first_trigger_price = round_(number=raw_sl_price, step=symbol_information.price_step)
                # sell_price = round_(number=raw_sl_price, step=symbol_information.price_step)
            else:
                return []
        elif custom_trigger_price is not None:
            first_trigger_price = round_(number=custom_trigger_price,
                                         step=symbol_information.price_step)
        elif stoploss_config.stoploss_price is not None:
            first_trigger_price = round_(number=stoploss_config.stoploss_price,
                                         step=symbol_information.price_step)
        elif stoploss_config.position_trigger_distance is not None:
            first_trigger_price = self._calculate_first_trigger_price(position_side=position.position_side,
                                                                      reference_price=position.entry_price,
                                                                      trigger_distance=stoploss_config.position_trigger_distance,
                                                                      symbol_information=symbol_information,
                                                                      current_price=current_price)
        elif stoploss_config.last_entry_trigger_distance is not None:
            open_entry_orders = self.exchange_state.open_entry_orders(symbol=symbol, position_side=position_side)
            if position.position_side == PositionSide.LONG:
                if len(open_entry_orders) > 0:
                    last_filled_price = min([order.price for order in open_entry_orders])
                else:
                    last_filled_price = self.exchange_state.min_filled_trade_price(symbol=symbol,
                                                                                   position_side=position_side,
                                                                                   order_type_identifiers=[
                                                                                       OrderTypeIdentifier.INITIAL_ENTRY,
                                                                                       OrderTypeIdentifier.ENTRY,
                                                                                       OrderTypeIdentifier.DCA,
                                                                                       OrderTypeIdentifier.UNKNOWN,
                                                                                       OrderTypeIdentifier.WEB])
            else:
                if len(open_entry_orders) > 0:
                    last_filled_price = max([order.price for order in open_entry_orders])
                else:
                    last_filled_price = self.exchange_state.max_filled_trade_price(symbol=symbol,
                                                                                   position_side=position_side,
                                                                                   order_type_identifiers=[
                                                                                       OrderTypeIdentifier.INITIAL_ENTRY,
                                                                                       OrderTypeIdentifier.ENTRY,
                                                                                       OrderTypeIdentifier.DCA,
                                                                                       OrderTypeIdentifier.UNKNOWN,
                                                                                       OrderTypeIdentifier.WEB])

            if last_filled_price is not None:
                if stoploss_config.wallet_exposure_threshold is not None:
                    current_wallet_exposure = position.cost / wallet_balance
                    if current_wallet_exposure >= stoploss_config.wallet_exposure_threshold:
                        first_trigger_price = self._calculate_first_trigger_price(position_side=position.position_side,
                                                                                  reference_price=last_filled_price,
                                                                                  trigger_distance=stoploss_config.last_entry_trigger_distance,
                                                                                  symbol_information=symbol_information,
                                                                                  current_price=current_price)
                    else:
                        logger.debug(f'{symbol} {position_side.name}: Not activating stoploss because the current '
                                     f'wallet exposure {current_wallet_exposure} (position cost {position.cost} / '
                                     f'wallet balance {wallet_balance}) is not equal or greater than the '
                                     f'wallet_exposure_threshold {stoploss_config.wallet_exposure_threshold}')
                        return []
                elif stoploss_config.relative_wallet_exposure_threshold is not None:
                    current_wallet_exposure = position.cost / wallet_balance
                    relative_wallet_exposure = current_wallet_exposure / wallet_exposure
                    if relative_wallet_exposure >= stoploss_config.relative_wallet_exposure_threshold:
                        first_trigger_price = self._calculate_first_trigger_price(position_side=position.position_side,
                                                                                  reference_price=last_filled_price,
                                                                                  trigger_distance=stoploss_config.last_entry_trigger_distance,
                                                                                  symbol_information=symbol_information,
                                                                                  current_price=current_price)
                    else:
                        logger.debug(f'{symbol} {position_side.name}: Not activating stoploss because the current '
                                     f'relative wallet exposure {relative_wallet_exposure} (current wallet exposure = '
                                     f'{current_wallet_exposure}, total wallet exposure = {wallet_exposure}) is '
                                     f'not equal or greater than the wallet_exposure_threshold '
                                     f'{stoploss_config.wallet_exposure_threshold}')
                        return []
                else:
                    first_trigger_price = self._calculate_first_trigger_price(position_side=position.position_side,
                                                                              reference_price=last_filled_price,
                                                                              trigger_distance=stoploss_config.last_entry_trigger_distance,
                                                                              symbol_information=symbol_information,
                                                                              current_price=current_price)
            else:
                logger.debug(f'{symbol} {position_side.name}: Not activating stoploss because the last filled price '
                             f'is None')
                return []
        else:
            open_dca_orders = self.exchange_state.open_dca_orders(symbol=symbol, position_side=position_side)
            first_trigger_price = self._calculate_first_trigger_price_from_dca(position=position,
                                                                               symbol_information=symbol_information,
                                                                               current_price=current_price,
                                                                               wallet_balance=wallet_balance,
                                                                               exposed_wallet_balance=exposed_balance,
                                                                               dca_orders=open_dca_orders,
                                                                               stoploss_config=stoploss_config)
            if first_trigger_price is None:
                return []

        trigger_prices = self.calculate_trigger_prices(symbol=symbol,
                                                       position_side=position.position_side,
                                                       trigger_price=first_trigger_price,
                                                       grid_range=stoploss_config.grid_range,
                                                       nr_orders=stoploss_config.nr_orders,
                                                       price_step=symbol_information.price_step,
                                                       current_price=current_price)

        # create the stoploss orders
        stoploss_orders = self.create_stoploss_grid_orders(position=position,
                                                           position_side=position_side,
                                                           stoploss_sell_distance_price_steps=stoploss_config.stoploss_sell_distance_price_steps,
                                                           symbol=symbol,
                                                           symbol_information=symbol_information,
                                                           trigger_prices=trigger_prices,
                                                           order_type=stoploss_config.order_type)

        # ensure the entire position is covered by stoploss
        self.fill_remaining_quantity(first_trigger_price=first_trigger_price,
                                     position=position,
                                     position_side=position_side,
                                     stoploss_orders=stoploss_orders,
                                     stoploss_sell_distance_price_steps=stoploss_config.stoploss_sell_distance_price_steps,
                                     symbol=symbol,
                                     symbol_information=symbol_information,
                                     order_type=stoploss_config.order_type)

        return stoploss_orders

    def _calculate_first_trailing_trigger_price(self, position_side: PositionSide,
                                                current_price: float,
                                                trigger_distance: float,
                                                symbol_information: SymbolInformation,
                                                existing_stoploss_orders: List[Order]):
        if position_side == PositionSide.LONG:
            first_trigger_price = round_(number=current_price * (1 - trigger_distance),
                                         step=symbol_information.price_step)
            highest_existing_price = max([o.stop_price for o in existing_stoploss_orders])
            final_trigger_price = max(highest_existing_price, first_trigger_price)
            logger.debug(f'{symbol_information.symbol} {position_side.name}: Trailing first trigger price is '
                         f'{final_trigger_price}, based on current highest stoploss price {highest_existing_price} and '
                         f'calculated first trigger price {first_trigger_price} based on current price {current_price} '
                         f'and trigger distance {trigger_distance}')
            return final_trigger_price
        else:
            first_trigger_price = round_(number=current_price * (1 + trigger_distance),
                                         step=symbol_information.price_step)
            lowest_existing_price = min([o.stop_price for o in existing_stoploss_orders])
            final_trigger_price = min(lowest_existing_price, first_trigger_price)
            logger.debug(
                f'{symbol_information.symbol} {position_side.name}: Trailing first trigger price is '
                f'{final_trigger_price}, based on current lowest stoploss price {lowest_existing_price} and calculated '
                f'first trigger price {first_trigger_price} based on current price {current_price} and trigger '
                f'distance {trigger_distance}')
            return final_trigger_price

    def _calculate_first_trigger_price(self,
                                       position_side: PositionSide,
                                       reference_price: float,
                                       trigger_distance: float,
                                       symbol_information: SymbolInformation,
                                       current_price: float):
        symbol = symbol_information.symbol
        if position_side == PositionSide.LONG:
            trigger_price = round_(number=reference_price * (1 - trigger_distance), step=symbol_information.price_step)
            if trigger_price > current_price:
                new_trigger_price = round_(number=current_price * (1 - trigger_distance),
                                           step=symbol_information.price_step)
                logger.warning(f'{symbol} {position_side.name}: The trigger price {trigger_price} is higher than the '
                               f'current price {current_price}, forcing first trigger price to be at current price - '
                               f'trigger distance {trigger_distance} = {new_trigger_price}')
                trigger_price = new_trigger_price
        else:
            trigger_price = round_(number=reference_price * (1 + trigger_distance),
                                   step=symbol_information.price_step)
            if trigger_price < current_price:
                new_trigger_price = round_(number=current_price * (1 + trigger_distance),
                                           step=symbol_information.price_step)
                logger.warning(f'{symbol} {position_side.name}: The trigger price {trigger_price} is lower than the '
                               f'current price {current_price}, forcing first trigger price to be at current price + '
                               f'trigger distance {trigger_distance} = {new_trigger_price}')
                trigger_price = new_trigger_price

        return trigger_price

    def _calculate_first_trigger_price_from_dca(self,
                                                position: Position,
                                                symbol_information: SymbolInformation,
                                                current_price: float,
                                                wallet_balance: float,
                                                exposed_wallet_balance: float,
                                                dca_orders: List[Order],
                                                stoploss_config: StoplossConfig) -> float:
        max_allowed_loss = self.determine_maximum_allowed_loss(wallet_balance=wallet_balance,
                                                               exposed_balance=exposed_wallet_balance,
                                                               stoploss_config=stoploss_config)
        position_post_dca = self.calculate_position_after_dcas(position=position, dca_orders=dca_orders)
        if position.position_side == PositionSide.LONG:
            # Stoploss price = position price - (max allowed loss / position size)
            sell_price = position_post_dca.entry_price - (max_allowed_loss / position_post_dca.position_size)
            if sell_price <= 0:
                logger.info(f'{position.symbol} {position.position_side.name}: Stoploss price at allowed loss {max_allowed_loss} will be {sell_price} which is less than 0, not '
                            f'placing stoploss (yet)')
                return None
            first_trigger_price = sell_price + (stoploss_config.stoploss_sell_distance_price_steps * symbol_information.price_step)
            if current_price > first_trigger_price:
                first_trigger_price = min(first_trigger_price, current_price)
        else:
            sell_price = position_post_dca.entry_price + (max_allowed_loss / position_post_dca.position_size)
            first_trigger_price = sell_price - (stoploss_config.stoploss_sell_distance_price_steps * symbol_information.price_step)
            if sell_price > current_price * 2:
                logger.info(f'{position.symbol} {position.position_side.name}: Stoploss price at allowed loss {max_allowed_loss} will be {sell_price} which is more than twice '
                            f'the current price {current_price}, not placing stoploss (yet)')
                return None
            if current_price < first_trigger_price:
                first_trigger_price = max(first_trigger_price, current_price)

        first_trigger_price = round_(number=first_trigger_price,
                                     step=symbol_information.price_step)
        return first_trigger_price

    def determine_maximum_allowed_loss(self,
                                       wallet_balance: float,
                                       exposed_balance: float,
                                       stoploss_config: StoplossConfig) -> float:
        if stoploss_config.upnl_exposed_wallet_trigger_threshold is not None:
            return exposed_balance * stoploss_config.upnl_exposed_wallet_trigger_threshold
        if stoploss_config.upnl_total_wallet_trigger_threshold is not None:
            return wallet_balance * stoploss_config.upnl_total_wallet_trigger_threshold

    def calculate_position_after_dcas(self, position: Position, dca_orders: List[Order]) -> Position:
        position_side = position.position_side
        position_entry_price = position.entry_price if position.entry_price is not None else 0
        position_size = position.position_size if position.position_size is not None else 0
        if position_side == PositionSide.LONG:
            dca_orders.sort(key=lambda o: o.price, reverse=True)
        else:
            dca_orders.sort(key=lambda o: o.price)

        for dca_order in dca_orders:
            new_position_size = position_size + dca_order.quantity

            position_entry_price = position_entry_price * (position_size / new_position_size) + dca_order.price * (
                    dca_order.quantity / new_position_size)
            position_size = new_position_size

        return Position(position_size=position_size, entry_price=position_entry_price)

    def fill_remaining_quantity(self,
                                first_trigger_price: float,
                                position: Position,
                                position_side: PositionSide,
                                stoploss_orders: List[Order],
                                stoploss_sell_distance_price_steps: float,
                                symbol: str,
                                symbol_information: SymbolInformation,
                                order_type: OrderType):

        total_quantity_orders = 0.0
        if len(stoploss_orders) == 1 and stoploss_orders[0].close_position is True:
            # close-position is used
            return
        elif len(stoploss_orders) > 0:
            total_quantity_orders = sum([order.quantity for order in stoploss_orders])
        if total_quantity_orders < position.position_size:
            if len(stoploss_orders) == 0:
                side = position_side.decrease_side()
                if order_type == OrderType.STOP:
                    if position_side == PositionSide.LONG:
                        sell_price = first_trigger_price - (stoploss_sell_distance_price_steps * symbol_information.price_step)
                        sell_price = round_dn(sell_price, symbol_information.price_step)
                    else:
                        sell_price = first_trigger_price + (stoploss_sell_distance_price_steps * symbol_information.price_step)
                        sell_price = round_up(sell_price, symbol_information.price_step)

                    new_stoploss_order = StopLimitOrder(order_type_identifier=OrderTypeIdentifier.STOPLOSS,
                                                        symbol=symbol,
                                                        quantity=position.position_size,
                                                        side=side,
                                                        position_side=position_side,
                                                        price=sell_price,
                                                        stop_price=first_trigger_price)
                    stoploss_orders.append(new_stoploss_order)
                elif order_type == OrderType.STOP_MARKET:
                    new_stoploss_order = StopLossMarketOrder(order_type_identifier=OrderTypeIdentifier.STOPLOSS,
                                                             symbol=symbol,
                                                             quantity=position.position_size,
                                                             stop_price=first_trigger_price,
                                                             side=side,
                                                             position_side=position_side)

                    stoploss_orders.append(new_stoploss_order)
                else:
                    raise InvalidConfigurationException(f'{symbol} {position_side.name}: The order-type '
                                                        f'{order_type.name} is not supported for a stoploss')
            else:
                # find first stoploss order to add the remaining quantity to
                first_stoploss_order = stoploss_orders[0]
                remaining_quantity = position.position_size - total_quantity_orders
                first_stoploss_order.quantity += remaining_quantity

    def create_stoploss_grid_orders(self,
                                    position: Position,
                                    position_side: PositionSide,
                                    stoploss_sell_distance_price_steps: float,
                                    symbol: str,
                                    symbol_information: SymbolInformation,
                                    trigger_prices: List[float],
                                    order_type: OrderType) -> List[Order]:
        stoploss_orders = []
        quantity_per_order = position.position_size / len(trigger_prices)
        quantity_per_order = round_dn(quantity_per_order, symbol_information.quantity_step)
        logger.debug(f'{symbol} {position_side.name}: Creating stoploss order(s) for {len(trigger_prices)} trigger prices. Total quantity to create stoploss order(s) for is '
                    f'{position.position_size}. Quantity per order = {quantity_per_order}')
        if position.position_side == PositionSide.LONG:
            min_cost = symbol_information.minimal_sell_cost
        else:
            min_cost = symbol_information.minimal_buy_cost
        for trigger_price in trigger_prices:
            min_qty = calc_min_qty(price=trigger_price,
                                   inverse=False,
                                   qty_step=symbol_information.quantity_step,
                                   min_qty=symbol_information.minimum_quantity,
                                   min_cost=min_cost)
            if quantity_per_order < min_qty:
                logger.debug(f'{symbol} {position_side.name}: Rounded quantity {quantity_per_order} is less than '
                             f'minimum quantity {min_qty}, skipping quantity for stoploss. Any remaining quantity will '
                             f'be gathered later in the calculation.')
                continue

            side = Side.SELL if position.position_side == PositionSide.LONG else Side.BUY
            if order_type == OrderType.STOP:
                if position.position_side == PositionSide.LONG:
                    sell_price = trigger_price - (stoploss_sell_distance_price_steps * symbol_information.price_step)
                    sell_price = round_dn(sell_price, symbol_information.price_step)
                else:
                    sell_price = trigger_price + (stoploss_sell_distance_price_steps * symbol_information.price_step)
                    sell_price = round_up(sell_price, symbol_information.price_step)

                new_stoploss_order = StopLimitOrder(order_type_identifier=OrderTypeIdentifier.STOPLOSS,
                                                    symbol=symbol,
                                                    quantity=quantity_per_order,
                                                    side=side,
                                                    position_side=position_side,
                                                    price=sell_price,
                                                    stop_price=trigger_price,
                                                    time_in_force=TimeInForce.POST_ONLY)
                if len(trigger_prices) == 1:
                    new_stoploss_order.close_position = True
                    logger.debug(f'{symbol} {position_side.name}: Setting close position')
                else:
                    logger.debug(f'{symbol} {position_side.name}: Not setting close position')

                logger.debug(f'{symbol} {position_side.name}: Adding limit stoploss order with trigger price '
                             f'{new_stoploss_order.stop_price} at sell price {new_stoploss_order.price} with quantity {new_stoploss_order.quantity}')

                stoploss_orders.append(new_stoploss_order)
            elif order_type == OrderType.STOP_MARKET:
                logger.debug(f'{symbol} {position_side.name}: Adding market stoploss order with trigger price '
                             f'{trigger_price} with quantity {quantity_per_order}')

                new_stoploss_order = StopLossMarketOrder(order_type_identifier=OrderTypeIdentifier.STOPLOSS,
                                                         symbol=symbol,
                                                         stop_price=trigger_price,
                                                         side=side,
                                                         position_side=position_side)
                if len(trigger_prices) == 1:
                    new_stoploss_order.quantity = 0
                    new_stoploss_order.close_position = True
                else:
                    # new_stoploss_order.reduce_only = True
                    new_stoploss_order.quantity = quantity_per_order
                stoploss_orders.append(new_stoploss_order)
            else:
                raise InvalidConfigurationException(f'{symbol} {position_side.name}: The order-type {order_type.name} '
                                                    f'is not supported for a stoploss')
        return stoploss_orders

    def calculate_trigger_prices(self,
                                 symbol: str,
                                 position_side: PositionSide,
                                 trigger_price: float,
                                 grid_range: float,
                                 nr_orders: int,
                                 price_step: float,
                                 current_price: float) -> List[float]:
        if position_side == PositionSide.LONG:
            if trigger_price > current_price:
                trigger_price = current_price - (2 * price_step)
        elif position_side == PositionSide.SHORT:
            if trigger_price < current_price:
                trigger_price = current_price + (2 * price_step)

        if nr_orders == 1:
            return [trigger_price]

        if position_side == PositionSide.LONG:
            outer_grid_price = trigger_price * (1 - grid_range)
        else:
            outer_grid_price = trigger_price * (1 + grid_range)
        price_distance = abs(trigger_price - outer_grid_price)
        price_distance_per_order = price_distance / nr_orders
        trigger_prices = []
        for i in range(nr_orders):
            if position_side == PositionSide.LONG:
                step_price = trigger_price - (i * price_distance_per_order)
            else:
                step_price = trigger_price + (i * price_distance_per_order)
            price = round_(number=step_price, step=price_step)
            trigger_prices.append(price)

        return trigger_prices

    def _should_calculate_trailing_price(self,
                                         symbol: str,
                                         position_side: PositionSide,
                                         position: Position,
                                         stoploss_config: StoplossConfig,
                                         existing_stoploss_orders: List[Order]) -> bool:
        if stoploss_config.trailing_enabled is False:
            return False

        if stoploss_config.trailing_threshold is None:
            logger.info(f'{symbol} {position_side.name}: Trailing threshold is not set, current nr of stoploss orders is {len(existing_stoploss_orders)}')
            return len(existing_stoploss_orders) > 0

        current_price = self.exchange_state.get_last_price(position.symbol)

        if position_side == PositionSide.LONG:
            threshold_price = position.entry_price * (1 + stoploss_config.trailing_threshold)
            # if we detect a SL order with the price above the position price, we're already trailing so we can continue
            if len(existing_stoploss_orders) > 0:
                max_existing_stoploss_price = max([o.stop_price for o in existing_stoploss_orders])
                if max_existing_stoploss_price >= position.entry_price:
                    logger.info(f'{symbol} {position_side.name}: Detected existing trailing SL order at {max_existing_stoploss_price}, continuing trailing SL')
            if current_price >= threshold_price:
                logger.info(f'{symbol} {position_side.name}: Current price {current_price} >= trailing threshold {threshold_price}, activating trailing SL')
                return True
            else:
                logger.info(f'{symbol} {position_side.name}: Current price {current_price} < trailing threshold {threshold_price}, not activating trailing SL')
                return False
        elif position_side == PositionSide.SHORT:
            threshold_price = position.entry_price * (1 - stoploss_config.trailing_threshold)
            # if we detect a SL order with the price below the position price, we're already trailing so we can continue
            if len(existing_stoploss_orders) > 0:
                min_existing_stoploss_price = min([o.stop_price for o in existing_stoploss_orders])
                if min_existing_stoploss_price <= position.entry_price:
                    logger.info(f'{symbol} {position_side.name}: Detected existing trailing SL order at {min_existing_stoploss_price}, continuing trailing SL')
            if current_price <= threshold_price:
                logger.info(f'{symbol} {position_side.name}: Current price {current_price} <= trailing threshold {threshold_price}, activating trailing SL')
                return True
            else:
                logger.info(f'{symbol} {position_side.name}: Current price {current_price} > trailing threshold {threshold_price}, not activating trailing SL')
                return False
