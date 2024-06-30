from hawkbot.strategies.EmaFlipLongStrategy.EmaFlipLongStrategy import EmaFlipLongStrategy
def get_strategy_class(name: str):


    if name != EmaFlipLongStrategy.__name__:
        raise Exception('Different value requested')
    return EmaFlipLongStrategy
