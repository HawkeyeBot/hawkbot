from hawkbot.filters.dynamicpricechangepctfilter.dynamic_pricechangepct_filter import DynamicPriceChangePctFilter
def get_filter_class(name: str):


    if name != DynamicPriceChangePctFilter.__name__:
        raise Exception('Different value requested')
    return DynamicPriceChangePctFilter
