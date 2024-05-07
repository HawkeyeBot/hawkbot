from hawkbot.plugins.scorestore.score_store import ScoreStorePlugin


def get_plugin_class(name: str):
    if name != ScoreStorePlugin.__name__:
        raise Exception('Different value requested')
    return ScoreStorePlugin
