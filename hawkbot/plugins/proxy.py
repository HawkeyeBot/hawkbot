plugins = []


def get_proxy_plugin_class(name):
    for plugin in plugins:
        if plugin.__name__ == name:
            return plugin
    return None
