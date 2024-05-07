from hawkbot.filters.csvsymbolfilter.csv_symbol_filter import CsvSymbolFilter
def get_filter_class(name: str):


    if name != CsvSymbolFilter.__name__:
        raise Exception('Different value requested')
    return CsvSymbolFilter
