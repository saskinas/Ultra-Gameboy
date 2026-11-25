"""Presets by cartridge title. Games without one use the generic preset."""
from ugb.presets import generic, kirby_dream_land, mario_land, pokemon_yellow, zelda_ladx

BY_TITLE = {pokemon_yellow.TITLE: pokemon_yellow, zelda_ladx.TITLE: zelda_ladx,
            mario_land.TITLE: mario_land, kirby_dream_land.TITLE: kirby_dream_land}


def for_title(title):
    t = title.strip()
    for k, v in BY_TITLE.items():
        if t.startswith(k):
            return v
    return generic
