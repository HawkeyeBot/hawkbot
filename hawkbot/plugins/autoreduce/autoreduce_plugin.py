import logging
import os
from dataclasses import field, dataclass
from typing import List, Dict

from redis import Redis

from hawkbot.core.config.bot_config import BotConfig
from hawkbot.core.data_classes import ExchangeState
from hawkbot.core.model import PositionSide, Order, LimitOrder, OrderTypeIdentifier, SymbolInformation, MarketOrder, Position
from hawkbot.core.redis_keys import INCOME_SYMBOL_POSITIONSIDE
from hawkbot.core.time_provider import TimeProvider
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.utils import period_as_ms, readable, round_, round_dn, fill_optional_parameters, fill_required_parameters, readable_pct

logger = logging.getLogger(__name__)


@dataclass
class AutoreduceConfig:
    enabled: bool = field(default=True)
    reduce_minimum_interval_ms: float = period_as_ms('1s')
    profit_percentage_used_for_reduction: float = None
    activate_size_above_exposed_balance_pct: float = None


class AutoreducePlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.time_provider: TimeProvider = None  # Injected by pluginloader
        self.exchange_state: ExchangeState = None  # Injected by plugin loader
        self.config: BotConfig = None  # Injected by plugin loader
        self.last_reduce_processing_timestamp: int = 0
        self.redis = Redis(host="127.0.0.1", port=self.redis_port, decode_responses=True)

    def parse_config(self, autoreduce_dict: Dict) -> AutoreduceConfig:
        autoreduce_config = AutoreduceConfig()

        if len(autoreduce_dict.keys()) == 0:
            autoreduce_config.enabled = False
            return autoreduce_config

        optional_parameters = ['enabled']
        fill_optional_parameters(target=autoreduce_config, config=autoreduce_dict, optional_parameters=optional_parameters)
        required_parameters = ['profit_percentage_used_for_reduction',
                               'activate_size_above_exposed_balance_pct']
        fill_required_parameters(target=autoreduce_config, config=autoreduce_dict, required_parameters=required_parameters)

        if 'reduce_minimum_interval' in autoreduce_dict:
            autoreduce_config.reduce_minimum_interval_ms = period_as_ms(autoreduce_dict['reduce_minimum_interval'])

        return autoreduce_config

    def stop(self):
        self.redis.close()

    def calculate_autoreduce_orders(self,
                                    symbol: str,
                                    position_side: PositionSide,
                                    position: Position,
                                    autoreduce_config: AutoreduceConfig,
                                    current_price: float,
                                    symbol_information: SymbolInformation) -> List[Order]:
        if autoreduce_config.enabled is False:
            return []

        if not self.position_needs_reducing(symbol=symbol, position_side=position_side, position=position, autoreduce_config=autoreduce_config):
            return []

        keys = self.redis.keys(pattern=f'{INCOME_SYMBOL_POSITIONSIDE}_{symbol}_{position_side.name}')
        if len(keys) == 0:
            logger.debug(f'{symbol} {position_side.name}: No income registered, ignoring reducing opposite position')
            return self.exchange_state.open_reduce_orders(symbol=symbol, position_side=position_side)

        now = self.time_provider.get_utc_now_timestamp()
        if now - self.last_reduce_processing_timestamp < autoreduce_config.reduce_minimum_interval_ms:
            logger.info(f'{symbol} {position_side.name}: Not processing placing new autoreduce orders, because the last order placement was less than '
                        f'{autoreduce_config.reduce_minimum_interval_ms / 1000} seconds ago')
            return self.exchange_state.open_reduce_orders(symbol=symbol, position_side=position_side)
        else:
            self.last_reduce_processing_timestamp = self.time_provider.get_utc_now_timestamp()

        last_processed_income_file = self.get_last_process_income_file(symbol=symbol, position_side=position_side)

        # get the total profit gained since the last processed income
        try:
            if not os.path.exists(last_processed_income_file):
                self.reset_last_processed_income_timestamp(symbol=symbol, position_side=position_side, autoreduce_config=autoreduce_config)

            with open(last_processed_income_file, 'r') as file:
                last_processed_income_timestamp = int(file.readline())
        except:
            logger.exception(f"Failed to read last income timestamp from file {last_processed_income_file}, expecting this to be an IO race condition")
            return self.exchange_state.open_reduce_orders(symbol=symbol, position_side=position_side)

        logger.debug(f'{symbol} {position_side.name}: Processing incomes from {readable(last_processed_income_timestamp)} to {readable(now)}')
        timestamp_incomes = self.redis.zrangebyscore(f'{INCOME_SYMBOL_POSITIONSIDE}_{symbol}_{position_side.inverse().name}',
                                                     min=last_processed_income_timestamp,
                                                     max=now,
                                                     withscores=True)

        raw_income_sum = sum([float(income) for income, _ in timestamp_incomes])
        cost_to_close = sum([float(income) for income, _ in timestamp_incomes if float(income) > 0]) * autoreduce_config.profit_percentage_used_for_reduction
        logger.info(f'{symbol} {position_side.name}: Determining if autoreduce should be done based on gained profits {cost_to_close} and current price {current_price}')

        # calculate the quantity to close worth of the gained income
        if position_side == PositionSide.LONG:
            reduce_price = current_price - symbol_information.price_step
        else:
            reduce_price = current_price + symbol_information.price_step

        reduce_price = round_(reduce_price, symbol_information.price_step)
        cost_diff_per_unit = abs(current_price - position.entry_price)
        if cost_diff_per_unit == 0:
            logger.warning(f"{symbol} {position_side.name}: The cost_diff_per_unit is 0, as a result of current price {current_price} and strategy's position "
                           f"{self.exchange_state.position(symbol=symbol, position_side=position_side)}")
            return self.exchange_state.open_reduce_orders(symbol=symbol, position_side=position_side)

        unrounded_quantity_to_close = cost_to_close / cost_diff_per_unit
        quantity_to_close = round_dn(unrounded_quantity_to_close, symbol_information.quantity_step)
        if quantity_to_close > position.position_size:
            quantity_to_close = position.position_size
        if quantity_to_close >= symbol_information.minimum_quantity or quantity_to_close == position.position_size:
            # if the quantity is bigger than the minimum quantity, place the order at current price
            new_reduction_orders: List[Order] = [LimitOrder(
                order_type_identifier=OrderTypeIdentifier.REDUCE,
                symbol=symbol_information.symbol,
                quantity=quantity_to_close,
                side=position_side.decrease_side(),  # placed on reverse position side
                position_side=position_side,
                initial_entry=False,
                reduce_only=True,
                price=reduce_price)]

            logger.info(f'{symbol} {position_side.name}: Reducing {position_side.name} position by quantity {quantity_to_close} based on current price '
                        f'{current_price} and position price {position.entry_price} by processing new income of {cost_to_close} (raw income = {raw_income_sum}) from '
                        f'{readable(last_processed_income_timestamp)} to {readable(now)}')
            return new_reduction_orders
        else:

            logger.info(f'{symbol} {position_side.name}: Not reducing stuck {position_side.name} position because the quantity to reduce based on gather income '
                        f'{cost_to_close} (raw income = {raw_income_sum}) from {readable(last_processed_income_timestamp)} to {readable(now)} results in quantity to close '
                        f'{quantity_to_close}, which is less than the symbol\'s minimum quantity of {symbol_information.minimum_quantity}')
            return []

    def reset_last_processed_income_timestamp(self, symbol: str, position_side: PositionSide, autoreduce_config: AutoreduceConfig):
        if autoreduce_config.enabled is False:
            return

        last_processed_income_timestamp = self.time_provider.get_utc_now_timestamp()
        with open(self.get_last_process_income_file(symbol=symbol, position_side=position_side), 'w') as f:
            f.write(f'{last_processed_income_timestamp}')
        logger.info(f'{symbol} {position_side.name}: Reset last processed income timestamp to {readable(last_processed_income_timestamp)}')

    def get_last_process_income_file(self, symbol: str, position_side: PositionSide) -> str:
        return f'./data/last_processed_income_{symbol}_{position_side.name}'

    def position_needs_reducing(self, symbol: str, position_side: PositionSide, position: Position, autoreduce_config: AutoreduceConfig) -> bool:
        total_balance = self.exchange_state.symbol_balance(symbol)
        position_side_config = self.config.find_position_side_config(symbol=symbol, position_side=position_side)
        wallet_exposure = position_side_config.wallet_exposure
        wallet_exposure_ratio = position_side_config.wallet_exposure_ratio
        configured_wallet_exposure = self.exchange_state.calculate_wallet_exposure_ratio(symbol=symbol,
                                                                                         wallet_exposure=wallet_exposure,
                                                                                         wallet_exposure_ratio=wallet_exposure_ratio)
        exposed_balance = total_balance * configured_wallet_exposure

        if autoreduce_config.activate_size_above_exposed_balance_pct is not None:
            current_exposure_opposite_side = position.cost / (exposed_balance / 100)
            if current_exposure_opposite_side >= autoreduce_config.activate_size_above_exposed_balance_pct:
                logger.debug(f'{symbol} {position_side.name}: REDUCE ALLOWED because there is a LONG position with an exposure of '
                             f'{current_exposure_opposite_side}, which exceeds the set hedging threshold of '
                             f'{readable_pct(autoreduce_config.activate_size_above_exposed_balance_pct, 2)}')
                return True
            else:
                logger.debug(f'{symbol} {position_side.name}: REDUCE NOT ALLOWED because there is a LONG position with an exposure of '
                             f'{current_exposure_opposite_side}, which is less than the set hedging threshold of '
                             f'{readable_pct(autoreduce_config.activate_size_above_exposed_balance_pct, 2)}')

        return False
