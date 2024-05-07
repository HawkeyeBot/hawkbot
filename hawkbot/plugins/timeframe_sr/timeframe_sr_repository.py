import logging
import os
from typing import Dict

from sqlalchemy import create_engine, MetaData
from sqlalchemy.exc import NoResultFound

from hawkbot.core.data_classes import Timeframe
from hawkbot.core.lockable_session import LockableSession
from hawkbot.plugins.timeframe_sr.data_classes import TimeframeCache, LevelType, SupportResistance
from hawkbot.plugins.timeframe_sr.orm_classes import Cache, Support, Resistance, _LEVEL_DECL_BASE

logger = logging.getLogger(__name__)


class TimeframeSupportResistanceRepository:
    def __init__(self, plugin_config: Dict):
        if 'database_path' in plugin_config:
            database_path = plugin_config['database_path']
        else:
            database_path = 'data/supportresistance_plugin.db'

        os.makedirs(os.path.dirname(database_path), exist_ok=True)
        self.engine = create_engine(url=f'sqlite:///{database_path}',
                                    echo=False,
                                    connect_args={"check_same_thread": False})
        self.metadata = MetaData(bind=self.engine)
        _LEVEL_DECL_BASE.metadata.create_all(self.engine)
        self.lockable_session = LockableSession(self.engine)

    def get_from_cache(self,
                       symbol: str,
                       timeframe: Timeframe) -> TimeframeCache:
        with self.lockable_session as session:
            try:
                cache = session.query(Cache)\
                    .filter(Cache.symbol == symbol)\
                    .filter(Cache.timeframe == timeframe.name).one()
            except NoResultFound:
                cache = Cache(symbol=symbol,
                              timeframe=timeframe,
                              last_candle_close=0,
                              supports=[],
                              resistances=[])
                session.add(cache)
                session.commit()
                logger.warning(f'{symbol} {timeframe.name}: Found multiple caches in database. This indicates a '
                               f'race condition happened that inserted multiple caches for the same symbol. Removing '
                               f'the entries so the next iteration can reset the database correctly.')
                self.remove_from_cache(symbol=symbol, timeframe=timeframe)
                cache = Cache(symbol=symbol,
                              timeframe=timeframe.name,
                              last_candle_close=0,
                              supports=[],
                              resistances=[])
                session.add(cache)
                session.commit()

            support_resistance = SupportResistance()
            for support in cache.supports:
                price = float(support.price)
                support_resistance.supports[price] = LevelType[support.type]
            for resistance in cache.resistances:
                price = float(resistance.price)
                support_resistance.resistances[price] = LevelType[resistance.type]
            timeframe_cache = TimeframeCache(symbol=symbol,
                                             timeframe=timeframe,
                                             last_candle_close_date=cache.last_candle_close,
                                             support_resistance=support_resistance)
            return timeframe_cache

    def cache_valid_until(self, symbol: str, timeframe: Timeframe) -> int:
        with self.lockable_session as session:
            try:
                cache = session \
                    .query(Cache) \
                    .filter(Cache.symbol == symbol) \
                    .filter(Cache.timeframe == timeframe.name) \
                    .one()
            except NoResultFound:
                cache = Cache(symbol=symbol,
                              timeframe=timeframe.name,
                              last_candle_close=0,
                              supports=[],
                              resistances=[])
                session.add(cache)
                session.commit()

            return cache.last_candle_close

    def remove_from_cache(self,
                          symbol: str,
                          timeframe: Timeframe):
        with self.lockable_session as session:
            query = session.query(Cache) \
                .filter(Cache.symbol == symbol) \
                .filter(Cache.timeframe == timeframe.name)
            query.delete(synchronize_session=False)
            session.commit()

    def set_in_cache(self,
                     symbol: str,
                     timeframe: Timeframe,
                     last_candle_close: int,
                     support_resistance: SupportResistance):
        self.remove_from_cache(symbol=symbol, timeframe=timeframe)
        with self.lockable_session as session:
            orm_supports = []
            for price, level_type in support_resistance.supports.items():
                orm_supports.append(Support(symbol=symbol,
                                            timeframe=timeframe.name,
                                            price=str(price),
                                            type=level_type.name))

            orm_resistances = []
            for price, level_type in support_resistance.resistances.items():
                orm_resistances.append(Resistance(symbol=symbol,
                                                  timeframe=timeframe.name,
                                                  price=str(price),
                                                  type=level_type.name))

            cache = Cache(symbol=symbol,
                          timeframe=timeframe.name,
                          last_candle_close=last_candle_close,
                          supports=orm_supports,
                          resistances=orm_resistances)
            session.add(cache)
            session.commit()