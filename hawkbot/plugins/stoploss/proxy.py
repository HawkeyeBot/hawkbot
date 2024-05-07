from hawkbot.plugins.stoploss.stoploss_plugin import StoplossPlugin


def get_plugin_class(name: str):
    if name != StoplossPlugin.__name__:
        raise Exception('Different value requested')
    return StoplossPlugin
