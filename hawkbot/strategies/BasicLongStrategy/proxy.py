from hawkbot.strategies.BasicLongStrategy.basiclongstrategy import BasicLongStrategy
def get_strategy_class(name: str):


    if name != BasicLongStrategy.__name__:
        raise Exception('Different value requested')
    return BasicLongStrategy
