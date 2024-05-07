from hawkbot.filters.last24hvolumefilter.last_24h_volume_filter import Last24hVolumeFilter
def get_filter_class(name: str):


    if name != Last24hVolumeFilter.__name__:
        raise Exception('Different value requested')
    return Last24hVolumeFilter
