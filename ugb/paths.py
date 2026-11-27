"""Where Ultra Game Boy keeps the files it writes.

Run from the source tree, that's the project folder (states/, out/, cache/,
as before). Run as the packaged app (PyInstaller), the program folder may not
be writable, so they go to the user's own app-data folder instead:
%APPDATA%/Ultra Game Boy on Windows, ~/.ultra-game-boy elsewhere. UGB_DATA
overrides both.
"""
import os
import sys

FROZEN = bool(getattr(sys, 'frozen', False))
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    d = os.environ.get('UGB_DATA')
    if not d:
        if not FROZEN:
            d = HERE
        elif os.name == 'nt':
            d = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'Ultra Game Boy')
        else:
            d = os.path.join(os.path.expanduser('~'), '.ultra-game-boy')
    os.makedirs(d, exist_ok=True)
    return d


def data_path(*parts):
    """A path under data_dir(); its folder is made if needed."""
    p = os.path.join(data_dir(), *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p
