from hawkbot.filters.atrfilter.atr_filter import ATRFilter
def get_filter_class(name: str):


    if name != ATRFilter.__name__:
        raise Exception('Different value requested')
    return ATRFilter
