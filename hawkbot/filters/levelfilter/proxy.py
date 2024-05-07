from hawkbot.filters.levelfilter.level_filter import LevelFilter
def get_filter_class(name: str):


    if name != LevelFilter.__name__:
        raise Exception('Different value requested')
    return LevelFilter
