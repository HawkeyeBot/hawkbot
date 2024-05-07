from hawkbot.filters.tickcountfilter.tickcount_filter import TickcountFilter
def get_filter_class(name: str):


    if name != TickcountFilter.__name__:
        raise Exception('Different value requested')
    return TickcountFilter
