from hawkbot.plugins.autoreduce.autoreduce_plugin import AutoreducePlugin


def get_plugin_class(name: str):
    if name != AutoreducePlugin.__name__:
        raise Exception('Different value requested')
    return AutoreducePlugin
