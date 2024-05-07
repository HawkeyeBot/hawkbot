from hawkbot.filters.maxquantityfilter.maxquantityfilter import MaxQuantityFilter
def get_filter_class(name: str):


    if name != MaxQuantityFilter.__name__:
        raise Exception('Different value requested')
    return MaxQuantityFilter
