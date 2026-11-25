"""Ultra Game Boy preset: Super Mario Land (World, Rev 1).

A 16-bit platformer look for all four worlds: a gradient sky, filled hills,
grassy ground over earth, green pipes lit as cylinders, gold ? blocks and coins,
soft clouds, the sea in World 2, stone and caves in World 3, bamboo and cloud
platforms in World 4. Original colours and shading, no art from other games.

Levels can be reached with tools/mario_levels.py (memory edits on the title
screen); tools/hash_sheet.py makes the labelling sheets.

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
    'water': hx('#0c2060', '#163496', '#2050c0', '#3074dc', '#5498ec', '#8cc4f8', '#d0ecff'),
    'wall': hx('#4a3020', '#7a5636', '#a67e52', '#ccaa74', '#e8cc98', '#f8e8c0'),
    'dirt2': hx('#2a1810', '#4a2e1a', '#6c4626', '#8e6234', '#ae8048'),
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


# ---- the other levels and worlds (from tools/mario_levels.py runs) ----
def _add(code, *hexes):
    for h in hexes:
        TILE_KEYS[int(h, 16)] = code


# World 1: 1-2 pillars and platforms, 1-3 inside the pyramid
_add('K', 'a560d6', '0ba422', '7e7347', '1f007a', '0652ca', '5bd28b')
_add('L', 'e4a3ff', '313433', 'a9f2db')
_add('H', '83edc6', '781d8e', '8fa024', '77dd69', '3bfda0', '0020d3', 'fc23f2', '079db7',
     'ebb2fc', 'eec362')
# World 2: the sea, coral rocks, stone platforms and pillars, square blocks
_add('W', 'eeb30e', 'f198e7', 'dc9421')
_add('K', '718357', '08eb6d', '0098a7', 'abe0cc', 'f5c250', '1877b9', '7511b2', '5f6441',
     'c7564a', '13f16a', '4ffcd0', '11bbbd', 'd3e8e4', '99c44a', '3ccb1b', '72a62e')
# World 3: rocky ground, stalactites, big stone blocks, stone heads, branches
_add('K', 'e85bb8', 'e33a48', 'bc2183', '7bde7d', 'c9c18a', '718e66', 'c2d897', 'c00eb0',
     '43e878', '9a26b7', 'f6c57a', '7919bb', '20604d', '3b789e', '625f10', '27c897',
     '8595af', '6bd137')
_add('T', 'a12d22', 'c59ca0', '6b93b7', '3943a9', 'bab5ee', '4575e8')   # hanging vines (3-2)
_add('K', 'ff1a10', 'deced3', '4c098a', 'd0157c', '6274eb', 'e65c3d', '544dfb', '0906cc',
     '5256b4', '8bfc17', '68bbec', '3b98c4')   # outlines of the stone heads (3-1)
# World 4: dark blocks and bricks, key-pattern ground, bamboo, clouds, cloud-top ground
_add('K', '55e9a6', '2a8d52', '3db338', '048a1d', 'd414fe', 'b0cb20', '58a8aa', '223491',
     'cc5bba')
_add('T', 'a3fa1e', '729f2f', '660032', '02e557', '97de38', '515781', 'f57ddd', 'cbf961',
     'eedbd9', '277d7a', '0787ca', 'f09283', '71cca6', '07db98', '2799bd', 'd91dc0',
     'fe9afc', '911b7c', '85d7fa')
_add('Z', 'fd4e99', 'd3b67b', 'b14dd3', '468250', 'a6201f', '18a7a7', '5149e8', 'cb8a18',
     'adfbc5', 'fede58', '973acb')
_add('L', 'b98b53', '90526a', '52131c', 'e8c76b', '86b0ca', 'a3da36', 'c12da3', '960bb9')
_add('V', 'a8de6d', '99f936', '75b65d', '7754ee')
