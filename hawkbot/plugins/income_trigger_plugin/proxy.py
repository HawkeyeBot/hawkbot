from hawkbot.plugins.income_trigger_plugin.income_trigger_plugin import IncomeTriggerPlugin


def get_plugin_class(name: str):
    if name != IncomeTriggerPlugin.__name__:
        raise Exception('Different value requested')
    return IncomeTriggerPlugin
