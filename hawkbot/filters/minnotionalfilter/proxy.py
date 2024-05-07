from hawkbot.filters.minnotionalfilter.min_notional_filter import MinNotionalFilter
def get_filter_class(name: str):


    if name != MinNotionalFilter.__name__:
        raise Exception('Different value requested')
    return MinNotionalFilter
