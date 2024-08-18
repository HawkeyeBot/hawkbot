import logging
from dataclasses import dataclass, field
from typing import List, Dict

from hawkbot.core.data_classes import ExchangeState, QuantityPrice
from hawkbot.core.model import PositionSide, SymbolInformation, Position, LimitOrder, Order, OrderTypeIdentifier, Side, \
    Timeframe
from hawkbot.exceptions import InvalidConfigurationException, NoInitialEntryOrderException
from hawkbot.logging import user_log
from hawkbot.plugins.clustering_sr.algo_type import AlgoType
from hawkbot.plugins.clustering_sr.clustering_sr_plugin import ClusteringSupportResistancePlugin
from hawkbot.plugins.gridstorage.data_classes import QuantityRecord, PriceRecord
from hawkbot.plugins.gridstorage.gridstorage_plugin import GridStoragePlugin
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.utils import round_dn, round_, cost_to_quantity, calc_min_qty, fill_optional_parameters, calculate_new_order_size

logger = logging.getLogger(__name__)


@dataclass
class DcaConfig:
    enabled: bool = field(default_factory=lambda: True)

    # first entry grid
    first_level_period: str = field(default_factory=lambda: None)
    first_level_period_timeframe: Timeframe = field(default_factory=lambda: None)
    first_level_algo: AlgoType = field(default_factory=lambda: None)
    first_level_nr_clusters: int = field(default_factory=lambda: None)
    # inner grid
    period: str = field(default_factory=lambda: None)
    period_timeframe: Timeframe = field(default_factory=lambda: None)
    algo: AlgoType = field(default_factory=lambda: None)
    period_start_date: int = field(default_factory=lambda: None)
    nr_clusters: int = None
    # outer price
    outer_price: float = field(default_factory=lambda: None)
    outer_price_distance: float = field(default_factory=lambda: None)
    outer_price_period: str = field(default_factory=lambda: None)
    outer_price_timeframe: Timeframe = field(default_factory=lambda: None)
    outer_price_period_start_date: int = field(default_factory=lambda: None)
    outer_price_algo: AlgoType = field(default_factory=lambda: None)
    minimum_distance_to_outer_price: float = field(default_factory=lambda: None)
    maximum_distance_from_outer_price: float = field(default_factory=lambda: None)
    outer_price_level_nr: int = 1
    outer_price_nr_clusters: int = None
    minimum_distance_between_levels: float = None

    overlap: float = 0.001
    quantity_unit_margin: int = 2
    ratio_power: float = field(default_factory=lambda: None)
    maximum_position_coin_size: float = field(default_factory=lambda: None)
    initial_entry_size: float = field(default_factory=lambda: None)
    desired_position_distance_after_dca: float = field(default_factory=lambda: None)
    previous_quantity_multiplier: float = field(default_factory=lambda: None)
    dca_quantity_multiplier: float = field(default_factory=lambda: None)
    minimum_number_dca_quantities: int = 15
    override_insufficient_levels_available: bool = False
    check_dca_against_wallet: bool = field(default=True)
    allow_add_new_smaller_dca: bool = field(default=True)


