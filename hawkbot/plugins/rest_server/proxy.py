from hawkbot.plugins.rest_server.rest_server import RestServer


def get_plugin_class(name: str):
    if name != RestServer.__name__:
        raise Exception('Different value requested')
    return RestServer
