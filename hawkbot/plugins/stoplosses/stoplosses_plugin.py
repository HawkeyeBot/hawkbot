import logging
from typing import List, Dict

from hawkbot.core.data_classes import ExchangeState
from hawkbot.core.model import Position, SymbolInformation, Order, PositionSide, OrderType
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.plugins.stoplosses.data_classes import StoplossesConfig, StoplossConfig, Condition

logger = logging.getLogger(__name__)


class StoplossesPlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange_state: ExchangeState = None  # Injected by loader

    def parse_config(self, stoplosses_dict: Dict) -> StoplossesConfig:
        stoplosses_config = StoplossesConfig()

        if len(stoplosses_dict) == 0:
            stoplosses_config.enabled = False
            return stoplosses_config

        if 'enabled' in stoplosses_dict:
            stoplosses_config.enabled = stoplosses_dict['enabled']
        if 'post_stoploss_mode' in stoplosses_dict:
            stoplosses_config.post_stoploss_mode = stoplosses_dict['post_stoploss_mode']

        for stoploss_dict in stoplosses_dict:
            stoploss_config = StoplossConfig()
            trigger = Condition()
            optional_parameters = ['upnl_exposed_wallet_above',
                                   'upnl_total_wallet_above',
                                   'relative_wallet_above',
                                   'wallet_exposure_above']
            for optional_parameter in optional_parameters:
                if optional_parameter in stoplosses_dict['conditions']:
                    setattr(trigger, optional_parameter, stoploss_dict[optional_parameter])

            optional_parameters = ['stoploss_price',
                                   'position_trigger_distance',
                                   'sell_distance',
                                   'grid_range',
                                   'nr_orders',
                                   'custom_trigger_price_enabled',
                                   'last_entry_trigger_distance',
                                   'wallet_exposure_threshold',
                                   'trailing_enabled',
                                   'trailing_distance']
            for optional_parameter in optional_parameters:
                if optional_parameter in stoplosses_dict:
                    setattr(stoploss_config, optional_parameter, stoplosses_dict[optional_parameter])

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
                    and trigger.upnl_exposed_wallet_above is None \
                    and trigger.upnl_total_wallet_above is None \
                    and stoploss_config.grid_range is None \
                    and stoploss_config.position_trigger_distance is None \
                    and stoploss_config.last_entry_trigger_distance is None \
                    and stoploss_config.custom_trigger_price_enabled is False:
                raise InvalidConfigurationException(
                    "None of the parameters 'stoploss_price', "
                    "'upnl_exposed_wallet_trigger_threshold', 'upnl_total_wallet_trigger_threshold', "
                    "'position_trigger_distance', 'last_entry_trigger_distance' and 'grid_range' "
                    "are not set; one of these is required when using the stoploss plugin, "
                    "or the parameter \'custom_trigger_price_enabled\' needs to be set to "
                    "true to allow the strategy to provide a custom trigger price")

            if stoploss_config.stoploss_price is not None \
                    and trigger.upnl_exposed_wallet_trigger_threshold is not None:
                raise InvalidConfigurationException("The parameter 'stoploss_price' and the parameter "
                                                    "'upnl_exposed_wallet_trigger_threshold' are both set; only one of "
                                                    "these is allowed")

            if stoploss_config.stoploss_price is not None \
                    and trigger.upnl_total_wallet_trigger_threshold is not None:
                raise InvalidConfigurationException("The parameter 'stoploss_price' and the parameter "
                                                    "'upnl_total_wallet_trigger_threshold' are both set; only one of these "
                                                    "is allowed")

            if trigger.upnl_exposed_wallet_trigger_threshold is not None \
                    and trigger.upnl_total_wallet_trigger_threshold is not None:
                raise InvalidConfigurationException(
                    "The parameter 'upnl_exposed_wallet_trigger_threshold' and the parameter "
                    "'upnl_total_wallet_trigger_threshold' are both set; only one of these is "
                    "allowed")

        return stoplosses_config

    def calculate_stoploss_orders(self,
                                  position: Position,
                                  position_side: PositionSide,
                                  symbol_information: SymbolInformation,
                                  current_price: float,
                                  wallet_balance: float,
                                  exposed_balance: float,
                                  wallet_exposure: float,
                                  stoplosses_config: StoplossesConfig,
                                  custom_trigger_price: float = None) -> List[Order]:
        if stoplosses_config.enabled is False:
            return []
        if len(stoplosses_config.stoploss) == 0:
            return []
        if position.no_position():
            return []

        symbol = symbol_information.symbol
        return []
