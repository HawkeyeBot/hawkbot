from hawkbot.filters.emareversalfilter.ema_reversal_filter import EmaReversalFilter
def get_filter_class(name: str):


    if name != EmaReversalFilter.__name__:
        raise Exception('Different value requested')
    return EmaReversalFilter
