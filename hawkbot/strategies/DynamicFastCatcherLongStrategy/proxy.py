from hawkbot.strategies.DynamicFastCatcherLongStrategy.DynamicFastCatcherLongStrategy import DynamicFastCatcherLongStrategy
def get_strategy_class(name: str):


    if name != DynamicFastCatcherLongStrategy.__name__:
        raise Exception('Different value requested')
    return DynamicFastCatcherLongStrategy
