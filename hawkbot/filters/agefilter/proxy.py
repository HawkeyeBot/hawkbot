from hawkbot.filters.agefilter.age_filter import AgeFilter
def get_filter_class(name: str):


    if name != AgeFilter.__name__:
        raise Exception('Different value requested')
    return AgeFilter
