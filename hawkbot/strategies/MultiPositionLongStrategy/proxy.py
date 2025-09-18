from hawkbot.strategies.MultiPositionLongStrategy.multipositionlongstrategy import MultiPositionLongStrategy
def get_strategy_class(name: str):


    if name != MultiPositionLongStrategy.__name__:
        raise Exception('Different value requested')
    return MultiPositionLongStrategy
