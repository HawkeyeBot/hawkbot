from hawkbot.strategies.ManualScalpLongStrategy.ManualScalpLongStrategy import ManualScalpLongStrategy
def get_strategy_class(name: str):


    if name != ManualScalpLongStrategy.__name__:
        raise Exception('Different value requested')
    return ManualScalpLongStrategy
