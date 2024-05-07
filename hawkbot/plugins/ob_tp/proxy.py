from hawkbot.plugins.ob_tp.ob_tp_plugin import ObTpPlugin


def get_plugin_class(name: str):
    if name != ObTpPlugin.__name__:
        raise Exception('Different value requested')
    return ObTpPlugin
