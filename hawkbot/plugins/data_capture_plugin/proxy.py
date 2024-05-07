from hawkbot.plugins.data_capture_plugin.data_capture_plugin import DataCapturePlugin


def get_plugin_class(name: str):
    if name != DataCapturePlugin.__name__:
        raise Exception('Different value requested')
    return DataCapturePlugin
