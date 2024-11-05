from hawkbot.strategies.DynamicCatcherEquilibriumShortStrategy.DynamicCatcherEquilibriumShortStrategy import DynamicCatcherEquilibriumShortStrategy
def get_strategy_class(name: str):


    if name != DynamicCatcherEquilibriumShortStrategy.__name__:
        raise Exception('Different value requested')
    return DynamicCatcherEquilibriumShortStrategy
