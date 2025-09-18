from hawkbot.strategies.ManualHedgedWiggleStrategy.ManualHedgedWiggleStrategy import ManualHedgedWiggleStrategy
def get_strategy_class(name: str):


    if name != ManualHedgedWiggleStrategy.__name__:
        raise Exception('Different value requested')
    return ManualHedgedWiggleStrategy
