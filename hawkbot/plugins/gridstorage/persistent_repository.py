import logging
import os
from typing import List

from sqlalchemy import create_engine, MetaData
from sqlalchemy.exc import NoResultFound

from hawkbot.core.lockable_session import LockableSession
from hawkbot.core.model import PositionSide
from hawkbot.plugins.gridstorage.data_classes import QuantityRecord, PriceRecord
from hawkbot.plugins.gridstorage.orm_classes import QuantityGrid, PriceGrid, RootPrice, _GRID_DECL_BASE

logger = logging.getLogger(__name__)


class PersistentRepository:
    def __init__(self, database_path: str):
        os.makedirs(os.path.dirname(database_path), exist_ok=True)
        self.engine = create_engine(url=f'sqlite:///{database_path}',
                                    echo=False,
                                    connect_args={"check_same_thread": False})
        self.metadata = MetaData(bind=self.engine)
        _GRID_DECL_BASE.metadata.create_all(self.engine, checkfirst=True)
        self.lockable_session = LockableSession(self.engine)

    def store_quantities(self, symbol: str, quantities: List[QuantityRecord]):
        logger.debug(f'Adding quantities list for symbol {symbol}')
        with self.lockable_session as session:
            for record in quantities:
                quantity_record = QuantityGrid(symbol=symbol,
                                               position_side=record.position_side.name,
                                               quantity=record.quantity,
                                               accumulated_quantity=record.accumulated_quantity,
                                               raw_quantity=record.raw_quantity)
                session.add(quantity_record)
            session.commit()
        logger.debug(f'Stored quantity grid {symbol}')

    def get_quantities(self, symbol: str, position_side: PositionSide) -> List[QuantityRecord]:
        quantities_grid: List[QuantityRecord] = []
        with self.lockable_session as session:
            for record in session.query(QuantityGrid) \
                    .filter(QuantityGrid.symbol == symbol) \
                    .filter(QuantityGrid.position_side == position_side.name) \
                    .order_by(QuantityGrid.quantity):
                quantities_grid.append(QuantityRecord(position_side=PositionSide[record.position_side],
                                                      quantity=record.quantity,
                                                      accumulated_quantity=record.accumulated_quantity,
                                                      raw_quantity=record.raw_quantity))
        quantities_grid.sort(key=lambda x: x.quantity)
        return quantities_grid

    def store_prices(self, symbol: str, prices_records: List[PriceRecord]):
        logger.debug(f'Adding prices list for symbol {symbol}')
        with self.lockable_session as session:
            for record in prices_records:
                price_record = PriceGrid(symbol=symbol,
                                         position_side=record.position_side.name,
                                         price=record.price)
                session.add(price_record)
            session.commit()
        logger.debug(f'Stored price grid {symbol}')

    def get_prices(self, symbol: str, position_side: PositionSide) -> List[float]:
        prices_grid = []
        with self.lockable_session as session:
            for entry in session \
                    .query(PriceGrid) \
                    .filter(PriceGrid.symbol == symbol) \
                    .filter(PriceGrid.position_side == position_side.name) \
                    .order_by(PriceGrid.price):
                prices_grid.append(entry.price)
        return prices_grid

    def get_root_price(self, symbol: str, position_side: PositionSide) -> float:
        with self.lockable_session as session:
            try:
                root_price = session \
                    .query(RootPrice) \
                    .filter(RootPrice.symbol == symbol) \
                    .filter(RootPrice.position_side == position_side.name) \
                    .one()
                return root_price.price
            except NoResultFound:
                return None

    def store_root_price(self, symbol: str, position_side: PositionSide, price: float):
        logger.debug(f'Adding root price for symbol {symbol} {position_side.name}: {price}')
        with self.lockable_session as session:
            root_price = RootPrice(symbol=symbol,
                                   position_side=position_side.name,
                                   price=price)
            session.add(root_price)
            session.commit()
        logger.debug(f'Stored root price {symbol} {position_side.name}: {price}')

    def reset(self, symbol: str, position_side: PositionSide):
        logger.debug(f'Resetting price & quantities for symbol {symbol} for {position_side.name}')
        self.reset_quantities(symbol=symbol, position_side=position_side)
        self.reset_prices(symbol=symbol, position_side=position_side)
        self.reset_root_price(symbol=symbol, position_side=position_side)

    def reset_root_price(self, symbol: str, position_side: PositionSide):
        logger.debug(f'Resetting root price for symbol {symbol} for {position_side.name}')
        with self.lockable_session as session:
            root_price_query = session.query(RootPrice) \
                .filter(RootPrice.symbol == symbol) \
                .filter(RootPrice.position_side == position_side.name)
            root_price_query.delete(synchronize_session=False)
            session.commit()
        logger.debug(f'Reset root price for {symbol} for {position_side.name}')

    def reset_prices(self, symbol: str, position_side: PositionSide):
        logger.debug(f'Resetting prices for symbol {symbol} for {position_side.name}')
        with self.lockable_session as session:
            count = session.query(PriceGrid) \
                .filter(PriceGrid.symbol == symbol) \
                .filter(PriceGrid.position_side == position_side.name) \
                .delete(synchronize_session=False)
            session.commit()
            logger.debug(f'Reset price grid for {symbol} for {position_side.name}: {count} records deleted')

    def reset_quantities(self, symbol: str, position_side: PositionSide):
        logger.debug(f'Resetting quantities for symbol {symbol} for {position_side.name}')
        with self.lockable_session as session:
            quantity_query = session.query(QuantityGrid) \
                .filter(QuantityGrid.symbol == symbol) \
                .filter(QuantityGrid.position_side == position_side.name)
            quantity_query.delete(synchronize_session=False)
            session.commit()
        logger.debug(f'Reset quantity grid for {symbol} for {position_side.name}')
