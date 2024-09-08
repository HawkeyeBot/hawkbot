from hawkbot.strategies.FastCatcherLongStrategy.FastCatcherLongStrategy import FastCatcherLongStrategy
def get_strategy_class(name: str):


    if name != FastCatcherLongStrategy.__name__:
        raise Exception('Different value requested')
    return FastCatcherLongStrategy
