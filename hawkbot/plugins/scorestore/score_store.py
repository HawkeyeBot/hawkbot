import logging
import os
import threading
from queue import Empty, Queue
from typing import List, Dict

import pandas as pd
import pyarrow
from pandas import DataFrame, concat
from pyarrow import parquet

from hawkbot.core.model import BotStatus
from hawkbot.core.time_provider import TimeProvider
from hawkbot.core.plugins.plugin import Plugin
from hawkbot.plugins.scorestore.data_classes import ScorePower
from hawkbot.plugins.scorestore.score_repository import ScoreRepository
from hawkbot.utils import readable

logger = logging.getLogger(__name__)


class ScoreStorePlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        self.time_provider: TimeProvider = None  # Injected by plugin loader
        database_path = 'data/score_cache.db'
        if 'database_path' in plugin_config:
            database_path = plugin_config['database_path']
        self.repository = ScoreRepository(database_path)
        self.persist_thread = threading.Thread(name='bot_scorestore_persist', target=self.persist_scores, daemon=True)
        self.persist_queue: Queue = Queue()
        self.status: BotStatus = BotStatus.NEW

        self.cache: Dict[str, List[ScorePower]] = {}
        self.cache_period: Dict[str, int] = {}
        self.cache_update_lock: threading.RLock = threading.RLock()
        self.cache_initialized: Dict[str, bool] = {}

        self.persist_to_file: bool = False
        self.persist_file_path: str = os.path.join('backtests', 'data', 'binance')
        if 'persist_file_path' in plugin_config:
            self.persist_file_path = plugin_config['persist_file_path']
        if 'persist_to_file' in plugin_config:
            self.persist_to_file = plugin_config['persist_to_file']
            logger.info(f'Enabled persisting scorepower to {self.persist_file_path}')
        self.scorepower_length_threshold = 10_000
        self.scorepower_df: Dict[str, DataFrame] = {}

    def start(self):
        if self.started is False:
            super().start()
            self.status = BotStatus.STARTING
            self.persist_thread.start()

    def stop(self):
        super().stop()

        for symbol, df in self.scorepower_df.items():
            try:
                self.save_swingpower_dataframe(symbol=symbol, df=df)
            except:
                logger.info(f'{symbol}: Failed to store scorepower dataframe on shutdown')

        self.persist_queue.put(BotStatus.STOPPING)

    def persist_scores(self):
        self.status = BotStatus.RUNNING
        while self.status == BotStatus.RUNNING:
            event = self.persist_queue.get(block=True)
            if event == BotStatus.STOPPING:
                break
            events = [event]
            try:
                events.append(self.persist_queue.get_nowait())
            except Empty:
                pass

            self.repository.store_scores(events)
            if self.persist_to_file is True:
                for e in events:
                    self.scorepower_df.setdefault(e['symbol'], DataFrame(columns=['exchange',
                                                                                  'symbol',
                                                                                  'price',
                                                                                  'score',
                                                                                  'power',
                                                                                  'nr_bins', 'depth']))
                    new_row = pd.DataFrame(data=e,
                                           index=[e['timestamp']])
                    new_df = concat([self.scorepower_df[e['symbol']], new_row])
                    if len(new_df.index) >= self.scorepower_length_threshold:
                        self.scorepower_df[e['symbol']] = DataFrame(columns=['exchange',
                                                                             'symbol',
                                                                             'price',
                                                                             'score',
                                                                             'power',
                                                                             'nr_bins',
                                                                             'depth'])
                        self.save_swingpower_dataframe(symbol=e['symbol'], df=new_df)
                    else:
                        self.scorepower_df[e['symbol']] = new_df

        logger.info(f'Stopped score persisting thread')
        self.status = BotStatus.STOPPED

    def save_swingpower_dataframe(self, symbol: str, df: DataFrame):
        table = pyarrow.Table.from_pandas(df)
        target_folder = os.path.join(self.persist_file_path, symbol, 'swingpower')
        parquet.write_to_dataset(table, target_folder)
        logger.info(f'Saved swingpower dataframe after {len(df.index)} entries to dataset'
                    f' {target_folder}')

    def store_score(self,
                    exchange: str,
                    symbol: str,
                    timestamp: int,
                    price: float,
                    score: float,
                    power: float,
                    nr_bins: int,
                    depth: int):
        self.persist_queue.put({'exchange': exchange,
                                'symbol': symbol,
                                'price': price,
                                'timestamp': timestamp,
                                'score': score,
                                'power': power,
                                'nr_bins': nr_bins,
                                'depth': depth})

        with self.cache_update_lock:
            self.cache.setdefault(symbol, [])
            if self.cache_initialized.setdefault(symbol, False) is False:
                return

            self.cache[symbol].append(ScorePower(timestamp=timestamp,
                                                 price=price,
                                                 score=score,
                                                 power=power,
                                                 nr_bins=nr_bins,
                                                 depth=depth))

            try:
                remove_cache_before = self.time_provider.get_utc_now_timestamp() - self.cache_period[symbol]
                for i, score in enumerate(self.cache[symbol]):
                    if score.timestamp >= remove_cache_before:
                        break
                self.cache[symbol] = self.cache[symbol][i:]
            except KeyError:
                logger.warning(f'{symbol}: No cache period detected (yet), so the cache is not purged of old entries. '
                               f'This can happen during startup, and is expected to correct automatically. If this '
                               f'happens (frequently) after startup please reach out.')

    def get_scores(self,
                   exchange: str,
                   symbol: str,
                   from_timestamp: int,
                   nr_bins: int,
                   depth: int,
                   count: int = None) -> List[ScorePower]:
        now = self.time_provider.get_utc_now_timestamp()
        self.cache_period.setdefault(symbol, 0)
        self.cache_period[symbol] = max(self.cache_period[symbol], now - from_timestamp)

        self.cache.setdefault(symbol, [])
        self.cache_initialized.setdefault(symbol, False)

        if self.cache_initialized[symbol] is False:
            with self.cache_update_lock:
                scores = self.repository.get_scores(exchange=exchange,
                                                    symbol=symbol,
                                                    from_timestamp=from_timestamp,
                                                    end_timestamp=now,
                                                    nr_bins=nr_bins,
                                                    depth=depth)
                self.cache[symbol] = scores
                logger.info(f'{symbol}: Initialized scores cache')
                self.cache_initialized[symbol] = True
        if count is None:
            return self.cache[symbol]
        else:
            return self.cache[symbol][-count:]

    def get_last_score_powers(self, exchange, symbol, count, nr_bins, depth) -> List[ScorePower]:
        now = self.time_provider.get_utc_now_timestamp()
        self.cache_period.setdefault(symbol, 0)
        self.cache_period[symbol] = max(self.cache_period[symbol], now - (count * 2000))

        self.cache.setdefault(symbol, [])
        self.cache_initialized.setdefault(symbol, False)

        if self.cache_initialized[symbol] is False:
            with self.cache_update_lock:
                scores = self.repository.get_last_scores(exchange=exchange,
                                                         symbol=symbol,
                                                         count=count,
                                                         nr_bins=nr_bins,
                                                         depth=depth)
                self.cache[symbol] = scores
                logger.info(f'{symbol}: Initialized scores cache with {len(scores)} entries')
                self.cache_initialized[symbol] = True
        return self.cache[symbol][-count:]
