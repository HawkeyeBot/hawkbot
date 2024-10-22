from hawkbot.strategies.DynamicCatcherLongStrategy.DynamicCatcherLongStrategy import DynamicCatcherLongStrategy
def get_strategy_class(name: str):


    if name != DynamicCatcherLongStrategy.__name__:
        raise Exception('Different value requested')
    return DynamicCatcherLongStrategy
