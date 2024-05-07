from hawkbot.plugins.tp_refill.tp_refill_plugin import TpRefillPlugin


def get_plugin_class(name: str):
    if name != TpRefillPlugin.__name__:
        raise Exception('Different value requested')
    return TpRefillPlugin
