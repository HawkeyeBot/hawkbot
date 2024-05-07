from hawkbot.plugins.hedge_plugin.hedge_plugin import HedgePlugin


def get_plugin_class(name: str):
    if name != HedgePlugin.__name__:
        raise Exception('Different value requested')
    return HedgePlugin
