from hawkbot.filters.symbolfilter.symbol_filter import SymbolFilter
def get_filter_class(name: str):


    if name != SymbolFilter.__name__:
        raise Exception('Different value requested')
    return SymbolFilter
