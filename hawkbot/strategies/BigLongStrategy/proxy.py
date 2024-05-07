from hawkbot.strategies.BigLongStrategy.biglongstrategy import BigLongStrategy
def get_strategy_class(name: str):


    if name != BigLongStrategy.__name__:
        raise Exception('Different value requested')
    return BigLongStrategy
