from hawkbot.filters.volatilityfilter.volatility_filter import VolatilityFilter
def get_filter_class(name: str):


    if name != VolatilityFilter.__name__:
        raise Exception('Different value requested')
    return VolatilityFilter
