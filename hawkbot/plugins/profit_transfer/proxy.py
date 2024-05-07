from hawkbot.plugins.profit_transfer.profit_transfer_plugin import ProfitTransferPlugin


def get_plugin_class(name: str):
    if name != ProfitTransferPlugin.__name__:
        raise Exception('Different value requested')
    return ProfitTransferPlugin
