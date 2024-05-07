filters = []


def get_proxy_filter_class(name):
    for filter in filters:
        if filter.__name__ == name:
            return filter
    return None
