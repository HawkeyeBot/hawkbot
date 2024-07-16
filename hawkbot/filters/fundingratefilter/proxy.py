from hawkbot.filters.fundingratefilter.fundingrate_filter import FundingRateFilter
def get_filter_class(name: str):


    if name != FundingRateFilter.__name__:
        raise Exception('Different value requested')
    return FundingRateFilter
