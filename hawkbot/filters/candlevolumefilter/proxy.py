from hawkbot.filters.candlevolumefilter.candle_volume_filter import CandleVolumeFilter
def get_filter_class(name: str):


    if name != CandleVolumeFilter.__name__:
        raise Exception('Different value requested')
    return CandleVolumeFilter
