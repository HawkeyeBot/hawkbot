from hawkbot.strategies.BigShortStrategy.bigshortstrategy import BigShortStrategy
def get_strategy_class(name: str):


    if name != BigShortStrategy.__name__:
        raise Exception('Different value requested')
    return BigShortStrategy
