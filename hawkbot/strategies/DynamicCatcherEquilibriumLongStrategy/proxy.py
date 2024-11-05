from hawkbot.strategies.DynamicCatcherEquilibriumLongStrategy.DynamicCatcherEquilibriumLongStrategy import DynamicCatcherEquilibriumLongStrategy
def get_strategy_class(name: str):


    if name != DynamicCatcherEquilibriumLongStrategy.__name__:
        raise Exception('Different value requested')
    return DynamicCatcherEquilibriumLongStrategy
