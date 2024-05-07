from hawkbot.plugins.orderbook_sr.orderbook_sr import OrderbookSrPlugin


def get_plugin_class(name: str):
    if name != OrderbookSrPlugin.__name__:
        raise Exception('Different value requested')
    return OrderbookSrPlugin
