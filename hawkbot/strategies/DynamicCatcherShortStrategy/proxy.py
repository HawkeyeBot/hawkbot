from hawkbot.strategies.DynamicCatcherShortStrategy.DynamicCatcherShortStrategy import DynamicCatcherShortStrategy
def get_strategy_class(name: str):


    if name != DynamicCatcherShortStrategy.__name__:
        raise Exception('Different value requested')
    return DynamicCatcherShortStrategy
