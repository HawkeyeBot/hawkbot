from hawkbot.strategies.TrailingEntryLongStrategy.trailingentrylongstrategy import TrailingEntryLongStrategy
def get_strategy_class(name: str):


    if name != TrailingEntryLongStrategy.__name__:
        raise Exception('Different value requested')
    return TrailingEntryLongStrategy
