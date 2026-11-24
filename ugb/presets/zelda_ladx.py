"""Ultra Game Boy preset: The Legend of Zelda: Link's Awakening DX (US v1.2).

Link's Awakening DX already has good colours, so this preset keeps them and
adds light: volume on trees and posts, shadows on the ground, texture on grass.
Tiles are recognised by a hash of their pixels, because the game loads the
same graphics into different VRAM slots in different areas.
"""
from ugb.presets.generic import RAMPS, SPRITE_SLOT, SPRITE_PIC, NPC_CYCLE  # noqa: F401

TITLE = 'ZELDA'
RAM = {}
TILESETS = {}
UI_FIRST_TILE = 256
GAME_COLOURS = True
REGION_OBJECTS = 'T'      # trees: one object per connected group of tree tiles


def _k(*hexes):
    return [int(h, 16) for h in hexes]


TILE_KEYS = {}
for h in _k('4f8671', '8ed753', '1bd938', 'f460a3', 'befb67', 'e90699', 'b56afe', '32694a'):
    TILE_KEYS[h] = 'g'        # grass, sand edging, flowers, dirt path
for h in _k('898cdb', '6ce8ca', 'c62dd8', '5f4bbf'):
    TILE_KEYS[h] = 'G'        # tall grass
for h in _k('ad942b', 'cfd336', 'd0f4d6', 'a6749e', '2c166f', 'c70c01', 'b3ba21', '04e70d',
            '757f56', '2034d4', 'f0b3be', 'e6125a', '150fef', 'edd1f2', 'da8791', 'bbfc2b'):
    TILE_KEYS[h] = 'T'        # the big round tree (4x4 tiles)
for h in _k('b45349', '2048e8'):
    TILE_KEYS[h] = 'P'        # wooden fence post (top, bottom)
for h in _k('90114b', 'ed1ee4'):
    TILE_KEYS[h] = 'R'        # blue roof
for h in _k('c5cbe4', '63f73f', 'a9226d', '45550b'):
    TILE_KEYS[h] = 'H'        # wooden house front
for h in _k('40d809', '43cfba', '9eeed5', '575294'):
    TILE_KEYS[h] = 'D'        # doorway

STAMPS = [(((0xb45349,), (0x2048e8,)), 'P')]
