from hawkbot.filters.trendreversalfilter.trend_reversal_filter import TrendReversalFilter
def get_filter_class(name: str):


    if name != TrendReversalFilter.__name__:
        raise Exception('Different value requested')
    return TrendReversalFilter
