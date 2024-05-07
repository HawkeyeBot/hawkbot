from hawkbot.plugins.cryptofeed_plugin.cryptofeed_plugin import CryptofeedPlugin


def get_plugin_class(name: str):
    if name != CryptofeedPlugin.__name__:
        raise Exception('Different value requested')
    return CryptofeedPlugin
