from hawkbot.plugins.log_reporter.log_reporter_plugin import LogReporterPlugin


def get_plugin_class(name: str):
    if name != LogReporterPlugin.__name__:
        raise Exception('Different value requested')
    return LogReporterPlugin
