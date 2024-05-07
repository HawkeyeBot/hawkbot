from hawkbot.plugins.clustering_sr.clustering_sr_plugin import ClusteringSupportResistancePlugin


def get_plugin_class(name: str):
    if name != ClusteringSupportResistancePlugin.__name__:
        raise Exception('Different value requested')
    return ClusteringSupportResistancePlugin
