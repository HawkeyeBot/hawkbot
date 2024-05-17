import logging
from dataclasses import dataclass, field
from typing import List, Dict

from hawkbot.core.config.bot_config import PositionSideConfig
from hawkbot.core.data_classes import ExchangeState
from hawkbot.core.model import PositionSide, Order, SymbolInformation, OrderTypeIdentifier, LimitOrder, MarketOrder, OrderStatus
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.plugins.dca.dca_plugin import DcaConfig, DcaPlugin
from hawkbot.plugins.gridstorage.gridstorage_plugin import GridStoragePlugin
from hawkbot.utils import readable_pct, fill_optional_parameters

logger = logging.getLogger(__name__)


@dataclass
class HedgeConfig:
    enabled: bool = field(default_factory=lambda: True)
    first_order_type: str = field(default_factory=lambda: 'LIMIT')
    activate_hedge_above_wallet_exposure_pct: float = field(default=None)
    activate_hedge_above_upnl_pct: float = field(default=None)
    # upnl_pct_threshold_hedge_order_size: Dict[float, float] = field(default_factory=lambda: {})
    dca_config: DcaConfig = field(default=None)


class HedgePlugin(Plugin):
    dca_plugin: DcaPlugin
    gridstorage_plugin: GridStoragePlugin

    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange_state: ExchangeState = None  # Injected by plugin loader
        self.config = None  # Inject by plugin loader

    def parse_config(self, hedge_dict: Dict) -> HedgeConfig:
        hedge_config = HedgeConfig()

        if len(hedge_dict.keys()) == 0:
            hedge_config.enabled = False
            return hedge_config

        optional_parameters = ['activate_hedge_above_wallet_exposure_pct',
                               'first_order_type']
        fill_optional_parameters(target=hedge_config, config=hedge_dict, optional_parameters=optional_parameters)

        if 'activate_hedge_above_upnl_pct' in hedge_dict:
            hedge_config.initial_entry_activate_hedge_above_upnl_pct = abs(hedge_dict['activate_hedge_above_upnl_pct'])

        # if 'upnl_pct_threshold_hedge_order_size' in hedge_dict:
        #     for threshold, order_size in hedge_dict['upnl_pct_threshold_hedge_order_size'].items():
        #         hedge_config.upnl_pct_threshold_hedge_order_size[float(threshold)] = order_size

        if 'dca_config' not in hedge_dict:
            raise InvalidConfigurationException('A configuration block "dca_config" is expected for the hedge plugin')
        hedge_config.dca_config = self.dca_plugin.parse_config(hedge_dict['dca_config'])
        return hedge_config

    def calculate_hedge_orders(self, symbol: str,
                               position_side: PositionSide,
                               symbol_information: SymbolInformation,
                               wallet_balance: float,
                               hedge_config: HedgeConfig) -> List[Order]:
        last_price = self.exchange_state.get_last_price(symbol)

        logger.info('Starting placing hedge orders')
        wallet_exposure = self._calc_wallet_exposure_ratio(self.config.find_position_side_config(symbol=symbol, position_side=position_side))
        self.dca_plugin.initialize_unlimited_grid(symbol=symbol,
                                                  position_side=position_side,
                                                  symbol_information=symbol_information,
                                                  current_price=last_price,
                                                  dca_config=hedge_config.dca_config,
                                                  wallet_exposure=wallet_exposure)
        all_prices = self.gridstorage_plugin.get_prices(symbol=symbol, position_side=position_side)
        if position_side == PositionSide.LONG:
            allowed_prices = [price for price in all_prices if price < last_price]
        else:
            allowed_prices = [price for price in all_prices if price > last_price]
        allowed_prices.sort(reverse=position_side == PositionSide.LONG)
        logger.info(f'{symbol} {position_side.name}: Selected price below current price {last_price}: '
                    f'{allowed_prices}')
        dca_quantities = self.gridstorage_plugin.get_quantities(symbol=symbol, position_side=position_side)
        logger.info(f'{symbol} {position_side.name}: DCA quantities to use for hedging: {dca_quantities}')

        exposed_balance = wallet_balance * wallet_exposure

        price_index = 0
        limit_orders = []
        orders_cost = 0
        for i, dca_quantity_record in enumerate(dca_quantities):
            logger.info(f'{symbol} {position_side.name}: Creating {i} order')
            if i >= len(allowed_prices):
                # no more prices available, break it off
                break
            dca_price = allowed_prices[price_index]
            dca_quantity = dca_quantity_record.quantity

            if price_index == 0:
                if hedge_config.first_order_type == 'MARKET':
                    order = MarketOrder(order_type_identifier=OrderTypeIdentifier.INITIAL_ENTRY,
                                        symbol=symbol,
                                        quantity=dca_quantity,
                                        side=position_side.increase_side(),
                                        position_side=position_side,
                                        initial_entry=True,
                                        status=OrderStatus.NEW)
                else:
                    order = LimitOrder(
                        order_type_identifier=OrderTypeIdentifier.DCA,
                        symbol=symbol_information.symbol,
                        quantity=dca_quantity,
                        side=position_side.increase_side(),
                        position_side=position_side,
                        initial_entry=False,
                        price=dca_price)
            else:
                order = LimitOrder(
                    order_type_identifier=OrderTypeIdentifier.DCA,
                    symbol=symbol_information.symbol,
                    quantity=dca_quantity,
                    side=position_side.increase_side(),
                    position_side=position_side,
                    initial_entry=False,
                    price=dca_price)
            price_index += 1
            if orders_cost + order.cost > exposed_balance:
                break
            orders_cost += order.cost
            limit_orders.append(order)

        logger.info(f'{symbol} {position_side.name}: Determined hedge orders {limit_orders}')
        return limit_orders

    def is_hedge_applicable(self,
                            symbol: str,
                            position_side: PositionSide,
                            hedge_config: HedgeConfig) -> bool:
        if hedge_config.enabled is False:
            return False

        opposite_position = self.exchange_state.position(symbol=symbol, position_side=position_side.inverse())
        if opposite_position.no_position():
            return False

        if hedge_config.activate_hedge_above_wallet_exposure_pct is None and hedge_config.activate_hedge_above_upnl_pct:
            return False

        total_balance = self.exchange_state.symbol_balance(symbol)
        position_side_config = self.config.find_position_side_config(symbol=symbol, position_side=position_side.inverse())
        wallet_exposure = position_side_config.wallet_exposure
        wallet_exposure_ratio = position_side_config.wallet_exposure_ratio
        configured_wallet_exposure = self.exchange_state.calculate_wallet_exposure_ratio(symbol=symbol,
                                                                                         wallet_exposure=wallet_exposure,
                                                                                         wallet_exposure_ratio=wallet_exposure_ratio)
        exposed_balance = total_balance * configured_wallet_exposure

        if hedge_config.activate_hedge_above_wallet_exposure_pct is not None:
            current_exposure_opposite_side = opposite_position.cost / (exposed_balance / 100)
            if current_exposure_opposite_side >= hedge_config.activate_hedge_above_wallet_exposure_pct:
                logger.info(f'{symbol} {position_side.name}: HEDGE ENTRY ALLOWED as a result of active hedging because there is a LONG position with an exposure of '
                            f'{current_exposure_opposite_side}, which exceeds the set hedging threshold of '
                            f'{readable_pct(hedge_config.activate_hedge_above_wallet_exposure_pct, 2)}')
                return True
            else:
                logger.debug(f'{symbol} {position_side.name}: NOT HEDGING as a result of active hedging because there is a LONG position with an exposure of '
                             f'{current_exposure_opposite_side}, which is less than the set hedging threshold of '
                             f'{readable_pct(hedge_config.activate_hedge_above_wallet_exposure_pct, 2)}')
        if hedge_config.activate_hedge_above_upnl_pct is not None:
            current_price = self.exchange_state.get_last_price(symbol)
            leverage = self._symbol_leverage(symbol)
            current_upnl_opposite_side = opposite_position.calculate_pnl_pct(price=current_price, leverage=leverage)
            upnl_percentage_of_exposed_balance = abs(current_upnl_opposite_side) / (total_balance / 100)

            if upnl_percentage_of_exposed_balance > hedge_config.activate_hedge_above_upnl_pct:
                logger.info(f'{symbol} {position_side.name}: HEDGE ENTRY ALLOWED as a result of active hedging because there is a LONG position with a upnl percentage of '
                            f'{current_upnl_opposite_side}, which exceeds the set hedging UPNL threshold of '
                            f'{readable_pct(hedge_config.activate_hedge_above_upnl_pct, 2)}')
                return True
            else:
                logger.debug(f'{symbol} {position_side.name}: NOT HEDGING as a result of active hedging because there is a LONG position with a upnl percentage of '
                             f'{current_upnl_opposite_side}, which is less than the set hedging UPNL threshold of '
                             f'{readable_pct(hedge_config.activate_hedge_above_upnl_pct, 2)}')
        return False

    def _symbol_leverage(self, symbol: str):
        leverage = self.config.find_symbol_config(symbol).exchange_leverage
        if leverage == "MAX":
            leverage = self.exchange_state.get_symbol_information(symbol).max_leverage
        return leverage

    def _calc_wallet_exposure_ratio(self, position_side_config: PositionSideConfig):
        return self.exchange_state.calculate_wallet_exposure_ratio(symbol=position_side_config.symbol,
                                                                   wallet_exposure=position_side_config.wallet_exposure,
                                                                   wallet_exposure_ratio=position_side_config.wallet_exposure_ratio)
