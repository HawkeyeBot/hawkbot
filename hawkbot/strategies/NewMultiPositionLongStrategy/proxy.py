from hawkbot.strategies.NewMultiPositionLongStrategy.newmultipositionlongstrategy import NewMultiPositionLongStrategy
def get_strategy_class(name: str):


    if name != NewMultiPositionLongStrategy.__name__:
        raise Exception('Different value requested')
    return NewMultiPositionLongStrategy
