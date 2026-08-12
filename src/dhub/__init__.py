"""d-hub: one-process multi-agent coordination layer."""

from .config import VERSION as __version__

__all__ = ["__version__"]


def __getattr__(name):
    if name == "app":
        from .app import app

        return app
    raise AttributeError(name)
