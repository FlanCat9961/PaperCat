from papercat.gui.i18n.zh_CN import T


def t(key: str) -> str:
    return T.get(key, key)


__all__ = ["T", "t"]
