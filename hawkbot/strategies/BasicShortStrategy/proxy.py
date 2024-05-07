from hawkbot.strategies.BasicShortStrategy.basicshortstrategy import BasicShortStrategy
def get_strategy_class(name: str):


    if name != BasicShortStrategy.__name__:
        raise Exception('Different value requested')
    return BasicShortStrategy