class DcaPlugin(Plugin):
    gridstorage_plugin: GridStoragePlugin = None
    sr_plugin: ClusteringSupportResistancePlugin = None

    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange_state: ExchangeState = None  # Injected by plugin loader

    def parse_config(self, dca_dict: Dict) -> DcaConfig:
        dca_config = DcaConfig()

        if len(dca_dict.keys()) == 0:
            dca_config.enabled = False
            return dca_config

        fill_optional_parameters(target=dca_config,
                                 config=dca_dict,
                                 optional_parameters=['enabled',
                                                      'first_level_period',
                                                      'first_level_nr_clusters',
                                                      'maximum_position_coin_size',
                                                      'period',
                                                      'period_start_date',
                                                      'outer_price',
                                                      'outer_price_distance',
                                                      'outer_price_period',
                                                      'outer_price_period_start_date',
                                                      'minimum_distance_to_outer_price',
                                                      'maximum_distance_from_outer_price',
                                                      'outer_price_level_nr',
                                                      'outer_price_nr_clusters',
                                                      'nr_clusters',
                                                      'quantity_unit_margin',
                                                      'previous_quantity_multiplier',
                                                      'dca_quantity_multiplier',
                                                      'ratio_power',
                                                      'check_dca_against_wallet',
                                                      'override_insufficient_levels_available',
                                                      'minimum_number_dca_quantities',
                                                      'desired_position_distance_after_dca',
                                                      'initial_entry_size',
                                                      'minimum_distance_between_levels',
                                                      'allow_add_new_smaller_dca'])

        if 'first_level_period_timeframe' in dca_dict:
            dca_config.first_level_period_timeframe = Timeframe.parse(dca_dict['first_level_period_timeframe'])

        if 'first_level_algo' in dca_dict:
            dca_config.first_level_algo = AlgoType[dca_dict['first_level_algo']]

        if dca_config.first_level_period is not None:
            if dca_config.first_level_nr_clusters is None:
                raise InvalidConfigurationException(f'The parameter \'first_level_nr_clusters\' is not set but is '
                                                    f'required when \'first_level_nr_clusters\' is provided')
            if dca_config.first_level_nr_clusters <= 0:
                raise InvalidConfigurationException(f'The parameter \'first_level_nr_clusters\' must be set with a '
                                                    f'value of 1 or higher')
            if dca_config.first_level_period_timeframe is None:
                raise InvalidConfigurationException(f'The parameter \'first_level_period_timeframe\' is not set but is '
                                                    f'required when \'first_level_period\' is provided')
            if dca_config.first_level_algo is None:
                raise InvalidConfigurationException(f'The parameter \'first_level_algo\' is not set but is '
                                                    f'required when \'first_level_period\' is provided')

        if 'algo' in dca_dict:
            dca_config.algo = AlgoType[dca_dict['algo']]
        else:
            raise InvalidConfigurationException("The parameter 'algo' is not set in the configuration")

        if 'period' not in dca_dict \
                and 'period_start_date' not in dca_dict \
                and dca_config.algo not in [AlgoType.LINEAR, AlgoType.IMMEDIATE_LINEAR]:
            raise InvalidConfigurationException("One of the parameters 'period' or 'period_start_date is mandatory")

        if 'period_timeframe' in dca_dict:
            dca_config.period_timeframe = Timeframe.parse(dca_dict['period_timeframe'])
        else:
            if dca_config.algo not in [AlgoType.LINEAR, AlgoType.IMMEDIATE_LINEAR]:
                raise InvalidConfigurationException("The parameter 'period_timeframe' is not set in the configuration")

        if 'outer_price_timeframe' in dca_dict:
            dca_config.outer_price_timeframe = Timeframe.parse(dca_dict['outer_price_timeframe'])

        if 'outer_price_algo' in dca_dict:
            dca_config.outer_price_algo = AlgoType[dca_dict['outer_price_algo']]
        else:
            if dca_config.outer_price_period is not None:
                raise InvalidConfigurationException("The parameter 'outer_price_algo' is not set in the configuration")

        if dca_config.dca_quantity_multiplier is None \
                and dca_config.previous_quantity_multiplier is None \
                and dca_config.ratio_power is None \
                and dca_config.desired_position_distance_after_dca is None:
            raise InvalidConfigurationException(f"Either of the parameters 'ratio_power', 'dca_quantity_multiplier', 'previous_quantity_multiplier' "
                                                f"or 'desired_position_distance_after_dca' is required but is not set.")
        if (dca_config.dca_quantity_multiplier is not None or dca_config.previous_quantity_multiplier is not None) and dca_config.ratio_power is not None:
            raise InvalidConfigurationException(f"Both parameters 'ratio_power' and ('dca_quantity_multiplier' or 'previous_quantity_multiplier') are "
                                                f"set but only one of the two is allowed.")

        if dca_config.minimum_distance_to_outer_price is not None \
                and dca_config.minimum_distance_to_outer_price <= 0:
            raise InvalidConfigurationException(f"The parameter 'minimum_distance_to_outer_price' needs to be a "
                                                f"positive value (current value = "
                                                f"'{dca_config.minimum_distance_to_outer_price}')")

        if dca_config.minimum_distance_to_outer_price is not None and dca_config.outer_price_distance is not None:
            raise InvalidConfigurationException(f'Both the parameter \'minimum_distance_to_outer_price\' and the '
                                                f'parameter \'outer_price_distance\' are set, but these are mutually '
                                                f'exclusive.')

        if dca_config.outer_price_timeframe is None and dca_config.outer_price_period is not None:
            raise InvalidConfigurationException("The parameter 'outer_price_timeframe' is required when the parameter "
                                                "'outer_price_period' is set")

        if dca_config.outer_price_timeframe is not None and dca_config.outer_price_period is None:
            raise InvalidConfigurationException("The parameter 'outer_price_period' is required when the parameter "
                                                "'outer_price_timeframe' is set")

        if dca_config.desired_position_distance_after_dca is not None and dca_config.initial_entry_size is None:
            raise InvalidConfigurationException("The parameter 'initial_entry_size' is required when the parameter "
                                                "'desired_position_distance_after_dca' is set")

        return dca_config

    def initialize_unlimited_grid(self,
                                  symbol: str,
                                  position_side: PositionSide,
                                  symbol_information: SymbolInformation,
                                  current_price: float,
                                  dca_config: DcaConfig,
                                  initial_cost: float = None,
                                  wallet_exposure: float = None,
                                  reset_quantities: bool = True,
                                  enforce_nr_clusters: bool = True):
        if not dca_config.enabled:
            return
        if position_side == PositionSide.LONG:
            self._initialize_unlimited_grid_long(symbol=symbol,
                                                 position_side=position_side,
                                                 symbol_information=symbol_information,
                                                 maximum_price=current_price,
                                                 dca_config=dca_config,
                                                 initial_cost=initial_cost,
                                                 wallet_exposure=wallet_exposure,
                                                 reset_quantities=reset_quantities,
                                                 enforce_nr_clusters=enforce_nr_clusters)
        else:
            self._initialize_unlimited_grid_short(symbol=symbol,
                                                  position_side=position_side,
                                                  symbol_information=symbol_information,
                                                  minimum_price=current_price,
                                                  dca_config=dca_config,
                                                  initial_cost=initial_cost,
                                                  wallet_exposure=wallet_exposure,
                                                  reset_quantities=reset_quantities,
                                                  enforce_nr_clusters=enforce_nr_clusters)

    def calculate_dca_grid(self,
                           symbol: str,
                           position: Position,
                           symbol_information: SymbolInformation,
                           wallet_balance: float,
                           wallet_exposure: float,
                           current_price: float,
                           dca_config: DcaConfig) -> List[Order]:
        if dca_config.enabled is False:
            return []

        if position.position_side is PositionSide.LONG:
            return self.calculate_dca_grid_long(symbol=symbol,
                                                position=position,
                                                symbol_information=symbol_information,
                                                wallet_balance=wallet_balance,
                                                wallet_exposure=wallet_exposure,
                                                current_price=current_price,
                                                dca_config=dca_config)
        elif position.position_side is PositionSide.SHORT:
            return self.calculate_dca_grid_short(symbol=symbol,
                                                 position=position,
                                                 symbol_information=symbol_information,
                                                 wallet_balance=wallet_balance,
                                                 wallet_exposure=wallet_exposure,
                                                 current_price=current_price,
                                                 dca_config=dca_config)

    def calculate_dca_grid_long(self,
                                symbol: str,
                                position: Position,
                                symbol_information: SymbolInformation,
                                wallet_balance: float,
                                wallet_exposure: float,
                                current_price: float,
                                dca_config: DcaConfig) -> List[Order]:
        position_side = position.position_side
        first_quantity_price = None

        if self.exchange_state.no_dca_orders_on_exchange(symbol=symbol, position_side=position_side):
            logger.info(f'{symbol} {position_side.name}: No DCA orders on the exchange')
            support_prices = self.gridstorage_plugin.get_prices(symbol=symbol, position_side=position_side)
            support_prices = [price for price in support_prices if price <= current_price]
            try:
                support_prices = [price for price in support_prices
                                  if price < self.exchange_state.initial_entry_price(symbol=symbol,
                                                                                     position_side=position_side)]
            except NoInitialEntryOrderException:
                logger.debug(f'{symbol} {position_side.name}: No initial entry found, ignoring filtering out prices below position price')

            support_prices.sort(reverse=True)
            if len(support_prices) > 0:
                # first DCA quantity is for the initial entry
                dca_quantities = self.gridstorage_plugin.get_quantities(symbol=symbol, position_side=position_side)[1:]
                margin = dca_config.quantity_unit_margin * symbol_information.quantity_step
                logger.info(f'{symbol} {position_side.name}: Selecting DCA quantities with a max position smaller or '
                            f'equal to {position.position_size} + {margin} margin')
                available_quantities = [record.quantity for record in dca_quantities
                                        if position.position_size <= record.max_position_size + margin]
                if len(available_quantities) > 0:
                    first_quantity = min(available_quantities)
                    quantity_index = len([q for q in dca_quantities if q.quantity <= first_quantity]) - 1
                    quantity_index = min(quantity_index, len(support_prices) - 1)
                    first_price = support_prices[quantity_index]
                    last_filled_dca_price = self.exchange_state.last_filled_dca_price(symbol=symbol,
                                                                                      position_side=position_side)
                    if last_filled_dca_price is not None and last_filled_dca_price < first_price:
                        prices_available_for_dca = [price for price in support_prices if price < last_filled_dca_price]
                        if len(prices_available_for_dca) == 0:
                            logger.info(f'{symbol} {position_side.name}: There are no DCA prices available in the '
                                        f'stored grid of which the price is below the last filled DCA price of '
                                        f'{last_filled_dca_price} based on the position size {position.position_size} '
                                        f'and margin {margin}. Not placing a new DCA grid')
                            return []
                        else:
                            first_price = max(prices_available_for_dca)
                    first_quantity_price = QuantityPrice(first_quantity, first_price)
            else:
                logger.warning(f'{symbol} {position_side.name}: Found 0 support prices, this situation is expected to '
                               f'auto correct on the next periodic check.')
        else:
            first_quantity_price = self.calculate_first_dca_quantity_price_long(symbol=symbol,
                                                                                symbol_information=symbol_information,
                                                                                wallet_balance=wallet_balance,
                                                                                wallet_exposure=wallet_exposure,
                                                                                current_price=current_price,
                                                                                position=position,
                                                                                dca_config=dca_config)

        if first_quantity_price is not None:
            return self._calculate_dca_grid_from_first_long(symbol=symbol,
                                                            position=position,
                                                            symbol_information=symbol_information,
                                                            first_support_price=first_quantity_price.price,
                                                            first_quantity=first_quantity_price.quantity)
        else:
            return self.exchange_state.open_dca_orders(symbol=symbol, position_side=position.position_side)

    def _calculate_dca_grid_from_first_long(self,
                                            symbol: str,
                                            position: Position,
                                            symbol_information: SymbolInformation,
                                            first_support_price: float,
                                            first_quantity: float) -> List[Order]:
        position_side = position.position_side
        # identify support prices based on current price & config
        all_dca_qtys = self.gridstorage_plugin.get_quantities(symbol=symbol, position_side=position_side)
        if not position.has_position():
            logger.warning('The code was called to create a DCA grid, but there is currently no open position on '
                           'the exchange. This situation should auto-correct on the next synchronisation round.')
            return []

        position_size = position.position_size
        available_dca_qtys = [record for record in all_dca_qtys if record.quantity >= first_quantity]
        if len(available_dca_qtys) == 0:
            user_log.info(f"{symbol}: There are no DCA orders on the exchange, but there are no quantities available "
                          f"based on position size {position_size}", __name__)
            return []

        support_price_records = self.gridstorage_plugin.get_prices(symbol=symbol, position_side=position_side)
        support_prices = [price for price in support_price_records if price <= first_support_price]
        support_prices.sort(reverse=True)

        current_price = self.exchange_state.last_tick_price(symbol)
        lowest_price = symbol_information.lowest_allowed_price(current_price=current_price)
        dca_orders = []
        for i in range(len(available_dca_qtys)):
            quantity_record = available_dca_qtys[i]
            dca_quantity = quantity_record.quantity
            if len(support_prices) <= i:
                logger.info(f'{symbol} {position_side.name}: There are only {len(support_prices)} available, while '
                            f'there are {len(available_dca_qtys)} DCA quantities available.')
                break
            dca_price = support_prices[i]
            if dca_price < lowest_price:
                logger.warning(f"{symbol} {position_side.name}: The desired DCA price of {dca_price} is less than the "
                               f"lowest allowed price of {lowest_price}, stopping further DCA calculation. Current "
                               f"price = {current_price}, symbol information = {symbol_information}")
                break
            order = LimitOrder(order_type_identifier=OrderTypeIdentifier.DCA,
                               symbol=symbol_information.symbol,
                               quantity=dca_quantity,
                               side=position_side.increase_side(),
                               position_side=position_side,
                               initial_entry=False,
                               price=round_(dca_price, symbol_information.price_step))
            dca_orders.append(order)
        return dca_orders

    def _initialize_unlimited_grid_long(self,
                                        symbol: str,
                                        position_side: PositionSide,
                                        symbol_information: SymbolInformation,
                                        maximum_price: float,
                                        dca_config: DcaConfig,
                                        initial_cost: float,
                                        wallet_exposure: float,
                                        reset_quantities: bool = True,
                                        enforce_nr_clusters: bool = True):
        self.gridstorage_plugin.reset(symbol=symbol, position_side=position_side)
        self.gridstorage_plugin.store_root_price(symbol=symbol, position_side=position_side, price=maximum_price)
        support_price_records = self.calculate_support_prices(symbol=symbol,
                                                              position_side=position_side,
                                                              maximum_price=maximum_price,
                                                              dca_config=dca_config,
                                                              enforce_nr_clusters=enforce_nr_clusters)
        self.gridstorage_plugin.store_prices(symbol=symbol, prices_records=support_price_records)
        for price_record in support_price_records:
            logger.info(f'{symbol} {position_side.name}: Stored grid support price {price_record.price}')

        if reset_quantities:
            self.gridstorage_plugin.reset_quantities(symbol=symbol, position_side=position_side)

            accumulated_qty = 0.0

            quantities: List[QuantityRecord] = []
            dca_quantities = self._calculate_dca_quantities(symbol=symbol,
                                                            position_side=position_side,
                                                            dca_config=dca_config,
                                                            level_prices=[r.price for r in support_price_records],
                                                            nr_clusters=dca_config.nr_clusters,
                                                            symbol_information=symbol_information,
                                                            initial_cost=initial_cost,
                                                            wallet_exposure=wallet_exposure)
            for dca_quantity in dca_quantities:
                accumulated_qty += dca_quantity
                rounded_quantity = round_(dca_quantity, symbol_information.quantity_step)
                quantity_record = QuantityRecord(position_side=position_side,
                                                 quantity=rounded_quantity,
                                                 accumulated_quantity=accumulated_qty,
                                                 raw_quantity=dca_quantity)
                logger.info(f'{symbol} {position_side.name}: accumulated_qty={accumulated_qty}, '
                            f'order qty={rounded_quantity}, raw qty={dca_quantity}')
                quantities.append(quantity_record)

            self.gridstorage_plugin.store_quantities(symbol=symbol, quantities=quantities)
        logging.info(f'{symbol} {position_side.name}: Initialized unlimited grid')

    def calculate_support_prices(self,
                                 symbol: str,
                                 position_side: PositionSide,
                                 maximum_price: float,
                                 dca_config: DcaConfig,
                                 enforce_nr_clusters: bool = True) -> List[PriceRecord]:
        if dca_config.enabled is False:
            return []
        price_step = self.exchange_state.get_symbol_information(symbol).price_step
        minimum_symbol_price = self.exchange_state.get_symbol_information(symbol).minimum_price
        support_resistance = self.sr_plugin.get_support_resistance_levels(symbol=symbol,
                                                                          position_side=position_side,
                                                                          even_price=maximum_price,
                                                                          price_step=price_step,
                                                                          dca_config=dca_config)
        final_support_list = support_resistance.supports
        for resistance in support_resistance.resistances:
            min_resistance_overlap_price = resistance * (1 - dca_config.overlap)
            max_resistance_overlap_price = resistance * (1 + dca_config.overlap)
            resistance_overlaps = False
            for support in final_support_list:
                if min_resistance_overlap_price <= support <= max_resistance_overlap_price:
                    resistance_overlaps = True
                    break
            if not resistance_overlaps and resistance < maximum_price:
                final_support_list.append(resistance)

        support_prices = [PriceRecord(position_side=position_side, price=price)
                          for price in final_support_list if price >= minimum_symbol_price]
        support_prices.sort(reverse=True, key=lambda r: r.price)
        if dca_config.minimum_distance_between_levels is not None:
            filtered_support_prices = []
            previous_support_price = None
            for support_price in support_prices:
                if previous_support_price is None:
                    filtered_support_prices.append(support_price)
                    previous_support_price = support_price
                else:
                    if previous_support_price.price * (1 - dca_config.minimum_distance_between_levels) > support_price.price:
                        filtered_support_prices.append(support_price)
                        previous_support_price = support_price

            support_prices = filtered_support_prices

        if dca_config.nr_clusters is not None:
            if len(support_prices) < dca_config.nr_clusters:
                if enforce_nr_clusters:
                    logger.warning(f'{symbol} {position_side.name}: The number of calculated supports is '
                                   f'{len(support_prices)}, while the number of configured clusters is '
                                   f'{dca_config.nr_clusters}. Explicit instruction is to ignore this, so returning the '
                                   f'found support-prices none-the-less.')
                else:
                    logger.warning(f'{symbol} {position_side.name}: The number of calculated supports is '
                                   f'{len(support_prices)}, while the number of configured clusters is '
                                   f'{dca_config.nr_clusters}. Not using the calculated levels due to not being able to '
                                   f'match the specified nr_clusters. This can likely be solved by adding more history, or '
                                   f'by changing nr_clusters.')
                    return []

        return support_prices

    def _calculate_dca_quantities(self,
                                  symbol: str,
                                  position_side: PositionSide,
                                  dca_config: DcaConfig,
                                  level_prices: List[float],
                                  nr_clusters: int,
                                  symbol_information: SymbolInformation,
                                  initial_cost: float,
                                  wallet_exposure: float) -> List[float]:
        if len(level_prices) == 0:
            logger.debug(f'{symbol} {position_side.name}: No level prices are found, returning an empty list of '
                         f'quantities')
            return []
        if dca_config.ratio_power is not None:
            if dca_config.maximum_position_coin_size is not None:
                max_size = dca_config.maximum_position_coin_size
            else:
                # calculate max_size optimistically from the last DCA price * wallet_exposure
                wallet_balance = self.exchange_state.symbol_balance(symbol)
                maximum_cost = wallet_balance * wallet_exposure
                least_coins_at_price = max(level_prices[0:nr_clusters])
                max_size = maximum_cost / least_coins_at_price
                logger.info(f'{symbol} {position_side.name}: Based on wallet balance {wallet_balance} and wallet '
                            f'exposure {wallet_exposure}, the maximum cost is {maximum_cost}. The level price '
                            f'resulting in the least amount of coins is {least_coins_at_price}. The results in a '
                            f'maximum position size {max_size}')

            ratio_power = dca_config.ratio_power
            return self._calculate_dca_quantities_final_size(symbol=symbol,
                                                             position_side=position_side,
                                                             steps=nr_clusters,
                                                             max_size=max_size,
                                                             ratio_power=ratio_power)
        elif dca_config.desired_position_distance_after_dca is not None:
            wallet_balance = self.exchange_state.symbol_balance(symbol)
            maximum_cost = wallet_balance * wallet_exposure
            return self._calculate_dca_quantities_for_desired_distance(symbol=symbol,
                                                                       position_side=position_side,
                                                                       initial_entry_size=dca_config.initial_entry_size,
                                                                       level_prices=level_prices,
                                                                       dca_config=dca_config,
                                                                       maximum_cost=maximum_cost,
                                                                       symbol_information=symbol_information)
        else:
            return self._calculate_dca_quantities_multiplier(symbol=symbol,
                                                             position_side=position_side,
                                                             level_prices=level_prices,
                                                             dca_config=dca_config,
                                                             symbol_information=symbol_information,
                                                             initial_cost=initial_cost,
                                                             wallet_exposure=wallet_exposure)

    def _calculate_dca_quantities_for_desired_distance(self,
                                                       symbol: str,
                                                       position_side: PositionSide,
                                                       initial_entry_size: float,
                                                       level_prices: List[float],
                                                       dca_config: DcaConfig,
                                                       maximum_cost: float,
                                                       symbol_information: SymbolInformation) -> List[float]:
        if position_side == PositionSide.LONG:
            level_prices.sort(reverse=True)
        elif position_side == PositionSide.SHORT:
            level_prices.sort()

        initial_cost = initial_entry_size * maximum_cost
        position_price = None
        position_size = None
        quantities = []

        for level_price in level_prices:
            if position_price is None:
                position_price = level_prices[0]
                position_size = initial_cost / position_price
                quantities.append(position_size)
            else:
                if position_side == PositionSide.LONG:
                    minimum_cost = symbol_information.minimal_buy_cost
                    desired_position_price = level_price * (1 + dca_config.desired_position_distance_after_dca)
                    if desired_position_price <= level_price:
                        quantities.append(0)
                        continue
                elif position_side == PositionSide.SHORT:
                    minimum_cost = symbol_information.minimal_sell_cost
                    desired_position_price = level_price * (1 - dca_config.desired_position_distance_after_dca)
                    if desired_position_price >= level_price:
                        quantities.append(0)
                        continue
                quantity_to_purchase = calculate_new_order_size(symbol=symbol,
                                                                position_side=position_side,
                                                                original_entry_price=position_price,
                                                                original_position_size=position_size,
                                                                desired_avg_price=desired_position_price,
                                                                current_price=level_price)
                minimum_quantity = calc_min_qty(price=level_price,
                                                inverse=False,
                                                qty_step=symbol_information.quantity_step,
                                                min_qty=symbol_information.minimum_quantity,
                                                min_cost=minimum_cost)
                quantity_to_purchase = max(quantity_to_purchase, minimum_quantity)
                position_price = desired_position_price
                position_size += quantity_to_purchase
                quantities.append(quantity_to_purchase)

        # IMPORTANT: DO NOT SORT, as the required quantities may not necessarily be only bigger on each DCA
        return quantities

    def _calculate_dca_quantities_multiplier(self,
                                             symbol: str,
                                             position_side: PositionSide,
                                             level_prices: List[float],
                                             dca_config: DcaConfig,
                                             symbol_information: SymbolInformation,
                                             initial_cost: float,
                                             wallet_exposure: float) -> List[float]:
        if self.exchange_state.has_open_position(symbol=symbol, position_side=position_side):
            initial_entry_order = self.exchange_state.initial_entry_order(symbol=symbol, position_side=position_side)
            logger.info(f'Initial entry order: {initial_entry_order}')
            if dca_config.check_dca_against_wallet:
                initial_entry_price = initial_entry_order.price
                wallet_balance = self.exchange_state.symbol_balance(symbol)
                initial_cost_amount = wallet_balance * wallet_exposure * initial_cost
                min_entry_qty = calc_min_qty(price=initial_entry_price,
                                             inverse=False,
                                             qty_step=symbol_information.quantity_step,
                                             min_qty=symbol_information.minimum_quantity,
                                             min_cost=symbol_information.minimal_buy_cost)
                max_entry_qty = round_(cost_to_quantity(cost=initial_cost_amount, price=initial_entry_price, inverse=False),
                                       step=symbol_information.quantity_step)
                accumulated_qty = max(min_entry_qty, max_entry_qty)
                position_size = self.exchange_state.position(symbol=symbol, position_side=position_side)
                logger.info(f'{symbol} {position_side.name}: Accumulated qty {accumulated_qty} based on initial cost {initial_cost} '
                            f'({wallet_balance} * {wallet_exposure} * {initial_cost}) at entry price '
                            f'{initial_entry_price}. Current position size = {position_size}')
            else:
                accumulated_qty = initial_entry_order.quantity
        else:
            if position_side == PositionSide.LONG:
                initial_entry_price = max(level_prices)
            else:
                initial_entry_price = min(level_prices)
            wallet_balance = self.exchange_state.symbol_balance(symbol)
            initial_cost_amount = wallet_balance * wallet_exposure * dca_config.initial_entry_size
            min_entry_qty = calc_min_qty(price=initial_entry_price,
                                         inverse=False,
                                         qty_step=symbol_information.quantity_step,
                                         min_qty=symbol_information.minimum_quantity,
                                         min_cost=symbol_information.minimal_buy_cost)
            max_entry_qty = round_(cost_to_quantity(cost=initial_cost_amount,
                                                    price=initial_entry_price,
                                                    inverse=False),
                                   step=symbol_information.quantity_step)
            accumulated_qty = max(min_entry_qty, max_entry_qty)

        quantities: List[float] = []
        desired_qty = None
        for i in range(max(len(level_prices), dca_config.minimum_number_dca_quantities)):
            if dca_config.previous_quantity_multiplier is not None:
                if desired_qty is None:
                    desired_qty = accumulated_qty
                else:
                    desired_qty = round_dn(desired_qty * dca_config.previous_quantity_multiplier, step=symbol_information.quantity_step)
            elif dca_config.dca_quantity_multiplier is not None:
                desired_qty = round_dn(accumulated_qty * dca_config.dca_quantity_multiplier, step=symbol_information.quantity_step)
            if i < len(level_prices):
                level_price = level_prices[i]
                if desired_qty == 0:
                    continue
                # skip quantity if the cost is less than the minimum allowed buy (LONG) or sell (SHORT) cost
                if position_side == PositionSide.LONG and symbol_information.minimal_buy_cost is not None and \
                        desired_qty * level_price < symbol_information.minimal_buy_cost:
                    continue
                if position_side == PositionSide.SHORT and symbol_information.minimal_sell_cost is not None and \
                        desired_qty * level_price < symbol_information.minimal_sell_cost:
                    continue

                min_entry_qty = calc_min_qty(price=level_price,
                                             inverse=False,
                                             qty_step=symbol_information.quantity_step,
                                             min_qty=symbol_information.minimum_quantity,
                                             min_cost=symbol_information.minimal_buy_cost if position_side == PositionSide.LONG else symbol_information.minimal_sell_cost)
                desired_qty = max(min_entry_qty, desired_qty)

            logger.debug(f'{symbol} {position_side.name}: accumulated_qty={accumulated_qty:10f}, order qty={desired_qty:10f}')
            accumulated_qty += desired_qty
            quantities.append(desired_qty)
        return quantities

    @staticmethod
    def _calculate_dca_quantities_final_size(symbol: str,
                                             position_side: PositionSide,
                                             steps: int,
                                             max_size: float,
                                             ratio_power: float) -> List[float]:
        """Creates a Geometric Progression with the Geometric sum of <n>
        The ratio r is the bee's knee ... it's how we also alter the curve of the progression
        1+5**0.5 is a standard 1.618 progression with a very small initial order
        """
        ratio = (1 + 5 ** ratio_power) / 2
        dca_quantities = [(max_size * (1 - ratio) / (1 - ratio ** steps)) * ratio ** i for i in range(steps)]
        logger.debug(f'{symbol} {position_side.name}: DCA quantities based on maximum_position_coin_size of '
                     f'{max_size} and {steps} steps are:')
        [logger.debug(f"{i}: {q}") for i, q in enumerate(dca_quantities)]
        logger.debug(f'sum = {sum(dca_quantities)}')
        return dca_quantities

    def calculate_first_dca_quantity_price_long(self,
                                                symbol: str,
                                                symbol_information: SymbolInformation,
                                                wallet_balance: float,
                                                wallet_exposure: float,
                                                current_price: float,
                                                position: Position,
                                                dca_config: DcaConfig) -> QuantityPrice:
        position_side = position.position_side
        dca_quantities = self.gridstorage_plugin.get_quantities(symbol=symbol, position_side=position_side)

        maximum_cost = wallet_balance * wallet_exposure
        dca_cost_on_exchange = self.exchange_state.open_dca_cost(symbol=symbol, position_side=position_side)
        free_cost = maximum_cost - dca_cost_on_exchange - position.cost

        if self.position_small_enough_for_dca_above(symbol=symbol,
                                                    position=position,
                                                    symbol_information=symbol_information,
                                                    dca_quantities=dca_quantities,
                                                    dca_config=dca_config):
            if self.support_price_available_above_top_dca(symbol=symbol,
                                                          current_price=current_price,
                                                          position_side=position_side):
                # determine the next smaller DCA quantity
                quantity_records = self.gridstorage_plugin.get_quantities(symbol=symbol, position_side=position_side)
                min_exchange_dca_qty = self.exchange_state.smallest_dca_quantity_on_exchange(symbol=symbol, position_side=position_side)
                quantity_records = [record for record in quantity_records if
                                    0 < record.quantity < min_exchange_dca_qty]
                if len(quantity_records) == 0:
                    logger.info(f'{symbol} {position_side.name}: There is no DCA quantity found below the smallest DCA '
                                f'quantity currently on the exchange {min_exchange_dca_qty}')
                    return None

                new_dca_quantity = min([record.quantity for record in quantity_records])
                new_dca_price = self.next_higher_support_price(symbol=symbol, position_side=position_side)
                next_dca_cost = new_dca_quantity * new_dca_price
                if next_dca_cost <= free_cost:
                    highest_dca = self.exchange_state.highest_dca_price_on_exchange(symbol=symbol, position_side=position_side)
                    user_log.info(f"{symbol} {position_side.name}: Creating DCA with quantity {new_dca_quantity} at "
                                  f"price {new_dca_price} above DCA located at price {highest_dca} because the "
                                  f"required cost of {next_dca_cost} is less than available funds {free_cost}",
                                  __name__)
                    return QuantityPrice(quantity=new_dca_quantity, price=new_dca_price)
                else:
                    logger.info(f'{symbol} {position_side.name}: The available funds of {free_cost:.2f} are '
                                f'insufficient to cover a new DCA to be placed at a price of {new_dca_price} with a '
                                f'quantity of {new_dca_quantity}, costing {next_dca_cost}')
                    return None
            else:
                shifted_grid = self.shifted_grid_long(symbol=symbol,
                                                      symbol_information=symbol_information,
                                                      dca_quantities=dca_quantities,
                                                      maximum_cost=maximum_cost,
                                                      position_side=position_side)
                if shifted_grid is not None:
                    shifted_grid.sort(key=lambda o: o.price, reverse=True)
                    first_order = shifted_grid[0]
                    return QuantityPrice(quantity=first_order.quantity, price=first_order.price)
        elif self.support_price_available_below_lowest_dca(symbol=symbol, position_side=position_side):
            # the position is not small enough to place a new DCA on top,
            # instead see if we can place a new DCA below the lowest one
            new_dca_price = self.next_lower_support_price(symbol=symbol, position_side=position_side)
            new_dca_quantity = self.next_bigger_dca_quantity(symbol=symbol,
                                                             dca_quantities=dca_quantities,
                                                             position_side=position_side)
            if new_dca_quantity is None:
                logger.debug(f"{symbol} {position_side.name}: There is now new DCA quantity below the lowest DCA, not "
                             f"adjusting grid.")
                return None
            new_dca_cost = new_dca_price * new_dca_quantity
            if free_cost >= new_dca_cost:
                user_log.info(
                    f'{symbol} {position_side.name}: Creating a new lower DCA at a price of {new_dca_price} with '
                    f'a quantity of {new_dca_quantity} resulting in a cost of {new_dca_cost} because the funds '
                    f'available ({free_cost}) are sufficient to create a new lower DCA', __name__)
                dca_orders = self.exchange_state.open_dca_orders(symbol=symbol, position_side=position_side)
                dca_orders.sort(key=lambda o: o.price, reverse=True)
                first_dca = dca_orders[0]
                return QuantityPrice(quantity=first_dca.quantity, price=first_dca.price)
            else:
                logger.debug(f'Not creating a new lower DCA at a price of {new_dca_price} with a quantity of '
                             f'{new_dca_quantity} resulting in a cost of {new_dca_cost} because the funds available '
                             f'({free_cost:.2f}) are not sufficient to create a new lower DCA')
        return None

    def shifted_grid_long(self,
                          symbol: str,
                          symbol_information: SymbolInformation,
                          dca_quantities: List[QuantityRecord],
                          maximum_cost: float,
                          position_side: PositionSide) -> List[Order]:
        # there's a price available below the current DCA grid,
        # calculate the cost of shifting the entire DCA grid to calculate the next_dca_cost
        shifted_grid = []
        shifted_grid_cost = 0.0
        dca_orders_on_exchange = self.exchange_state.open_dca_orders(symbol, position_side=position_side)
        sorted_dca_orders_on_exchange = list(dca_orders_on_exchange)
        sorted_dca_orders_on_exchange.sort(key=lambda x: x.price, reverse=True)
        highest_exchange_dca_price = self.exchange_state.highest_dca_price_on_exchange(symbol=symbol,
                                                                                       position_side=position_side)
        next_smaller_dca_quantity = self.next_smaller_dca_quantity(symbol=symbol,
                                                                   dca_quantities=dca_quantities,
                                                                   position_side=position_side)

        # add the first order on top
        shifted_grid.append(LimitOrder(order_type_identifier=OrderTypeIdentifier.DCA,
                                       symbol=symbol_information.symbol,
                                       quantity=next_smaller_dca_quantity,
                                       side=Side.BUY,
                                       position_side=position_side,
                                       initial_entry=False,
                                       price=highest_exchange_dca_price))

        # shift the grid down except for the lowest order
        for i in range(1, len(sorted_dca_orders_on_exchange)):
            # the last order is added separately after the shift
            current_order = sorted_dca_orders_on_exchange[i]
            above_order = sorted_dca_orders_on_exchange[i - 1]
            shifted_grid.append(LimitOrder(order_type_identifier=OrderTypeIdentifier.DCA,
                                           symbol=symbol_information.symbol,
                                           quantity=above_order.quantity,
                                           side=position_side.increase_side(),
                                           position_side=position_side,
                                           initial_entry=False,
                                           price=current_order.price))

        # add the order below the previous grid
        new_lower_quantity = self.exchange_state.biggest_dca_quantity_on_exchange(symbol=symbol, position_side=position_side)
        new_lower_price = self.next_lower_support_price(symbol=symbol, position_side=position_side)
        if new_lower_price is None:
            lowest_dca_on_exchange = self.exchange_state.lowest_dca_price_on_exchange(symbol=symbol, position_side=position_side)
            user_log.info(f'{symbol} {position_side.name}: Unable to shift the DCA grid down for a new DCA on top '
                          f'because there is no support available below the currently lowest support of '
                          f'{lowest_dca_on_exchange}')
            return None
        shifted_grid.append(LimitOrder(order_type_identifier=OrderTypeIdentifier.DCA,
                                       symbol=symbol_information.symbol,
                                       quantity=new_lower_quantity,
                                       side=position_side.increase_side(),
                                       position_side=position_side,
                                       initial_entry=False,
                                       price=new_lower_price))

        for order in shifted_grid:
            shifted_grid_cost += order.cost

        if shifted_grid_cost <= maximum_cost:
            user_log.info(f'{symbol} {position_side.name}: Shifting DCA grid down to make room for a new DCA on top '
                          f'with a quantity of {next_smaller_dca_quantity} at a price of {highest_exchange_dca_price}. '
                          f'The lowest DCA will be created with a quantity of {new_lower_quantity} at a price of '
                          f'{new_lower_price}', __name__)
            return shifted_grid
        else:
            user_log.info(f'{symbol} {position_side.name}: Available funds of {maximum_cost:.2f} are not enough to '
                          f'shift DCA grid down for a new DCA with a quantity of {new_lower_quantity} at a price of '
                          f'{new_lower_price} which requires {shifted_grid_cost:.2f} to be available. There is '
                          f'no support price above the current highest DCA price of '
                          f'{highest_exchange_dca_price}', __name__)
            return None

    def position_small_enough_for_dca_above(self,
                                            symbol: str,
                                            position: Position,
                                            symbol_information: SymbolInformation,
                                            dca_quantities: List[QuantityRecord],
                                            dca_config: DcaConfig) -> bool:
        position_side = position.position_side
        if dca_config.allow_add_new_smaller_dca is False:
            logger.debug(f'{symbol} {position_side.name}: Not checking if a new DCA can be placed on top, because the parameter \'allow_add_new_smaller_dca\' is set to False')
            return False

        position_size = position.position_size
        min_exchange_dca_qty = self.exchange_state.smallest_dca_quantity_on_exchange(symbol=symbol,
                                                                                     position_side=position_side)
        if min_exchange_dca_qty is None:
            logger.info(f'{symbol} {position_side.name}: There is currently no DCA order found on the exchange')
            return False

        smaller_quantity_records = [record for record in dca_quantities if record.quantity < min_exchange_dca_qty]
        if len(smaller_quantity_records) == 0:
            logger.info(f'{symbol} {position_side.name}: There are no DCA quantities available smaller than '
                        f'{min_exchange_dca_qty}, not able to create a new smaller DCA')
            return False

        next_smaller_dca_qty = max([record.quantity for record in smaller_quantity_records])
        next_smaller_dca_record = [record for record in dca_quantities if record.quantity == next_smaller_dca_qty][0]
        highest_dca = self.exchange_state.highest_dca_price_on_exchange(symbol=symbol, position_side=position_side)
        margin = dca_config.quantity_unit_margin * symbol_information.quantity_step
        if position_size <= next_smaller_dca_record.max_position_size + margin:
            logger.info(f'{symbol} {position_side.name}: Position size of {position_size} is less than or equal than '
                        f'the expected max position size of {next_smaller_dca_record.max_position_size} + {margin} '
                        f'margin, a new DCA can potentially be placed above the support of quantity '
                        f'{min_exchange_dca_qty} located at a price of {highest_dca}')
            return True
        else:
            logger.info(f'{symbol} {position_side.name}: Position size of {position_size} exceeds the expected max '
                        f'position size of {next_smaller_dca_record.max_position_size}, a new DCA is not allowed to be '
                        f'placed above the highest support at a quantity of {min_exchange_dca_qty} located at a price '
                        f'of {highest_dca}')
            return False

    def support_price_available_above_top_dca(self,
                                              symbol: str,
                                              current_price: float,
                                              position_side: PositionSide) -> bool:
        next_higher_support_price = self.next_higher_support_price(symbol=symbol, position_side=position_side)
        max_exchange_dca_price = self.exchange_state.highest_dca_price_on_exchange(symbol=symbol,
                                                                                   position_side=position_side)

        if next_higher_support_price is not None:
            if next_higher_support_price < current_price:
                logger.info(f'{symbol} {position_side.name}: There is a support price available above the the '
                            f'currently highest DCA price of {max_exchange_dca_price}')
                return True
            else:
                logger.info(f'{symbol} {position_side.name}: There is a support price available above the currently '
                            f'highest DCA price of {max_exchange_dca_price}, but it is above the current price of '
                            f'{current_price}, so unable put a DCA there')
        else:
            logger.info(f'There are no support prices available above the currently highest DCA price '
                        f'of {max_exchange_dca_price}')
            return False

    def support_price_available_below_lowest_dca(self,
                                                 symbol: str,
                                                 position_side: PositionSide) -> bool:
        next_lower_support_price = self.next_lower_support_price(symbol=symbol, position_side=position_side)
        lowest_dca_price = self.exchange_state.lowest_dca_price_on_exchange(symbol=symbol,
                                                                            position_side=position_side)
        if next_lower_support_price is not None:
            logger.debug(f'{symbol} {position_side.name}: There is a support price available below the lowest DCA '
                         f'price on the exchange {lowest_dca_price}, being {next_lower_support_price}')
            return True
        else:
            logger.info(f'{symbol} {position_side.name}: There are no support prices available below the lowest DCA '
                        f'price on the exchange of {lowest_dca_price}')
            return False

    def next_higher_support_price(self,
                                  symbol: str,
                                  position_side: PositionSide) -> float:
        max_exchange_dca_price = self.exchange_state.highest_dca_price_on_exchange(symbol=symbol,
                                                                                   position_side=position_side)
        support_prices = self.gridstorage_plugin.get_prices(symbol=symbol, position_side=position_side)
        higher_support_prices = [price for price in support_prices if price > max_exchange_dca_price]
        if len(higher_support_prices) > 0:
            return min(higher_support_prices)
        else:
            return None

    def next_lower_support_price(self,
                                 symbol: str,
                                 position_side: PositionSide) -> float:
        min_exchange_dca_price = self.exchange_state.lowest_dca_price_on_exchange(symbol=symbol,
                                                                                  position_side=position_side)
        support_prices = self.gridstorage_plugin.get_prices(symbol=symbol, position_side=position_side)
        lower_support_prices = [price for price in support_prices if price < min_exchange_dca_price]
        if len(lower_support_prices) > 0:
            return max(lower_support_prices)
        else:
            return None

    def next_smaller_dca_quantity(self, symbol: str,
                                  dca_quantities: List[QuantityRecord],
                                  position_side: PositionSide) -> float:
        min_exchange_dca_qty = self.exchange_state.smallest_dca_quantity_on_exchange(symbol=symbol,
                                                                                     position_side=position_side)
        smaller_quantity_records = [record for record in dca_quantities if record.quantity < min_exchange_dca_qty]
        if len(smaller_quantity_records) == 0:
            logger.info(f'{symbol} {position_side.name}: There is no DCA quantity available small than the biggest '
                        f'DCA quantity currently on the exchange of {min_exchange_dca_qty}')
            return None
        else:
            return max([record.quantity for record in smaller_quantity_records])

    def next_bigger_dca_quantity(self,
                                 symbol: str,
                                 dca_quantities: List[QuantityRecord],
                                 position_side: PositionSide) -> float:
        max_exchange_dca_qty = self.exchange_state.biggest_dca_quantity_on_exchange(symbol=symbol,
                                                                                    position_side=position_side)
        bigger_quantity_records = [record for record in dca_quantities if record.quantity > max_exchange_dca_qty]
        if len(bigger_quantity_records) == 0:
            logger.info(f'{symbol} {position_side.name}: There is no DCA quantity available bigger than the biggest '
                        f'DCA quantity currently on the exchange of {max_exchange_dca_qty}')
            return None
        else:
            return min([record.quantity for record in bigger_quantity_records])

    # SHORT
    def _initialize_unlimited_grid_short(self,
                                         symbol: str,
                                         position_side: PositionSide,
                                         symbol_information: SymbolInformation,
                                         minimum_price: float,
                                         dca_config: DcaConfig,
                                         initial_cost: float,
                                         wallet_exposure: float,
                                         reset_quantities: bool = True,
                                         enforce_nr_clusters: bool = True):
        self.gridstorage_plugin.reset(symbol=symbol, position_side=position_side)
        self.gridstorage_plugin.store_root_price(symbol=symbol, position_side=position_side, price=minimum_price)
        resistance_price_records = self.calculate_resistance_prices(symbol=symbol,
                                                                    position_side=position_side,
                                                                    minimum_price=minimum_price,
                                                                    dca_config=dca_config,
                                                                    enforce_nr_clusters=enforce_nr_clusters)
        self.gridstorage_plugin.store_prices(symbol=symbol, prices_records=resistance_price_records)
        for price_record in resistance_price_records:
            logger.info(f'{symbol} {position_side.name}: Stored grid resistance price {price_record.price}')
        if reset_quantities:
            self.gridstorage_plugin.reset_quantities(symbol=symbol, position_side=position_side)

            accumulated_qty = 0.0

            quantities: List[QuantityRecord] = []
            dca_quantities = self._calculate_dca_quantities(symbol=symbol,
                                                            position_side=position_side,
                                                            dca_config=dca_config,
                                                            level_prices=[r.price for r in resistance_price_records],
                                                            nr_clusters=dca_config.nr_clusters,
                                                            symbol_information=symbol_information,
                                                            initial_cost=initial_cost,
                                                            wallet_exposure=wallet_exposure)

            for dca_quantity in dca_quantities:
                accumulated_qty += dca_quantity
                rounded_quantity = round_(dca_quantity, symbol_information.quantity_step)
                quantity_record = QuantityRecord(position_side=position_side,
                                                 quantity=rounded_quantity,
                                                 accumulated_quantity=accumulated_qty,
                                                 raw_quantity=dca_quantity)
                logger.info(f'{symbol} {position_side.name}: accumulated_qty={accumulated_qty}, '
                            f'order qty={rounded_quantity}, raw qty={dca_quantity}')
                quantities.append(quantity_record)

            self.gridstorage_plugin.store_quantities(symbol=symbol, quantities=quantities)
        logging.info(f'{symbol} {position_side.name}: Initialized unlimited grid')

    def calculate_resistance_prices(self,
                                    symbol: str,
                                    position_side: PositionSide,
                                    minimum_price: float,
                                    dca_config: DcaConfig,
                                    enforce_nr_clusters: bool = True) -> List[PriceRecord]:
        if dca_config.enabled is False:
            return []
        price_step = self.exchange_state.get_symbol_information(symbol).price_step
        maximum_symbol_price = self.exchange_state.get_symbol_information(symbol).maximum_price
        timeframe = dca_config.period_timeframe
        support_resistance = self.sr_plugin.get_support_resistance_levels(symbol=symbol,
                                                                          position_side=position_side,
                                                                          even_price=minimum_price,
                                                                          price_step=price_step,
                                                                          dca_config=dca_config)
        final_resistance_list = support_resistance.resistances
        for support in support_resistance.supports:
            min_support_overlap_price = support * (1 - dca_config.overlap)
            max_support_overlap_price = support * (1 + dca_config.overlap)
            resistance_overlaps = False
            for resistance in final_resistance_list:
                if min_support_overlap_price <= resistance <= max_support_overlap_price:
                    resistance_overlaps = True
                    break
            if not resistance_overlaps and support > minimum_price:
                final_resistance_list.append(support)

        resistance_prices = [PriceRecord(position_side=position_side, price=price)
                             for price in final_resistance_list if price <= maximum_symbol_price]
        resistance_prices.sort(key=lambda r: r.price)
        if dca_config.minimum_distance_between_levels is not None:
            filtered_resistance_prices = []
            previous_resistance_price = None
            for resistance_price in resistance_prices:
                if previous_resistance_price is not None:
                    if previous_resistance_price.price * (1 + dca_config.minimum_distance_between_levels) < resistance_price.price:
                        filtered_resistance_prices.append(resistance_price)
                previous_resistance_price = resistance_price

            resistance_prices = filtered_resistance_prices

        if dca_config.nr_clusters is not None:
            if len(resistance_prices) < dca_config.nr_clusters:
                if enforce_nr_clusters:
                    logger.warning(f'{symbol} {position_side.name}: The number of calculated resistances is '
                                   f'{len(resistance_prices)}, while the number of configured clusters is '
                                   f'{dca_config.nr_clusters}. Not using the calculated levels due to not being able to '
                                   f'match the specified nr_clusters. This can likely be solved by adding more history, or '
                                   f'by changing nr_clusters.')
                    return []
                else:
                    logger.warning(f'{symbol} {position_side.name}: The number of calculated resistances is '
                                   f'{len(resistance_prices)}, while the number of configured clusters is '
                                   f'{dca_config.nr_clusters}. Explicit instruction is to ignore this, so returning the '
                                   f'found support-prices none-the-less.')

        return resistance_prices

    def resistance_price_available_below_bottom_dca(self,
                                                    symbol: str,
                                                    current_price: float,
                                                    position_side: PositionSide) -> bool:
        next_lower_resistance_price = self.next_lower_resistance_price(symbol=symbol, position_side=position_side)
        min_exchange_dca_price = self.exchange_state.lowest_dca_price_on_exchange(symbol=symbol,
                                                                                  position_side=position_side)

        if next_lower_resistance_price is not None:
            if min_exchange_dca_price > current_price:
                logger.info(f'There is a resistance price available below the the currently lowest DCA price of '
                            f'{min_exchange_dca_price}')
                return True
            else:
                logger.info(f'There is a resistance price available below the currently lowest DCA price of '
                            f'{min_exchange_dca_price}, but it is below the current price of {current_price}, '
                            f'so unable put a DCA there')
        else:
            logger.info(f'There are no resistance prices available below the currently lowest DCA price '
                        f'of {min_exchange_dca_price}')
            return False

    def resistance_price_available_above_highest_dca(self,
                                                     symbol: str,
                                                     position_side: PositionSide) -> bool:
        next_higher_resistance_price = self.next_higher_resistance_price(symbol=symbol, position_side=position_side)
        highest_dca_price_on_exchange = self.exchange_state \
            .highest_dca_price_on_exchange(symbol=symbol,
                                           position_side=position_side)
        if next_higher_resistance_price is not None:
            logger.debug(f'There is a resistance price available above the highest DCA price on the exchange '
                         f'{highest_dca_price_on_exchange}, being {next_higher_resistance_price}')
            return True
        else:
            logger.debug(f'There is no resistance price available above the highest DCA price on the exchange of '
                         f'{highest_dca_price_on_exchange}')
            return False

    def shifted_grid_short(self,
                           symbol: str,
                           symbol_information: SymbolInformation,
                           dca_quantities: List[QuantityRecord],
                           position_side: PositionSide) -> List[Order]:
        # there's a price available below the current DCA grid,
        # calculate the cost of shifting the entire DCA grid to calculate the next_dca_cost
        shifted_grid = []
        dca_orders_on_exchange = self.exchange_state.open_dca_orders(symbol, position_side=position_side)
        sorted_dca_orders_on_exchange = list(dca_orders_on_exchange)
        sorted_dca_orders_on_exchange.sort(key=lambda x: x.price)
        lowest_exchange_dca_price = self.exchange_state.lowest_dca_price_on_exchange(symbol=symbol,
                                                                                     position_side=position_side)
        next_smaller_dca_quantity = self.next_smaller_dca_quantity(symbol=symbol,
                                                                   dca_quantities=dca_quantities,
                                                                   position_side=position_side)

        # add the first order on top
        shifted_grid.append(LimitOrder(order_type_identifier=OrderTypeIdentifier.DCA,
                                       symbol=symbol_information.symbol,
                                       quantity=next_smaller_dca_quantity,
                                       side=position_side.increase_side(),
                                       position_side=position_side,
                                       initial_entry=False,
                                       price=lowest_exchange_dca_price))

        # shift the grid up except for the lowest order
        for i in range(1, len(sorted_dca_orders_on_exchange)):
            # the last order is added separately after the shift
            current_order = sorted_dca_orders_on_exchange[i]
            above_order = sorted_dca_orders_on_exchange[i - 1]
            shifted_grid.append(LimitOrder(order_type_identifier=OrderTypeIdentifier.DCA,
                                           symbol=symbol_information.symbol,
                                           quantity=above_order.quantity,
                                           side=position_side.increase_side(),
                                           position_side=position_side,
                                           initial_entry=False,
                                           price=current_order.price))

        # On shorts the higher DCA will immediately prevent shifting the grid. Instead we'll allow shifting while not
        # creating a new DCA higher up

        # shifted_grid.append(LimitOrder(order_type_identifier=OrderTypeIdentifier.DCA,
        #                                symbol=symbol_information.symbol,
        #                                quantity=new_higher_quantity,
        #                                side=Side.SELL,
        #                                position_side=PositionSide.SHORT,
        #                                initial_entry=False,
        #                                price=new_higher_price))

        user_log.info(f'{symbol} {position_side.name}: Shifting DCA grid up to make room for a new DCA below '
                      f'with a quantity of {next_smaller_dca_quantity} at a price of {lowest_exchange_dca_price}.',
                      __name__)
        return shifted_grid

    def next_lower_resistance_price(self,
                                    symbol: str,
                                    position_side: PositionSide) -> float:
        min_exchange_dca_price = self.exchange_state.lowest_dca_price_on_exchange(symbol=symbol,
                                                                                  position_side=position_side)
        resistance_prices = self.gridstorage_plugin.get_prices(symbol=symbol, position_side=position_side)
        lower_resistance_prices = [price for price in resistance_prices if price < min_exchange_dca_price]
        if len(lower_resistance_prices) > 0:
            return max(lower_resistance_prices)
        else:
            return None

    def next_higher_resistance_price(self,
                                     symbol: str,
                                     position_side: PositionSide) -> float:
        max_exchange_dca_price = self.exchange_state.highest_dca_price_on_exchange(symbol=symbol,
                                                                                   position_side=position_side)
        resistance_prices = self.gridstorage_plugin.get_prices(symbol=symbol, position_side=position_side)
        higher_resistance_prices = [price for price in resistance_prices if price > max_exchange_dca_price]
        if len(higher_resistance_prices) > 0:
            return min(higher_resistance_prices)
        else:
            return None

    def position_small_enough_for_dca_below(self,
                                            symbol: str,
                                            position: Position,
                                            symbol_information: SymbolInformation,
                                            dca_quantities: List[QuantityRecord],
                                            dca_config: DcaConfig) -> bool:
        position_side = position.position_side
        if dca_config.allow_add_new_smaller_dca is False:
            logger.debug(f'{symbol} {position_side.name}: Not checking if a new DCA can be placed below, because the parameter \'allow_add_new_smaller_dca\' is set to False')
            return False

        position_size = position.position_size
        min_exchange_dca_qty = self.exchange_state.smallest_dca_quantity_on_exchange(symbol=symbol,
                                                                                     position_side=position_side)
        if min_exchange_dca_qty is None:
            logger.info(f'{symbol} {position_side.name}: There is no DCA order on the exchange, not able to determine '
                        f'a new smaller DCA should be placed on the exchange')
            return False

        smaller_quantity_records = [record for record in dca_quantities if record.quantity < min_exchange_dca_qty]
        if len(smaller_quantity_records) == 0:
            logger.info(f'{symbol} {position_side.name}: There are no DCA quantities available smaller than '
                        f'{min_exchange_dca_qty}, not able to create a new smaller DCA')
            return False

        next_smaller_dca_qty = max([record.quantity for record in smaller_quantity_records])
        next_smaller_dca_record = [record for record in dca_quantities if record.quantity == next_smaller_dca_qty][0]
        lowest_dca = self.exchange_state.lowest_dca_price_on_exchange(symbol=symbol, position_side=position_side)
        margin = dca_config.quantity_unit_margin * symbol_information.quantity_step
        if position_size <= next_smaller_dca_record.max_position_size + margin:
            logger.info(f'{symbol} {position_side.name}: Position size of {position_size} is less than or equal than '
                        f'the expected max position size of {next_smaller_dca_record.max_position_size} + {margin} '
                        f'margin, a new DCA can potentially be placed below the resistance of quantity '
                        f'{min_exchange_dca_qty} located at a price of {lowest_dca}')
            return True
        else:
            logger.info(f'{symbol} {position_side.name}: Position size of {position_size} + {next_smaller_dca_qty} '
                        f'exceeds the expected max position size of {next_smaller_dca_record.max_position_size}, a new '
                        f'DCA is NOT allowed to be placed below the lowest resistance at a quantity of '
                        f'{min_exchange_dca_qty} located at a price of {lowest_dca}')
            return False

    def calculate_first_dca_quantity_price_short(self,
                                                 symbol: str,
                                                 symbol_information: SymbolInformation,
                                                 wallet_balance: float,
                                                 wallet_exposure: float,
                                                 current_price: float,
                                                 position: Position,
                                                 dca_config: DcaConfig) -> QuantityPrice:
        position_side = position.position_side
        dca_quantities = self.gridstorage_plugin.get_quantities(symbol=symbol, position_side=position_side)

        maximum_cost = wallet_balance * wallet_exposure
        dca_cost_on_exchange = self.exchange_state.open_dca_cost(symbol=symbol, position_side=position_side)
        free_cost = maximum_cost - dca_cost_on_exchange - position.cost

        if self.position_small_enough_for_dca_below(symbol=symbol,
                                                    position=position,
                                                    symbol_information=symbol_information,
                                                    dca_quantities=dca_quantities,
                                                    dca_config=dca_config):
            if self.resistance_price_available_below_bottom_dca(symbol=symbol,
                                                                current_price=current_price,
                                                                position_side=position_side):
                # determine the next smaller DCA quantity
                quantity_records = self.gridstorage_plugin.get_quantities(symbol=symbol,
                                                                          position_side=position_side)
                min_exchange_dca_qty = self.exchange_state. \
                    smallest_dca_quantity_on_exchange(symbol=symbol,
                                                      position_side=position_side)
                quantity_records = [record for record in quantity_records if 0 < record.quantity < min_exchange_dca_qty]
                if len(quantity_records) == 0:
                    logger.info(f'{symbol} {position_side.name}: There is no DCA quantity found below the smallest DCA '
                                f'quantity currently on the exchange {min_exchange_dca_qty}')
                    return None

                new_dca_quantity = max([record.quantity for record in quantity_records])
                new_dca_price = self.next_lower_resistance_price(symbol=symbol, position_side=position_side)
                next_dca_cost = new_dca_quantity * new_dca_price
                if next_dca_cost <= free_cost:
                    lowest_dca_price = self.exchange_state \
                        .lowest_dca_price_on_exchange(symbol=symbol, position_side=position_side)
                    user_log.info(f"{symbol} {position_side.name}: Creating DCA with quantity {new_dca_quantity} at "
                                  f"price {new_dca_price} above DCA located at price {lowest_dca_price} because the "
                                  f"required cost of {next_dca_cost} is less than available funds {free_cost}",
                                  __name__)
                    return QuantityPrice(quantity=new_dca_quantity, price=new_dca_price)
                else:
                    logger.info(
                        f'The available funds of {free_cost:.2f} are insufficient to cover a new DCA to be placed at a '
                        f'price of {new_dca_price} with a quantity of {new_dca_quantity}, costing {next_dca_cost}')
                    return None
            else:
                shifted_grid = self.shifted_grid_short(symbol=symbol,
                                                       symbol_information=symbol_information,
                                                       dca_quantities=dca_quantities,
                                                       position_side=position_side)
                if shifted_grid is not None:
                    shifted_grid.sort(key=lambda o: o.price)
                    first_order = shifted_grid[0]
                    return QuantityPrice(quantity=first_order.quantity, price=first_order.price)
        elif self.resistance_price_available_above_highest_dca(symbol=symbol, position_side=position_side):
            # the position is not small enough to place a new DCA below,
            # instead see if we can place a new DCA on top of the highest one
            new_dca_price = self.next_higher_resistance_price(symbol=symbol, position_side=position_side)
            new_dca_quantity = self.next_bigger_dca_quantity(symbol=symbol,
                                                             dca_quantities=dca_quantities,
                                                             position_side=position_side)
            if new_dca_quantity is None:
                logger.debug(f"{symbol} {position_side.name}: There is now new DCA quantity below the lowest DCA, not "
                             f"adjusting grid.")
                return None
            new_dca_cost = new_dca_price * new_dca_quantity
            if free_cost >= new_dca_cost:
                user_log.info(
                    f'{symbol} {position_side.name}: Creating a new lower DCA at a price of {new_dca_price} with a '
                    f'quantity of {new_dca_quantity} resulting in a cost of {new_dca_cost} because the funds available '
                    f'({free_cost}) are sufficient to create a new lower DCA', __name__)
                dca_orders = self.exchange_state.open_dca_orders(symbol=symbol, position_side=position_side)
                dca_orders.sort(key=lambda o: o.price)
                first_dca = dca_orders[0]
                return QuantityPrice(quantity=first_dca.quantity, price=first_dca.price)
            else:
                logger.debug(f'Not creating a new lower DCA at a price of {new_dca_price} with a quantity of '
                             f'{new_dca_quantity} resulting in a cost of {new_dca_cost} because the funds available '
                             f'({free_cost:.2f}) are not sufficient to create a new lower DCA')
        return None

    def _calculate_dca_grid_from_first_short(self,
                                             symbol: str,
                                             position: Position,
                                             symbol_information: SymbolInformation,
                                             first_resistance_price: float,
                                             first_quantity: float) -> List[Order]:
        position_side = position.position_side
        # identify support prices based on current price & config
        all_dca_qtys = self.gridstorage_plugin.get_quantities(symbol=symbol, position_side=position_side)
        if not position.has_position():
            logger.warning('The code was called to create a DCA grid, but there is currently no open position on '
                           'the exchange. This situation should auto-correct on the next synchronisation round.')
            return []

        position_size = position.position_size
        available_dca_qtys = [record for record in all_dca_qtys
                              if record.quantity >= first_quantity]
        if len(available_dca_qtys) == 0:
            user_log.info(f"{symbol}: There are no DCA orders on the exchange, but there are no quantities available "
                          f"based on position size {position_size}", __name__)
            return []

        resistance_price_records = self.gridstorage_plugin.get_prices(symbol=symbol, position_side=position_side)
        resistance_prices = [price for price in resistance_price_records if price >= first_resistance_price]
        resistance_prices.sort()

        current_price = self.exchange_state.last_tick_price(symbol)
        highest_price = symbol_information.highest_allowed_price(current_price=current_price)
        dca_orders = []
        for i in range(len(available_dca_qtys)):
            quantity_record = available_dca_qtys[i]
            dca_quantity = quantity_record.quantity
            if len(resistance_prices) <= i:
                logger.info(f'{symbol} {position_side.name}: There are only {len(resistance_prices)} available, while '
                            f'there are {len(available_dca_qtys)} DCA quantities available.')
                break
            dca_price = resistance_prices[i]
            if dca_price > highest_price:
                logger.warning(f"{symbol} {position_side.name}: The desired DCA price of {dca_price} is more than the "
                               f"highest allowed price of {highest_price}, stopping further DCA calculation. Current "
                               f"price = {current_price}, symbol information = {symbol_information}")
                break
            order = LimitOrder(order_type_identifier=OrderTypeIdentifier.DCA,
                               symbol=symbol_information.symbol,
                               quantity=dca_quantity,
                               side=Side.SELL,
                               position_side=position_side,
                               initial_entry=False,
                               price=round_(dca_price, symbol_information.price_step))
            dca_orders.append(order)
        return dca_orders

    def calculate_dca_grid_short(self,
                                 symbol: str,
                                 position: Position,
                                 symbol_information: SymbolInformation,
                                 wallet_balance: float,
                                 wallet_exposure: float,
                                 current_price: float,
                                 dca_config: DcaConfig) -> List[Order]:
        position_side = position.position_side
        first_quantity_price = None

        if self.exchange_state.no_dca_orders_on_exchange(symbol=symbol, position_side=position_side):
            logger.info(f'{symbol} {position_side.name}: No DCA orders on the exchange')
            resistance_prices = self.gridstorage_plugin.get_prices(symbol=symbol, position_side=position_side)
            resistance_prices = [price for price in resistance_prices if price >= current_price]
            try:
                resistance_prices = [price for price in resistance_prices
                                     if price > self.exchange_state.position(symbol=symbol,
                                                                             position_side=position_side).entry_price]
            except NoInitialEntryOrderException:
                logger.debug(f'{symbol} {position_side.name}: No initial entry found, ignoring filtering out prices below position price')

            resistance_prices.sort(reverse=True)
            if len(resistance_prices) > 0:
                # first DCA quantity is for the initial entry
                dca_quantities = self.gridstorage_plugin.get_quantities(symbol=symbol, position_side=position_side)[1:]
                margin = dca_config.quantity_unit_margin * symbol_information.quantity_step
                logger.info(f'{symbol} {position_side.name}: Selecting initial DCA quantities with a max position '
                            f'smaller or equal to {position.position_size} + {margin} margin')
                available_quantities = [record.quantity for record in dca_quantities
                                        if position.position_size <= record.max_position_size + margin]
                if len(available_quantities) > 0:
                    first_quantity_price = QuantityPrice(min(available_quantities), min(resistance_prices))
            else:
                logger.info(f'{symbol} {position_side.name}: Found 0 resistance prices, this situation is expected to '
                            f'auto correct on the next periodic check.')
        else:
            first_quantity_price = self.calculate_first_dca_quantity_price_short(symbol=symbol,
                                                                                 symbol_information=symbol_information,
                                                                                 wallet_balance=wallet_balance,
                                                                                 wallet_exposure=wallet_exposure,
                                                                                 current_price=current_price,
                                                                                 position=position,
                                                                                 dca_config=dca_config)
        if first_quantity_price is not None:
            return self._calculate_dca_grid_from_first_short(symbol=symbol,
                                                             position=position,
                                                             symbol_information=symbol_information,
                                                             first_resistance_price=first_quantity_price.price,
                                                             first_quantity=first_quantity_price.quantity)
        else:
            return self.exchange_state.open_dca_orders(symbol=symbol, position_side=position.position_side)

    def grid_initialized(self, symbol: str, position_side: PositionSide, dca_config: DcaConfig) -> bool:
        if dca_config.enabled is False:
            return False
        return self.gridstorage_plugin.is_correctly_filled_for(symbol=symbol, position_side=position_side)

    def erase_grid(self, symbol: str, position_side: PositionSide, dca_config: DcaConfig):
        if dca_config.enabled:
            self.gridstorage_plugin.reset(symbol=symbol, position_side=position_side)
