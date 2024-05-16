import logging
from typing import List, Dict

from hawkbot.core.data_classes import PositionSide
from hawkbot.plugins.gridstorage.data_classes import QuantityRecord, PriceRecord
from hawkbot.plugins.gridstorage.memory_repository import MemoryRepository
from hawkbot.plugins.gridstorage.persistent_repository import PersistentRepository
from hawkbot.core.plugins.plugin import Plugin

logger = logging.getLogger(__name__)


class GridStoragePlugin(Plugin):
    @classmethod
    def plugin_name(cls):
        return cls.__name__

    def __init__(self, name: str, plugin_loader, plugin_config, redis_host: str, redis_port: int) -> None:
        super().__init__(name=name, plugin_loader=plugin_loader, plugin_config=plugin_config, redis_host=redis_host, redis_port=redis_port)
        if 'in-memory' in plugin_config and plugin_config['in-memory'] is True:
            self.repository = MemoryRepository()
        else:
            if 'database_path' in plugin_config:
                database_path = plugin_config['database_path']
            else:
                database_path = 'data/gridstorage_plugin.db'

            self.repository = PersistentRepository(database_path)

    def store_quantities(self, symbol: str, quantities: List[QuantityRecord]):
        if len(quantities) == 0:
            return
        logger.debug(f'Adding quantities list for symbol {symbol}')
        self.repository.store_quantities(symbol=symbol, quantities=quantities)
        logger.debug(f'Stored quantity grid {symbol}')

    def get_quantities(self, symbol: str, position_side: PositionSide) -> List[QuantityRecord]:
        return self.repository.get_quantities(symbol=symbol, position_side=position_side)

    def store_prices(self, symbol: str, prices_records: List[PriceRecord]):
        if len(prices_records) == 0:
            return

        logger.debug(f'Adding prices list for symbol {symbol}')
        self.repository.store_prices(symbol=symbol, prices_records=prices_records)
        logger.debug(f'Stored price grid {symbol}')

    def get_prices(self, symbol: str, position_side: PositionSide) -> List[float]:
        return self.repository.get_prices(symbol=symbol, position_side=position_side)

    def get_root_price(self, symbol: str, position_side: PositionSide) -> float:
        return self.repository.get_root_price(symbol=symbol, position_side=position_side)

    def store_root_price(self, symbol: str, position_side: PositionSide, price: float):
        logger.debug(f'Adding root price for symbol {symbol} {position_side.name}: {price}')
        self.repository.store_root_price(symbol=symbol, position_side=position_side, price=price)
        logger.debug(f'Stored root price {symbol} {position_side.name}: {price}')

    def reset(self, symbol: str, position_side: PositionSide):
        logger.debug(f'Resetting price & quantities for symbol {symbol} for {position_side.name}')
        self.repository.reset_quantities(symbol=symbol, position_side=position_side)
        self.repository.reset_prices(symbol=symbol, position_side=position_side)
        self.repository.reset_root_price(symbol=symbol, position_side=position_side)

    def reset_quantities(self, symbol: str, position_side: PositionSide):
        logger.debug(f'Resetting quantities for symbol {symbol} for {position_side.name}')
        self.repository.reset_quantities(symbol=symbol, position_side=position_side)
        logger.debug(f'Reset quantity grid for {symbol} for {position_side.name}')

    def is_correctly_filled_for(self, symbol: str, position_side: PositionSide) -> bool:
        prices = self.get_prices(symbol=symbol, position_side=position_side)
        quantities = self.get_quantities(symbol=symbol, position_side=position_side)

        logger.debug(f'{symbol} {position_side.name}: Prices = {prices}, quantities = {quantities}')
        return len(prices) > 0 and len(quantities) > 0
