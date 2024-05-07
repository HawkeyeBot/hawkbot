import logging
from typing import List, Dict

from hawkbot.core.data_classes import SymbolPositionSide, FilterResult, ExchangeState
from hawkbot.core.model import PositionSide
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.exchange.exchange import Exchange
from hawkbot.core.filters.filter import Filter
from hawkbot.utils import calc_min_qty, round_, cost_to_quantity

logger = logging.getLogger(__name__)


class MaxQuantityFilter(Filter):
    @classmethod
    def filter_name(cls):
        return cls.__name__

    def __init__(self, bot, name: str, filter_config, redis_host: str, redis_port: int):
        super().__init__(bot=bot, name=name, filter_config=filter_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange_state: ExchangeState = None  # Injected by framework
        self.exchange: Exchange = None  # Injected by framework
        self.wallet_exposure: float = None
        self.wallet_exposure_ratio: float = None
        self.initial_cost: float = None
        self.dca_assumed_max_distance: float = None
        self.dca_quantity_multiplier: float = 2.0

        self.init_config(filter_config)

    def init_config(self, filter_config):
        if 'wallet_exposure' not in filter_config and 'wallet_exposure_ratio' not in filter_config:
            raise InvalidConfigurationException("The MaxQuantityFilter requires specifying either 'wallet_exposure' "
                                                "or 'wallet_exposure_ratio', both of which are absent in the "
                                                "configuration")

        if 'wallet_exposure' in filter_config and 'wallet_exposure_ratio' in filter_config:
            raise InvalidConfigurationException("The MaxQuantityFilter requires specifying EITHER 'wallet_exposure' or "
                                                "'wallet_exposure_ratio', but both are currently defined in the "
                                                "configuration")

        if 'wallet_exposure' in filter_config:
            self.wallet_exposure = filter_config['wallet_exposure']
        if 'wallet_exposure_ratio' in filter_config:
            self.wallet_exposure_ratio = filter_config['wallet_exposure_ratio']

        if 'initial_cost' not in filter_config:
            raise InvalidConfigurationException("The required parameter 'initial_cost' for the MaxQuantityFilter "
                                                "is not specified")
        self.initial_cost = filter_config['initial_cost']

        if 'dca_assumed_max_distance' not in filter_config:
            raise InvalidConfigurationException("The required parameter 'dca_assumed_max_distance' for the "
                                                "MaxQuantityFilter is not specified")
        self.dca_assumed_max_distance = filter_config['dca_assumed_max_distance']

        if 'dca_quantity_multiplier' not in filter_config:
            raise InvalidConfigurationException("The required parameter 'dca_quantity_multiplier' for the "
                                                "MaxQuantityFilter is not specified")
        self.dca_quantity_multiplier = filter_config['dca_quantity_multiplier']

    def filter_symbols(self,
                       starting_list: List[SymbolPositionSide],
                       first_filter: bool,
                       position_side: PositionSide,
                       previous_filter_results: List[FilterResult]) -> Dict[SymbolPositionSide, Dict]:
        if first_filter:
            all_symbols = self.exchange_state.get_all_symbol_informations_by_symbol().keys()
            starting_list = [SymbolPositionSide(symbol=symbol, position_side=position_side) for symbol in all_symbols]

        exposed_balance = self.wallet_exposure
        current_prices = self.exchange.fetch_all_current_prices()

        filtered_symbols = {}
        for symbol_positionside in starting_list:
            symbol = symbol_positionside.symbol
            symbol_information = self.exchange_state.get_symbol_information(symbol)
            current_price = current_prices[symbol].price

            if self.wallet_exposure_ratio is not None:
                wallet_balance = self.exchange_state.symbol_balance(symbol)
                exposed_balance = wallet_balance * self.wallet_exposure_ratio

            if position_side == PositionSide.LONG:
                assumed_dca_price = current_price * (1 - self.dca_assumed_max_distance)
            else:
                assumed_dca_price = current_price * (1 + self.dca_assumed_max_distance)

            initial_cost = exposed_balance * self.initial_cost
            min_entry_qty = calc_min_qty(price=current_price,
                                         inverse=False,
                                         qty_step=symbol_information.quantity_step,
                                         min_qty=symbol_information.minimum_quantity,
                                         min_cost=symbol_information.minimal_buy_cost)
            max_entry_qty = round_(cost_to_quantity(cost=initial_cost, price=current_price, inverse=False),
                                   step=symbol_information.quantity_step)
            last_quantity = max(min_entry_qty, max_entry_qty)

            accumulated_cost = last_quantity * current_price

            max_quantity_exceeded = False
            while accumulated_cost <= exposed_balance:
                last_quantity *= self.dca_quantity_multiplier
                if last_quantity > symbol_information.maximum_quantity:
                    max_quantity_exceeded = True
                    break
                new_cost = last_quantity * assumed_dca_price
                accumulated_cost += new_cost

            if max_quantity_exceeded is True:
                logger.info(f"{symbol} {position_side.name}: Adding symbol to candidate list because a DCA was "
                            f"calculated with a quantity if {last_quantity}, which exceeds the symbol's maximum "
                            f"quantity of {symbol_information.maximum_quantity}")
            else:
                filtered_symbols[symbol_positionside] = {}

        return filtered_symbols
