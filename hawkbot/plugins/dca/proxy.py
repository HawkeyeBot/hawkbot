from hawkbot.plugins.dca.dca_plugin import DcaPlugin


def get_plugin_class(name: str):
    if name != DcaPlugin.__name__:
        raise Exception('Different value requested')
    return DcaPlugin
