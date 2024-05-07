from hawkbot.plugins.gridstorage.gridstorage_plugin import GridStoragePlugin


def get_plugin_class(name: str):
    if name != GridStoragePlugin.__name__:
        raise Exception('Different value requested')
    return GridStoragePlugin
