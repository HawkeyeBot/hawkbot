from hawkbot.filters.last24hpricechangepctfilter.last_24h_pricechangepct_filter import Last24hPriceChangePctFilter
def get_filter_class(name: str):


    if name != Last24hPriceChangePctFilter.__name__:
        raise Exception('Different value requested')
    return Last24hPriceChangePctFilter
