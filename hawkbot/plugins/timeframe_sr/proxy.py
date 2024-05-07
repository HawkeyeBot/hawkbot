from hawkbot.plugins.timeframe_sr.timeframe_sr_plugin import TimeframeSupportResistancePlugin


def get_plugin_class(name: str):
    if name != TimeframeSupportResistancePlugin.__name__:
        raise Exception('Different value requested')
    return TimeframeSupportResistancePlugin
