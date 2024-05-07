from hawkbot.plugins.gtfo.gtfo_plugin import GtfoPlugin


def get_plugin_class(name: str):
    if name != GtfoPlugin.__name__:
        raise Exception('Different value requested')
    return GtfoPlugin
