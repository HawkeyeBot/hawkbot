from hawkbot.strategies.CatcherEquilibriumLongStrategy.CatcherEquilibriumLongStrategy import CatcherEquilibriumLongStrategy
def get_strategy_class(name: str):


    if name != CatcherEquilibriumLongStrategy.__name__:
        raise Exception('Different value requested')
    return CatcherEquilibriumLongStrategy
