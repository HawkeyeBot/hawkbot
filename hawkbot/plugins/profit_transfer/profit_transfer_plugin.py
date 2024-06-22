import logging
import os
import threading
from typing import Optional, List, Dict

from sqlalchemy import create_engine, MetaData, desc

from hawkbot.core.data_classes import ExchangeState
from hawkbot.core.lockable_session import LockableSession
from hawkbot.core.model import BotStatus, Income, Timeframe
from hawkbot.core.time_provider import TimeProvider
from hawkbot.exceptions import InvalidConfigurationException
from hawkbot.exchange.data_classes import TransferType
from hawkbot.exchange.exchange import Exchange
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.plugins.profit_transfer.orm_classes import _PROFIT_TRANSFER_DECL_BASE, IncomeEntity
from hawkbot.utils import readable_pct, readable, fill_required_parameters, period_as_ms, period_as_s, round_dn, fill_optional_parameters

logger = logging.getLogger(__name__)

"""
    Example config transferring 50% of realized PNL every once a minute:

    "plugins": {
        "ProfitTransferPlugin": {
            # "profit_transfer_share": 0.5,
            # "transfer_all_above": 100,
            "profit_transfer_share_thresholds": {
                "0": 0.1,
                "200": 0.3,
                "500": 0.5,
                "1000": 0.8
            }
            "transfer_interval": "1m",
            "initial_lookback_period": "5m",
            "transfer_type": "USDT_FUTURES_TO_SPOT"
        }
    },
"""


class ProfitTransferPlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.exchange: Exchange = None  # Injected by plugin loader
        self.exchange_state: ExchangeState = None  # Injected by plugin loader
        self.time_provider: TimeProvider = None  # Injected by plugin loader
        self.status: BotStatus = BotStatus.NEW
        self.trigger_event: threading.Event = threading.Event()

        if 'database_path' in plugin_config:
            database_path = plugin_config['database_path']
        else:
            database_path = 'data/profit_transfer_plugin.db'

        os.makedirs(os.path.dirname(database_path), exist_ok=True)
        self.engine = create_engine(url=f'sqlite:///{database_path}',
                                    echo=False,
                                    connect_args={"check_same_thread": False})
        self.metadata = MetaData(bind=self.engine)
        _PROFIT_TRANSFER_DECL_BASE.metadata.create_all(self.engine)
        self.lockable_session = LockableSession(self.engine)

        self.enabled: bool = True
        self.profit_transfer_share: float = None
        self.profit_transfer_share_thresholds: Dict[float, float] = None
        self.transfer_interval: int = None
        self.transfer_all_above: float = None

        if 'enabled' in plugin_config:
            self.enabled = plugin_config['enabled']

        optional_parameters = ['profit_transfer_share',
                               'transfer_all_above']
        fill_optional_parameters(target=self, config=plugin_config, optional_parameters=optional_parameters)

        self.transfer_interval = period_as_s(plugin_config['transfer_interval'])
        self.initial_lookback_period = period_as_ms(plugin_config['initial_lookback_period'])

        if self.initial_lookback_period > period_as_ms('7D'):
            raise InvalidConfigurationException('The parameter \'initial_lookbacck_period\' can not be greater than 7 days')

        if 'transfer_type' in plugin_config:
            self.transfer_type = TransferType(plugin_config['transfer_type'])
        else:
            raise InvalidConfigurationException('The parameter \'transfer_type\' is required, supporting one of the '
                                                'following options: [SPOT_TO_USDT_FUTURES, USDT_FUTURES_TO_SPOT, '
                                                'SPOT_TO_COINM_FUTURES,COINM_FUTURES_TO_SPOT]')

        if 'profit_transfer_share_thresholds' in plugin_config:
            self.profit_transfer_share_thresholds = {}
            for threshold, share in plugin_config['profit_transfer_share_thresholds'].items():
                self.profit_transfer_share_thresholds[float(threshold)] = share

        if self.profit_transfer_share is None and self.profit_transfer_share_thresholds is None and self.transfer_all_above is None:
            raise InvalidConfigurationException('One of the parameters \'profit_transfer_share\' or \'profit_transfer_share_thresholds\' or \'transfer_all_above\' is required')
        if self.profit_transfer_share_thresholds is not None and self.profit_transfer_share_thresholds is not None:
            raise InvalidConfigurationException('The parameters \'profit_transfer_share\' and \'profit_transfer_share_thresholds\' are mutually exclusive, please remove one of '
                                                'the two')

    def start(self):
        self.status = BotStatus.STARTING
        transfer_thread = threading.Thread(name=f'profit_transfer_plugin',
                                           target=self.process_scheduled_transfers,
                                           daemon=True)
        transfer_thread.start()

    def process_scheduled_transfers(self):
        self.status = BotStatus.RUNNING
        self.trigger_event.wait(self.transfer_interval)
        while self.status == BotStatus.RUNNING:
            if self.enabled is True:
                try:
                    self.transfer_superfluous_balance()
                    self.execute_profit_transfer()
                except:
                    logger.exception('Failed to execute transfers')

            self.trigger_event.wait(self.transfer_interval)
        self.status = BotStatus.RUNNING

    def transfer_superfluous_balance(self):
        if self.transfer_all_above is not None:
            asset = 'USDT'
            current_balance = self.exchange_state.asset_balance(asset)
            if current_balance > self.transfer_all_above:
                funds_to_transfer = current_balance - self.transfer_all_above
                rounded_funds_to_transfer = round_dn(number=funds_to_transfer, step=0.01)
                if rounded_funds_to_transfer > 0:
                    logger.info(f'Transferring funds {rounded_funds_to_transfer} {asset} based on current balance {current_balance} and setting to tranfser everything above '
                                f'{self.transfer_all_above}')
                    self.exchange.transfer(transfer_type=self.transfer_type, asset=asset, amount=rounded_funds_to_transfer)
                    logger.info('Transfer completed')

    def execute_profit_transfer(self):
        if self.profit_transfer_share is not None or self.profit_transfer_share_thresholds is not None:
            now = self.time_provider.get_utc_now_timestamp()
            last_income = self.get_last_stored_income()
            if last_income is None:
                last_start_income = now - self.initial_lookback_period
                logger.info(f'Last stored income is None, last_start_income is set to {readable(last_start_income)}')
            else:
                last_start_income = last_income.timestamp + Timeframe.ONE_SECOND.milliseconds
                logger.info(f'Last stored income is {readable(last_income.timestamp)}, setting last_start_income to {readable(last_start_income)}')

            last_start_income = max(last_start_income, now - period_as_ms('7D'))
            logger.info(f'Fetching income from {readable(last_start_income)} until {readable(now)} (last income = {readable(last_income.timestamp)}')
            new_incomes = self.exchange.fetch_incomes(start_time=last_start_income + 1, end_time=now)
            if len(new_incomes) > 0:
                unique_assets = set([income.asset for income in new_incomes])
                for asset in unique_assets:
                    total_new_profit = sum([income.income for income in new_incomes if income.asset == asset])
                    share_to_transfer = self._determine_share_to_transfer(total_new_profit)
                    if share_to_transfer > 0:
                        logger.info(f'Transferring realized PNL {share_to_transfer} {asset} '
                                    f'({readable_pct(self.profit_transfer_share, 3)}) of total profit '
                                    f'{total_new_profit} realized between [{readable(last_start_income)} - '
                                    f'{readable(now)}]')
                        self.exchange.transfer(transfer_type=self.transfer_type, asset=asset, amount=share_to_transfer)
                        logger.info('Transfer completed')
                        self.persist_transferred_incomes(new_incomes)
                    else:
                        logger.info(f'Not transferring realized PNL {share_to_transfer} {asset} '
                                    f'({readable_pct(self.profit_transfer_share, 3)}) of total profit '
                                    f'{total_new_profit} realized between [{readable(last_start_income)} - '
                                    f'{readable(now)}] because rounded down to 0.01 precision it is 0')
            else:
                logger.info(f'No new incomes to transfer profits for since {readable(last_start_income)}')

    def _determine_share_to_transfer(self, total_new_profit: float):
        if self.profit_transfer_share is not None:
            return round_dn(number=total_new_profit * self.profit_transfer_share, step=0.01)
        if self.profit_transfer_share_thresholds is not None:
            if len(self.profit_transfer_share_thresholds) == 0:
                return 0

            wallet_balance = self.exchange_state.asset_balance('USDT')
            thresholds_below_wallet_balance = [key for key in self.profit_transfer_share_thresholds if key < wallet_balance]
            if len(thresholds_below_wallet_balance) == 0:
                logger.info(f'No threshold found below wallet balance {wallet_balance}, not transferring any profit')
                return 0

            nearest_applicable_threshold = max(thresholds_below_wallet_balance)
            profit_share = self.profit_transfer_share_thresholds[nearest_applicable_threshold]
            return round_dn(number=total_new_profit * profit_share, step=0.01)

    def get_last_stored_income(self) -> Optional[Income]:
        with self.lockable_session as session:
            income_entity: IncomeEntity = session.query(IncomeEntity).order_by(desc(IncomeEntity.timestamp)).first()
            if income_entity is None:
                return None
            else:
                return Income(symbol=income_entity.symbol,
                              asset=income_entity.asset,
                              income=income_entity.pnl,
                              timestamp=income_entity.timestamp)

    def persist_transferred_incomes(self, incomes: List[Income]):
        logger.debug(f'Persisting incomes {incomes}')
        with self.lockable_session as session:
            for income in incomes:
                session.add(IncomeEntity(symbol=income.symbol,
                                         asset=income.asset,
                                         pnl=f'{income.income}',
                                         timestamp=income.timestamp))
            session.commit()
        logger.debug('Finished persisting incomes')

    def stop(self):
        self.status = BotStatus.STOPPING
        self.trigger_event.set()
