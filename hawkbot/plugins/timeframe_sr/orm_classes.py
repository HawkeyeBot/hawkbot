from sqlalchemy import Column, Integer, String, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

_LEVEL_DECL_BASE = declarative_base()


class Cache(_LEVEL_DECL_BASE):
    __tablename__ = 'CACHE'
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    timeframe = Column(String)
    last_candle_close = Column(Integer)
    supports = relationship("Support")
    resistances = relationship("Resistance")


class Support(_LEVEL_DECL_BASE):
    __tablename__ = 'SUPPORT'
    id = Column(Integer, primary_key=True)
    cache_id = Column(Integer, ForeignKey('CACHE.id'))
    symbol = Column(String)
    timeframe = Column(String)
    price = Column(Float)
    type = Column(String)


class Resistance(_LEVEL_DECL_BASE):
    __tablename__ = 'RESISTANCE'
    id = Column(Integer, primary_key=True)
    cache_id = Column(Integer, ForeignKey('CACHE.id'))
    symbol = Column(String)
    timeframe = Column(String)
    price = Column(Float)
    type = Column(String)