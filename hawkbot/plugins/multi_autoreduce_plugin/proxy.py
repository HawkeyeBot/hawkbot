from hawkbot.plugins.multi_autoreduce_plugin.multi_autoreduce_plugin import MultiAutoreducePlugin


def get_plugin_class(name: str):
    if name != MultiAutoreducePlugin.__name__:
        raise Exception('Different value requested')
    return MultiAutoreducePlugin
