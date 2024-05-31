from hawkbot.strategies.ManualScalpShortStrategy.ManualScalpShortStrategy import ManualScalpShortStrategy
def get_strategy_class(name: str):


    if name != ManualScalpShortStrategy.__name__:
        raise Exception('Different value requested')
    return ManualScalpShortStrategy
