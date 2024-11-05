import logging

from datetime import datetime, timezone

from redis import Redis

from hawkbot.core.data_classes import OrderStatus, SymbolInformation, Side, PositionSide, OrderTypeIdentifier, Position
from hawkbot.core.dynamic_entry.dynamic_entry_selector import DynamicEntrySelector
from hawkbot.core.model import LimitOrder, MarketOrder, Timeframe
from hawkbot.core.strategy.data_classes import InitializeConfig
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.logging import user_log
from hawkbot.plugins.clustering_sr.algo_type import AlgoType
from hawkbot.plugins.clustering_sr.algos.algo import Algo
from hawkbot.strategies.abstract_base_strategy import AbstractBaseStrategy
from hawkbot.utils import calc_min_qty, calc_diff, readable_pct, period_as_ms, fill_optional_parameters

logger = logging.getLogger(__name__)


class CatcherEquilibriumLongStrategy(AbstractBaseStrategy):
    def __init__(self):
        super().__init__()
        self.entry_order_type: str = None
        self.limit_orders_reissue_threshold: float = None
        self.override_insufficient_grid_funds: bool = None
        self.no_entry_within_resistance_distance: float = None
        self.no_entry_within_resistance_period: str = None
        self.no_entry_within_resistance_nr_clusters: int = None
        self.no_entry_within_resistance_timeframe: Timeframe = None
        self.no_entry_within_resistance_algo: Algo = None
        self.global_long_min_distance_pct: float = None
        self.equilibrium_timeframe: Timeframe = None
        self.repost_lower_allowed: bool = True
        self.execute_orders_enabled: bool = True
        self.redis = None

    def init_config(self):
        super().init_config()

        self.redis = Redis(host="127.0.0.1", port=self.redis_port, decode_responses=True)
        optional_parameters = ['no_entry_within_resistance_distance',
                               'no_entry_within_resistance_period',
                               'no_entry_within_resistance_nr_clusters',
                               'override_insufficient_grid_funds',
                               'global_long_min_distance_pct',
                               'equilibrium_timeframe',
                               'equilibrium_hour',
                               'repost_lower_allowed',
                               'execute_orders_enabled']
        fill_optional_parameters(target=self, config=self.strategy_config, optional_parameters=optional_parameters)

        if 'no_entry_within_resistance_timeframe' in self.strategy_config:
            self.no_entry_within_resistance_timeframe = Timeframe.parse(self.strategy_config["no_entry_within_resistance_timeframe"])
        if 'no_entry_within_resistance_algo' in self.strategy_config:
            algo_type = AlgoType[self.strategy_config["no_entry_within_resistance_algo"]]
            self.no_entry_within_resistance_algo = algo_type.value[1]()

        if self.no_entry_within_resistance_distance and self.no_entry_within_resistance_period is None:
            raise InvalidConfigurationException(f'When the parameter \'no_entry_within_resistance_distance\' is '
                                                f'specified, the missing parameter '
                                                f'\'no_entry_within_resistance_period\' is mandatory')

        if self.no_entry_within_resistance_distance and self.no_entry_within_resistance_timeframe is None:
            raise InvalidConfigurationException(f'When the parameter \'no_entry_within_resistance_distance\' is '
                                                f'specified, the missing parameter '
                                                f'\'no_entry_within_resistance_timeframe\' is mandatory')

        if self.no_entry_within_resistance_distance and self.no_entry_within_resistance_algo is None:
            raise InvalidConfigurationException(f'When the parameter \'no_entry_within_resistance_distance\' is '
                                                f'specified, the missing parameter \'no_entry_within_resistance_algo\' '
                                                f'is mandatory')
        
        if self.global_long_min_distance_pct is None:
            raise InvalidConfigurationException("Parameter 'global_long_min_distance_pct' is required.")
        
        if 'equilibrium_timeframe' in self.strategy_config:
            self.equilibrium_timeframe = Timeframe.parse(self.strategy_config['equilibrium_timeframe'])
        else:
            raise InvalidConfigurationException('The parameter \'equilibrium_timeframe\' is mandatory')

        if 'entry_order_type' in self.strategy_config:
            self.entry_order_type = self.strategy_config['entry_order_type']
        else:
            raise InvalidConfigurationException(f'{self.symbol} {self.position_side.name}: The field '
                                                f'\'entry_order_type\' is not defined')

        if self.entry_order_type not in ['MARKET', 'LIMIT']:
            raise InvalidConfigurationException(f'{self.symbol} {self.position_side.name}: The value '
                                                f'\'{self.entry_order_type}\' is not a valid value, only \'MARKET\' or '
                                                f'\'LIMIT\' is accepted.')

        if 'limit_orders_reissue_threshold' in self.strategy_config:
            self.limit_orders_reissue_threshold = self.strategy_config['limit_orders_reissue_threshold']
        elif self.entry_order_type == 'LIMIT':
            raise InvalidConfigurationException(f'{self.symbol} {self.position_side.name}: The parameter '
                                                f'\'limit_orders_reissue_threshold\' is mandatory when using '
                                                f'\'entry_order_type\' LIMIT orders but is not specified')

    def get_initializing_config(self) -> InitializeConfig:
        init_config = super().get_initializing_config()
        if self.no_entry_within_resistance_distance is not None:
            init_config.add_period(self.no_entry_within_resistance_timeframe, self.no_entry_within_resistance_period)

        return init_config

    def on_no_open_position(self,
                            symbol: str,
                            position: Position,
                            symbol_information: SymbolInformation,
                            wallet_balance: float,
                            current_price: float):
        position_side = position.position_side
        
        # retrieve the close price for the specified equilibrium time and timeframe
        last_close = self.get_utc_close_price(
            symbol,
            equilibrium_timeframe=self.equilibrium_timeframe,
            equilibrium_hour=self.strategy_config.get("equilibrium_hour", 17)
        )

        if last_close is None:
            logger.warning(f"Close price for the specified time not found for {symbol}.")
            return
        
        # check long distance conditions
        allow_long = current_price <= last_close * (1 - self.global_long_min_distance_pct / 100)
        if not allow_long:
            logger.info(f'{symbol}: Skipping action as allow_long condition is not met.')
            return

        if self.config.is_dynamic_entry and self.candidate_state.is_not_candidate_symbol(symbol=symbol, position_side=self.position_side):
            if self.exchange_state.has_no_open_position(symbol=symbol, position_side=self.position_side) \
                    and self.exchange_state.has_no_open_position(symbol=symbol, position_side=self.position_side.inverse()):
                logger.info(f'{symbol} {self.position_side.name}: Deactivating strategy because it\'s no longer a candidate symbol, '
                            f'and there\'s no position on either position side')
                self.redis.set(name=f'{DynamicEntrySelector.DEACTIVATABLE_SYMBOL_POSITIONSIDE}_{symbol}_{self.position_side.name}', value=int(True))
                return
        self.redis.set(name=f'{DynamicEntrySelector.DEACTIVATABLE_SYMBOL_POSITIONSIDE}_{symbol}_{self.position_side.name}', value=int(False))

        if self.hedge_plugin.is_hedge_applicable(symbol=symbol, position_side=position_side, hedge_config=self.hedge_config):
            existing_orders = self.exchange_state.open_entry_orders(symbol=symbol, position_side=position_side)
            hedge_orders = self.hedge_plugin.calculate_hedge_orders(symbol=symbol,
                                                                    position_side=position_side,
                                                                    symbol_information=symbol_information,
                                                                    wallet_balance=wallet_balance,
                                                                    hedge_config=self.hedge_config)
            self.enforce_grid(new_orders=hedge_orders, exchange_orders=existing_orders, lowest_price_first=False)
            logger.info(f'{symbol} {position_side.name}: Finished placing hedge orders')
            return

        if self.price_outside_boundaries(symbol=symbol, position_side=position_side, current_price=current_price):
            open_orders = self.exchange_state.all_open_orders(symbol=symbol, position_side=position_side)
            self.order_executor.cancel_orders(open_orders)
            return

        if self.price_within_resistance_distance(symbol=symbol,
                                                 position_side=position_side,
                                                 current_price=current_price):
            open_orders = self.exchange_state.all_open_orders(symbol=symbol, position_side=position_side)
            self.order_executor.cancel_orders(open_orders)
            return

        if self.entry_order_type == 'LIMIT':
            existing_entry_orders = self.exchange_state.open_entry_orders(symbol=symbol, position_side=position_side)
            if len(existing_entry_orders) >= self.dca_config.expected_nr_orders:
                highest_entry_order = max(order.price for order in existing_entry_orders)

                support_records = self.dca_plugin.calculate_support_prices(symbol=symbol,
                                                                           position_side=position_side,
                                                                           maximum_price=current_price,
                                                                           dca_config=self.dca_config)
                if len(support_records) == 0:
                    logger.info(f'{symbol} {position_side.name}: There are no support records found, maintaining existing grid')
                    return
                highest_new_price = max(record.price for record in support_records)

                diff = calc_diff(highest_entry_order, highest_new_price)
                if diff > self.limit_orders_reissue_threshold:
                    if highest_new_price < highest_entry_order and self.repost_lower_allowed is False:
                        return
                    else:
                        user_log.info(f'{symbol} {position_side.name}: Calculating & issuing new entry grid as new price '
                                      f'{highest_new_price} is {readable_pct(diff, 4)} away from current first entry '
                                      f'{highest_entry_order}, with the threshold configured at '
                                      f'{readable_pct(self.limit_orders_reissue_threshold, 4)}',
                                      __name__)
                else:
                    logger.info(f'{symbol} {position_side.name}: Leaving LIMIT entry orders as new price '
                                f'{highest_new_price} is {readable_pct(diff, 4)} away from current first entry '
                                f'{highest_entry_order}, with the threshold configured at '
                                f'{readable_pct(self.limit_orders_reissue_threshold, 4)}, '
                                f'Highest entry order price = {highest_entry_order}, current price = {current_price}')
                    return

        self.gridstorage_plugin.reset(symbol=symbol, position_side=position_side)

        # calculate support prices linear
        logger.info('Starting placing initial orders')
        self.dca_plugin.initialize_unlimited_grid(symbol=symbol,
                                                  position_side=position_side,
                                                  symbol_information=symbol_information,
                                                  current_price=current_price,
                                                  dca_config=self.dca_config,
                                                  wallet_exposure=self.calc_wallet_exposure_ratio())
        all_prices = self.gridstorage_plugin.get_prices(symbol=symbol, position_side=position_side)
        allowed_prices = [price for price in all_prices if price < current_price]
        allowed_prices.sort(reverse=True)
        logger.info(f'{symbol} {position_side.name}: Selected price below current price {current_price}: '
                    f'{allowed_prices}')
        dca_quantities = self.gridstorage_plugin.get_quantities(symbol=symbol, position_side=position_side)

        wallet_exposure = self.calc_wallet_exposure_ratio()
        exposed_balance = wallet_balance * wallet_exposure

        price_index = 0
        limit_orders = []
        orders_cost = 0
        for i, dca_quantity_record in enumerate(dca_quantities):
            if i >= len(allowed_prices):
                # no more prices available, break it off
                break
            dca_price = allowed_prices[price_index]
            dca_quantity = dca_quantity_record.quantity
            min_entry_qty = calc_min_qty(price=dca_price,
                                         inverse=False,
                                         qty_step=symbol_information.quantity_step,
                                         min_qty=symbol_information.minimum_quantity,
                                         min_cost=symbol_information.minimal_buy_cost)
            if dca_quantity < min_entry_qty:
                if not self.override_insufficient_grid_funds:
                    raw_quantity = dca_quantity_record.raw_quantity
                    required_balance = exposed_balance * (min_entry_qty / raw_quantity)
                    logger.warning(f'{symbol} {position_side.name}: The entry at price {dca_price} with quantity '
                                   f'{dca_quantity} ({raw_quantity}) does not meet minimum quantity {min_entry_qty}. The quantities are '
                                   f'based on exposed balance {exposed_balance}. In order to make the bot enter, either '
                                   f'1) increase the exposed balance to (roughly) a minimum of {required_balance} by having a bigger wallet_exposure_ratio, or adding equity if '
                                   f'you want to maintain the same settings, 2) reduce the number of clusters, 3) reduce the DCA strength (ratio power, quantity multiplier or '
                                   f'desired position distance), 4) force the bot to run with an incomplete grid by setting \'override_insufficient_grid_funds\' to true')
                    return

            if self.entry_order_type == 'MARKET' and price_index == 0:
                order = MarketOrder(order_type_identifier=OrderTypeIdentifier.INITIAL_ENTRY,
                                    symbol=symbol,
                                    quantity=max(min_entry_qty, dca_quantity),
                                    side=Side.BUY,
                                    position_side=PositionSide.LONG,
                                    initial_entry=True,
                                    status=OrderStatus.NEW)
                price_index += 1
            else:
                order = LimitOrder(
                    order_type_identifier=OrderTypeIdentifier.INITIAL_ENTRY if price_index == 0 else OrderTypeIdentifier.DCA,
                    symbol=symbol_information.symbol,
                    quantity=dca_quantity,
                    side=Side.BUY,
                    position_side=PositionSide.LONG,
                    initial_entry=False,
                    price=dca_price)
                price_index += 1
            if orders_cost + order.cost > exposed_balance:
                break
            orders_cost += order.cost
            limit_orders.append(order)

        if len(limit_orders) == 0:
            return

        if self.stoploss_config.enabled is True and (
                self.stoploss_config.upnl_exposed_wallet_trigger_threshold is not None or self.stoploss_config.upnl_total_wallet_trigger_threshold is not None):
            first_trigger_price = self.stoploss_plugin._calculate_first_trigger_price_from_dca(position=position,
                                                                                               symbol_information=symbol_information,
                                                                                               current_price=current_price,
                                                                                               wallet_balance=wallet_balance,
                                                                                               exposed_wallet_balance=exposed_balance,
                                                                                               dca_orders=limit_orders,
                                                                                               stoploss_config=self.stoploss_config)
            last_dca_price = min([o.price for o in limit_orders])
            orders_str = [f'{o.quantity}@{o.price}' for o in limit_orders]
            maximum_allowed_loss = self.stoploss_plugin.determine_maximum_allowed_loss(wallet_balance=wallet_balance,
                                                                                       exposed_balance=exposed_balance,
                                                                                       stoploss_config=self.stoploss_config)
            if first_trigger_price is not None and first_trigger_price > last_dca_price:
                logger.warning(
                    f'{symbol} {position_side.name}: NOT PLACING INITIAL GRID because the stoploss price for '
                    f'maximum allowed loss of {maximum_allowed_loss} would be {first_trigger_price}, which is '
                    f'above the last DCA price of {last_dca_price} (orders: {orders_str}). There are a number of '
                    f'things you can do to make the configuration allow entry: 1) increase the allowed loss the '
                    f'stoploss can cause, 2) make the grid tighter so the stoploss is placed after the last DCA, '
                    f'3) disable the stoploss plugin')
                return
            else:
                logger.info(f'{symbol} {position_side.name}: PLACING INITIAL GRID because the stoploss price for '
                            f'maximum allowed loss of {maximum_allowed_loss} would be {first_trigger_price}, which is '
                            f'below the last DCA price of {last_dca_price} (orders: {orders_str})')

        if self.execute_orders_enabled is True:
            existing_orders = self.exchange_state.open_entry_orders(symbol=symbol, position_side=position_side)
            self.enforce_grid(new_orders=limit_orders, exchange_orders=existing_orders, lowest_price_first=False)
            logger.info(f'{symbol} {position_side.name}: Finished placing orders')
        elif len(limit_orders) > 0:
            logger.info(f'{symbol} {position_side.name}: Order execution is explicitly disabled in the config')

    def price_within_resistance_distance(self, symbol: str, position_side: PositionSide,
                                         current_price: float) -> bool:
        if self.no_entry_within_resistance_distance is None:
            return False

        algo = self.no_entry_within_resistance_algo
        original_start_date = self.time_provider.get_utc_now_timestamp() - period_as_ms(
            self.no_entry_within_resistance_period)
        start_date = algo.get_candles_start_date(symbol=symbol,
                                                 timeframe=self.no_entry_within_resistance_timeframe,
                                                 start_date=original_start_date,
                                                 outer_grid_price=None)
        if start_date is None:
            candles = []
        else:
            candles = self.candlestore_client.get_candles_in_range(symbol=symbol,
                                                                   timeframe=self.no_entry_within_resistance_timeframe,
                                                                   start_date=start_date,
                                                                   end_date=self.time_provider.get_utc_now_timestamp())
        support_resistances = algo.calculate_levels(symbol=symbol,
                                                    position_side=PositionSide.SHORT,
                                                    candles=candles,
                                                    nr_clusters=self.no_entry_within_resistance_nr_clusters,
                                                    current_price=current_price,
                                                    outer_price=None,
                                                    original_start_date=original_start_date,
                                                    symbol_information=self.exchange_state.get_symbol_information(symbol))
        if len(support_resistances.resistances) == 0:
            logger.info(f'{symbol} {position_side.name}: ALLOWING INITIAL ENTRY for current price {current_price} '
                        f'because there is no resistance detected based on period '
                        f'{self.no_entry_within_resistance_period} on timeframe '
                        f'{self.no_entry_within_resistance_timeframe}')
            return False

        closest_resistance = min(support_resistances.resistances)

        resistance_distance = calc_diff(closest_resistance, current_price)
        if resistance_distance < self.no_entry_within_resistance_distance:
            logger.info(f'{symbol} {position_side.name}: BLOCKING INITIAL ENTRY because current price {current_price} '
                        f'is {readable_pct(resistance_distance, 2)} from closest resistance {closest_resistance}, '
                        f'which is less than the specified no_entry_within_resistance_distance '
                        f'{readable_pct(self.no_entry_within_resistance_distance, 2)}')
            return True
        else:
            logger.info(f'{symbol} {position_side.name}: ALLOWING INITIAL ENTRY because current price {current_price} '
                        f'is {readable_pct(resistance_distance, 2)} from closest resistance {closest_resistance}, '
                        f'which is more than the specified no_entry_within_resistance_distance '
                        f'{readable_pct(self.no_entry_within_resistance_distance, 2)}')
            return False
        
    # retrieve the filtered data from redis with prefix for the symbol
    def get_filter_result_for_symbol(self, symbol: str) -> dict:
        redis_prefix = 'DynamicPriceChangePctFilter'
        filter_result = self.redis.hgetall(f'{redis_prefix}_filtered_symbol_{symbol}')
        if filter_result:
            filter_result['short'] = filter_result.get('short', '0') == '1'  # '1' is True, '0' is False
            filter_result['long'] = filter_result.get('long', '0') == '1'  # '1' is True, '0' is False
        return filter_result
    
    def get_utc_close_price(self, symbol: str, equilibrium_timeframe: Timeframe = Timeframe.ONE_HOUR, equilibrium_hour: int = 16):
        # Fetch the last 48 1-hour candles
        candles = self.candlestore_client.get_last_candles(symbol=symbol, timeframe=equilibrium_timeframe, amount=48)
        
        # Log each candle's start_datetime for debugging
        for idx, candle in enumerate(candles):
            logger.info(f"Candle {idx}: start_datetime={candle.start_datetime}, raw data={candle}")
        
        # Filter candles for the specified start hour (equilibrium_hour) in UTC
        filtered_candles = sorted(
            [
                c for c in candles
                if c.start_datetime.hour == equilibrium_hour
            ],
            key=lambda c: c.start_date
        )
        
        # Return the close price of the first matching candle, or None if no matches
        return filtered_candles[0].close if filtered_candles else None

