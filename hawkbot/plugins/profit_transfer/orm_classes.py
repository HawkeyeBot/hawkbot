from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base

_PROFIT_TRANSFER_DECL_BASE = declarative_base()


class IncomeEntity(_PROFIT_TRANSFER_DECL_BASE):
    __tablename__ = 'Income'
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    asset = Column(String)
    pnl = Column(Float)
    timestamp = Column(Integer)
