from hawkbot.plugins.wiggle.wiggle_plugin import WigglePlugin


def get_plugin_class(name: str):
    if name != WigglePlugin.__name__:
        raise Exception('Different value requested')
    return WigglePlugin
