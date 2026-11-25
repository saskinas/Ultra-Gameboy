"""Ultra Game Boy preset: Super Mario Land (World, Rev 1).

A 16-bit platformer look for World 1 (Birabuto): a gradient sky, filled hills,
grassy ground over earth, green pipes lit as cylinders, gold ? blocks and coins,
soft clouds. Original colours and shading, no art from other games.

Tiles are recognised by a hash of their pixels (tools/hash_sheet.py), because
each world loads its own graphics.
"""
from ugb.fx import hx

TITLE = 'SUPER MARIOLAND'
RAM = {}
TILESETS = {}
UI_FIRST_TILE = 256
GAME_COLOURS = False

RAMPS = {
    'sky': hx('#2850b8', '#3866d0', '#4c80e0', '#68a0ec', '#8cbcf4', '#b4d8f8', '#d8ecfc'),
    'hill': hx('#2c5a48', '#3a7458', '#4c8e66', '#64a874', '#82c088', '#a4d8a0'),
    'ground': hx('#2c6a28', '#3e8a2e', '#58a838', '#7cc444', '#a8dc5c', '#d4f088'),
    'lawn': hx('#24601c', '#2e7a24', '#3e942c', '#56ac38', '#74c448'),
    'dirt': hx('#3a1c0c', '#5e3214', '#88501e', '#b0702c', '#d4964a'),
    'earth': hx('#341a0c', '#56301a', '#7a4826', '#9e6434', '#c08448', '#dca868'),
    'tree': hx('#123620', '#1c5028', '#2a6c30', '#3e8a36', '#5aa83e', '#86c858'),
    'rock': hx('#2a2430', '#4a4250', '#6c6472', '#90888e', '#b4acac', '#d8d2cc'),
    'gold': hx('#5a3008', '#8e5410', '#c4801a', '#e8a828', '#f8d048', '#fff0a0'),
    'pipe': hx('#0c3418', '#12522a', '#1c7438', '#2c964a', '#4cb860', '#88dc88', '#c8f4b8'),
    'cloud': hx('#7890c8', '#a0b4e0', '#c8d4f0', '#e4ecfa', '#ffffff'),
    'specks': hx('#3e8a2e', '#7cc444'),
    'neutral': hx('#202028', '#505060', '#8a8a98', '#c8c8d0', '#f4f4f8'),
}
SPRITE_SLOT = {}
SPRITE_PIC = {}
NPC_CYCLE = []


def _k(*hexes):
    return [int(h, 16) for h in hexes]


TILE_KEYS = {}
for h in _k('b77a35', 'dd5805'):
    TILE_KEYS[h] = 'Y'          # sky, and the striped band at the top of the sky
TILE_KEYS[int('4f8671', 16)] = 'A'   # plain fill: platform inside when on ground, else sky
TILE_KEYS[int('599106', 16)] = 'L'   # ground: grassy top edge
TILE_KEYS[int('d16b50', 16)] = 'E'   # ground: earth below
for h in _k('6b9e29', '83e50d', '07980e'):
    TILE_KEYS[h] = 'h'          # outline hills
for h in _k('f835e9', '53f6ca', '969645'):
    TILE_KEYS[h] = 'T'          # palm trees (trunk, fronds)
for h in _k('5a5306', 'e4dfee', '852b37'):
    TILE_KEYS[h] = 'Q'          # ? blocks and coins
TILE_KEYS[int('1a9e06', 16)] = 'K'   # hard blocks
for h in _k('8c2e95', 'db2d8b', '5f6266', 'e414dd'):
    TILE_KEYS[h] = 'V'          # pipes (top left/right, body left/right)
for h in _k('be4f3c', '029bbf', '3544e6', 'ac3059', 'c57d13', '9ba361', '2995f6'):
    TILE_KEYS[h] = 'Z'          # clouds

STAMPS = [
    (((0x8c2e95, 0xdb2d8b),), 'V'),     # pipe top, lit across both tiles
    (((0x5f6266, 0xe414dd),), 'V'),     # pipe body
    (((0x5a5306,),), 'Q'),
    (((0xe4dfee,),), 'Q'),
    (((0x852b37,),), 'Q'),
]
