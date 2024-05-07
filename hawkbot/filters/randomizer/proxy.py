from hawkbot.filters.randomizer.randomizer_filter import RandomizerFilter
def get_filter_class(name: str):


    if name != RandomizerFilter.__name__:
        raise Exception('Different value requested')
    return RandomizerFilter
