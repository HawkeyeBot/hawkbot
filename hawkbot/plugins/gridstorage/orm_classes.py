from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base

_GRID_DECL_BASE = declarative_base()


class QuantityGrid(_GRID_DECL_BASE):
    __tablename__ = 'QUANTITY_GRID'
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    position_side = Column(String)
    quantity = Column(Float)
    accumulated_quantity = Column(Float)
    raw_quantity = Column(Float)


class PriceGrid(_GRID_DECL_BASE):
    __tablename__ = 'PRICE_GRID'
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    position_side = Column(String)
    price = Column(Float)


class RootPrice(_GRID_DECL_BASE):
    __tablename__ = 'ROOT_PRICE'
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    position_side = Column(String)
    price = Column(Float)
