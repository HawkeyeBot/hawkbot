from hawkbot.plugins.stoplosses.stoplosses_plugin import StoplossesPlugin


def get_plugin_class(name: str):
    if name != StoplossesPlugin.__name__:
        raise Exception('Different value requested')
    return StoplossesPlugin
