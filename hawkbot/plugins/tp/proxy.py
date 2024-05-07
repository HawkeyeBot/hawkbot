from hawkbot.plugins.tp.tp_plugin import TpPlugin


def get_plugin_class(name: str):
    if name != TpPlugin.__name__:
        raise Exception('Different value requested')
    return TpPlugin
