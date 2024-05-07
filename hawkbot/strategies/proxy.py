strategies = []


def get_proxy_strategy_class(name):
    for strategy in strategies:
        if strategy.__name__ == name:
            return strategy
    return None
