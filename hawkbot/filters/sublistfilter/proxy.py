from hawkbot.filters.sublistfilter.sub_list_filter import SubListFilter
def get_filter_class(name: str):


    if name != SubListFilter.__name__:
        raise Exception('Different value requested')
    return SubListFilter
