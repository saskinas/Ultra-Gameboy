"""Find ROMs in input/ by a short name, e.g. UGB_ROM=zelda or UGB_ROM=balloon."""
import glob
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALIASES = {'yellow': 'Pokemon - Yellow', 'zelda': "Link's Awakening", 'balloon': 'Balloon Kid'}


def rom_path(name=None):
    name = name or os.environ.get('UGB_ROM', 'yellow')
    if os.path.exists(name):
        return name
    key = ALIASES.get(name.lower(), name).lower()
    for p in sorted(glob.glob(os.path.join(HERE, 'input', '*.gb*'))):
        if key in os.path.basename(p).lower() and not p.endswith(('.ram', '.bak')):
            return p
    raise FileNotFoundError('no ROM matching %r in input/' % name)
