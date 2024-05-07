from sqlalchemy import MetaData, Table, Column, Integer, DateTime, func, String, Float, Index


def create_score_table(symbol: str, metadata: MetaData):
    identifier = get_score_table_identifier(symbol)
    return Table(identifier,
                 metadata,
                 Column('id', Integer, primary_key=True),
                 Column('registration_datetime', DateTime, default=func.now()),
                 Column('exchange', String, index=True),
                 Column('symbol', String, index=True),
                 Column('timestamp', Integer, index=True),
                 Column('price', Float),
                 Column('score', Float),
                 Column('power', Float),
                 Column('nr_bins', Integer),
                 Column('depth', Integer),
                 Column('threshold', Float),
                 Index(f'idx_{identifier}_1', 'exchange', 'symbol'),
                 Index(f'idx_{identifier}_2', 'exchange', 'symbol', 'timestamp', unique=True),
                 Index(f'idx_{identifier}_3', 'exchange', 'timestamp'),
                 extend_existing=True
                 )


def get_score_table_identifier(symbol: str) -> str:
    return f'score_{symbol.replace("/", "")}'
