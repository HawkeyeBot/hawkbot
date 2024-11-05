from hawkbot.strategies.CatcherEquilibriumShortStrategy.CatcherEquilibriumShortStrategy import CatcherEquilibriumShortStrategy
def get_strategy_class(name: str):


    if name != CatcherEquilibriumShortStrategy.__name__:
        raise Exception('Different value requested')
    return CatcherEquilibriumShortStrategy
