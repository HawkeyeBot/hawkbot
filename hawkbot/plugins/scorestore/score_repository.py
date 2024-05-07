import logging
import os
from typing import List, Dict

from sqlalchemy import create_engine, MetaData, Table, and_
from sqlalchemy.dialects.sqlite import insert

from hawkbot.core.lockable_session import LockableSession
from hawkbot.core.time_provider import now
from hawkbot.utils import readable
from .data_classes import ScorePower
from .orm_classes import get_score_table_identifier, create_score_table

logger = logging.getLogger(__name__)


class ScoreRepository:
    def __init__(self, database_path: str):
        super().__init__()
        os.makedirs(os.path.dirname(database_path), exist_ok=True)
        self.engine = create_engine(url=f'sqlite:///{database_path}',
                                    echo=False,
                                    connect_args={"check_same_thread": False})
        self.metadata = MetaData(bind=self.engine)
        self.metadata.reflect(bind=self.engine)

        self.score_tables = {}
        for name in self.metadata.tables:
            if name.startswith('score_'):
                self.score_tables[name] = self.metadata.tables[name]
        self.lockable_session = LockableSession(self.engine)

    def get_score_table(self, symbol: str) -> Table:
        identifier = get_score_table_identifier(symbol=symbol)
        try:
            return self.score_tables[identifier]
        except KeyError:
            with self.lockable_session:
                table = create_score_table(symbol=symbol,
                                           metadata=self.metadata)
                self.metadata.create_all(tables=[table])
                self.score_tables[identifier] = table
                return table

    def store_scores(self, events: List[Dict]):
        symbols = set([e['symbol'] for e in events])
        tables = {symbol: self.get_score_table(symbol=symbol) for symbol in symbols}
        with self.lockable_session:
            for symbol in symbols:
                data = [{
                    "registration_datetime": now(),
                    "exchange": e['exchange'],
                    "symbol": symbol,
                    "timestamp": e['timestamp'],
                    "price": e['price'],
                    "score": e['score'],
                    "power": e['power'],
                    "nr_bins": e['nr_bins'],
                    "depth": e['depth']
                } for e in events if e['symbol'] == symbol]

                statement = insert(tables[symbol]).on_conflict_do_nothing()
                self.engine.execute(statement, data)

    def get_scores(self,
                   exchange: str,
                   symbol: str,
                   from_timestamp: int,
                   end_timestamp: int,
                   nr_bins: int,
                   depth: int) -> List[ScorePower]:
        table_name = self.get_score_table(symbol=symbol).name
        scores = []
        with self.engine.connect() as con:
            query = f"""
             select timestamp,
                    price,
                    score,
                    power,
                    nr_bins,
                    depth
               from {table_name}
              where exchange='{exchange}'
                and timestamp >= {from_timestamp}
                and timestamp <= {end_timestamp}
                and nr_bins = {nr_bins}
                and depth = {depth}
                order by timestamp
            """

            rs = con.execute(query)
            rows = rs.fetchall()
            for row in rows:
                scores.append(ScorePower(timestamp=row.timestamp,
                                         price=row.price,
                                         score=row.score,
                                         power=row.power,
                                         nr_bins=row.nr_bins,
                                         depth=row.depth))
        return scores

    def get_last_scores(self,
                        exchange: str,
                        symbol: str,
                        count: int,
                        nr_bins: int,
                        depth: int) -> List[ScorePower]:
        table_name = self.get_score_table(symbol=symbol).name
        scores = []
        with self.engine.connect() as con:
            query = f"""
             select timestamp,
                    price,
                    score,
                    power,
                    nr_bins,
                    depth
               from {table_name}
              where exchange='{exchange}'
                and nr_bins = {nr_bins}
                and depth = {depth}
                order by timestamp
                limit {count}
            """

            rs = con.execute(query)
            rows = rs.fetchall()
            for row in rows:
                scores.append(ScorePower(timestamp=row.timestamp,
                                         price=row.price,
                                         score=row.score,
                                         power=row.power,
                                         nr_bins=row.nr_bins,
                                         depth=row.depth))
        return scores

    def delete_scores(self, exchange: str, symbol: str, to_timestamp: int):
        logger.debug(f'{symbol}: Removing all scores with a timestamp at or before {readable(to_timestamp)}')
        table = self.get_score_table(symbol=symbol)
        with self.lockable_session as session:
            query = session.query(table).filter(
                and_(
                    table.columns.exchange == exchange,
                    table.columns.symbol == symbol,
                    table.columns.timestamp <= to_timestamp
                )
            )
            count = query.delete(synchronize_session=False)
            session.commit()
            if count > 0:
                logger.debug(f'{symbol}: Removed {count} scores with a timestamp at or before '
                             f'{readable(to_timestamp)}')
