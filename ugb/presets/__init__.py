"""Presets by cartridge title. Games without one use the generic preset."""
from ugb.presets import generic, pokemon_yellow, zelda_ladx

BY_TITLE = {pokemon_yellow.TITLE: pokemon_yellow, zelda_ladx.TITLE: zelda_ladx}


def for_title(title):
    t = title.strip()
    for k, v in BY_TITLE.items():
        if t.startswith(k):
            return v
    return generic
