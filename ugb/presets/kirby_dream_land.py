"""Ultra Game Boy preset: Kirby's Dream Land. The special one.

Kirby is the one game where game-specific code is welcome (docs/KIRBY_PLAN.md):
vibrant colours, a hand-tuned look per stage, and parallax backdrops drawn by code
behind the open sky. All art is procedural and original; nothing is taken from
later Kirby games.

Tiles are recognised by a hash of their pixels (tools/hash_sheet.py).
States for labelling come from tools/kirby_run.py.
"""
import numpy as np

from ugb.fx import hx

TITLE = 'KIRBY DREAM LAN'
RAM = {'extra_game': 0xD03A}   # 1 in the hidden Extra Game (Up+A+Select on the title)

def camera_x(mem):
    """The camera's world X: D051 counts 16 px columns (one ahead), D053 holds
    the low bits (it is SCX)."""
    return (mem[0xD051] - 1) * 16 + (mem[0xD053] & 15)


def camera(mem):
    """Camera world (x, y) to anchor ugb.atlas. Y the same way as X: D052 counts
    16 px rows (one ahead; rooms sit lower in the world, the tree's at 512) and
    SCY holds the low bits."""
    return camera_x(mem), (mem[0xD052] - 1) * 16 + (mem[0xFF42] & 15)


RAM['area'] = 0xD03E     # area within the stage (0 outside, 1 behind the first door...)

# How ugb.atlas drives a hidden copy across an area: Kirby's screen X and Y
# (D05C, D05D) are pinned just past the scroll threshold the way it should go,
# a direction held and A tapped to keep flying; the game scrolls (about 6 px a
# frame, slow enough to stream every column) until it reaches the area's edge.
#
# The game decompresses the level forwards only, so the camera can't scroll back
# further than its 256 px ring of columns. To see an area's left part from the
# middle of it, the copy first loses a life: the game restarts the area at its
# start (ugb.atlas keeps that only if it comes back to the same area).
SCROLLS_ITSELF = {(4, 7)}     # Kaboola's sky on Mt. DeDeDe: the screen scrolls by itself


def area_key(m):
    """Stage bytes, area within the stage and the Extra Game; None outside play."""
    if m[0xD03C] == 0x11 and m[0xD03B] == 4 and m[RAM['area']] == 5 and m[0xD160] == 1:
        pass            # (King DeDeDe's ring; 0x11 is also the stage's intro and the ending,
                        # where D160 is 0: not captured)
    elif m[0xD03C] not in (0x0D, 0x08, 0x10, 0x0E, 0x0F, 0x12):   # (0x08: areas that scroll up and down; 0x10: Castle Lololo's; 0x0E: Float Islands'; 0x0F: Bubbly Clouds'; 0x12: Mt. DeDeDe's)
        return None
    if (m[0xD03B], m[RAM['area']]) in SCROLLS_ITSELF:
        return None     # (drawn frame by frame: a capture of it doesn't hold together)
    return (m[0xD039], m[0xD03B], m[RAM['area']], m[RAM['extra_game']])


def _lose_life(m):
    m[0xD089] = max(m[0xD089], 3)   # lives + 1: with none left the copy would hit game over
    m[0xD086] = 0          # health


def _keep_alive(m):
    m[0xD086] = 6          # health (in the copy only)


def _start_game(pb):
    """From the title screen, in a copy: press Start until the first area is in
    play (ugb.lineart.precapture captures it before the player has started)."""
    m = pb.memory
    for i in range(3000):
        if i % 40 == 0:
            pb.button_press('start')
        if i % 40 == 4:
            pb.button_release('start')
        pb.tick(1, False)
        if area_key(m) is not None and m[0xD03C] == 0x0D:
            return True
    return False


SWEEP = {'camera': camera, 'pin_x': 0xD05C, 'pin_y': 0xD05D,
         'key': area_key, 'restart': _lose_life, 'start_game': _start_game,
         'on_title': lambda m: m[0xD03C] == 0, 'rounds': 8, 'settle': 90,
         'moves': [('left', ['left'], 0x44, 0x0C, True),       # (high, over tall pillars)
                   ('up', ['up'], 0x50, 0x0C, True),
                   ('right', ['right'], 0x50, 0x0C, True),
                   ('right low', ['right'], 0x50, 0x58, True),  # (just above the floor, under beams)
                   # up, with Y free (pinned, it wouldn't scroll), at three places
                   # across the screen: a shaft may be beside a beam
                   ('up mid', ['up'], 0x50, None, True),
                   ('up right', ['up', 'right'], None, None, True),
                   ('up left', ['up'], 0x18, None, True),
                   # areas taller than the screen (climbed in stages): free flight
                   # both ways and up again at each end, round after round
                   # (right first: the game scrolls only as Kirby walks across its
                   # scroll point, and the last move left him left of it)
                   ('right free', ['right'], None, None, True, 'tall'),
                   ('up right free', ['up', 'right'], None, None, True, 'tall'),
                   ('left free', ['left'], None, None, True, 'tall'),
                   ('up free', ['up'], None, None, True, 'tall'),
                   ('up left free', ['up', 'left'], None, None, True, 'tall'),
                   ('down', ['down'], 0x50, None, False),       # (falling: pinned low it scrolls into the void)
                   ('down right', ['down', 'right'], None, None, False),   # (and through gaps
                   ('down left', ['down', 'left'], None, None, False),     # to either side)
                   # narrow areas that descend: drop at every 16 px across the
                   # screen, to find the gaps in the floors
                   *[('drop %d' % x, [], x, None, 'b', 'narrow', 'descend') for x in range(0x14, 0xA0, 0x10)],
                   ('left again', ['left'], 0x44, 0x58, True, 'tall')]}
TILESETS = {}
UI_FIRST_TILE = 256
GAME_COLOURS = False
LINE_ART = True     # white shapes outlined on a white sky: classify regions map-wide
SPRITE_SLOT = {}
SPRITE_PIC = {}
NPC_CYCLE = []

RAMPS = {
    # Green Greens: a bright spring morning
    'sky': hx('#3a78e0', '#4a8cf0', '#64a6f6', '#86c4fa', '#acdcfc', '#d6f2ff', '#f2fbff'),
    'hill': hx('#2a7a5a', '#38966a', '#4cb07a', '#6ac88c', '#90dca4', '#bcecc4'),
    'ground': hx('#1e7a2c', '#2c9a34', '#46b83e', '#6cd04c', '#9ae268', '#ccf49c'),
    'dirt': hx('#2a8a34', '#3aa23c', '#52b846', '#70cc54', '#96dc6c'),
    'earth': hx('#227a30', '#329438', '#48ac40', '#64c04c', '#86d462', '#b0e888'),
    'tallgrass': hx('#0c4a22', '#14682c', '#1e8636', '#30a444', '#52c05a', '#84d874', '#b8ec9c'),
    'rock': hx('#3a3478', '#544ea0', '#7270c0', '#9898dc', '#c2c2f0', '#eaeaff'),
    'cloud': hx('#8aa0e8', '#aebef4', '#d2dcfa', '#ecf2ff', '#ffffff'),
    'specks': hx('#46b83e', '#9ae268'),
    'neutral': hx('#2a2440', '#5a5480', '#9890b8', '#d0cce4', '#fbf8ff'),
    # the forest: canopy (white dots are light catching the leaves; the dark
    # shade is the deep forest behind), bark, star blocks, berries
    'tree': hx('#0e3a24', '#16502c', '#1e6a34', '#2e8840', '#4aa84c', '#76c464', '#a8e088'),
    'bark': hx('#3a2010', '#5a3418', '#7c4c24', '#9e6a36', '#c08c50', '#dcb07a'),
    'post': hx('#3a2010', '#5a3418', '#7c4c24', '#9e6a36', '#c08c50', '#dcb07a'),
    'pipe': hx('#3a2010', '#5a3418', '#7c4c24', '#9e6a36', '#c08c50', '#dcb07a'),
    'sign': hx('#0a2a1a', '#123a24', '#1a4c2e', '#245e38', '#2e7042'),
    'gold': hx('#6a3a00', '#b06a08', '#e8a018', '#ffd040', '#fff090', '#fffde0'),
    # rooms: a quilted plum wall, warm wood, cream pillars, light through the door
    'room': hx('#140c26', '#1e1236', '#2a1a48', '#38245a', '#4a306e', '#5e3e84'),
    'heartwood': hx('#1a0c06', '#2a140a', '#3c1e0e', '#502a14', '#66381c'),
    'floor': hx('#3a1c0c', '#5e3014', '#86481e', '#ac642c', '#cc8440', '#e8a862'),
    'furniture': hx('#3a1c0c', '#5e3014', '#86481e', '#ac642c', '#cc8440', '#e8a862', '#f8d090'),
    'pillar': hx('#5a3a5a', '#8a6080', '#b48ca4', '#d8b8c8', '#f0dce4', '#fff4f6'),
    'doorway': hx('#ffb848', '#ffd068', '#ffe494', '#fff2c4', '#fffbe8'),
    'berry': hx('#4a0820', '#8a1434', '#c8304c', '#ee5a6c', '#ff9cac', '#fff0f2'),
    # status bar icons
    'health': hx('#8a4a00', '#d08a10', '#f6c020', '#ffe050', '#fff4a0', '#fffde0'),
    'health_empty': hx('#b07090', '#d8a0bc', '#ecc4d6', '#f8e0ea', '#fff4f8'),
    'boss_health': hx('#6a0c1c', '#b0222c', '#e8503c', '#ff8458', '#ffb894', '#fff0e8'),
    'boss': hx('#2a1030', '#4a1e50', '#704080', '#9a68a8', '#c8a0d0', '#f4e4f6'),
    'kirby': hx('#6a0c3a', '#c0306e', '#ec78a8', '#ffaed0', '#ffd8e8', '#fff4f8'),
    # title screen
    'logo': hx('#4a0a36', '#8e1a56', '#d23e82', '#f86aa8', '#ff96c4', '#ffc2dc', '#ffe8f2', '#ffffff'),
    'logo2': hx('#5a2a06', '#a0520c', '#e08a16', '#f8b42a', '#ffd448', '#ffe88a', '#fff6cc', '#ffffff'),
    'text': hx('#3a0830', '#561046', '#741c5c', '#943070', '#b84a8a'),
}

# Status bar: light pink panel, berry lettering with a soft pink shadow, yellow
# health pips, a pink Kirby lives icon. Icons are window tile numbers.
HUD_STYLE = {
    'panel': ('#fff2f8', '#ffe8f2', '#ffdeec', '#ffd4e6', '#ffcae0', '#ffc0da'),
    'edge': '#f4a6c8',
    'text': ('#c43c7c', '#9c1e5c', '#7c1048'),
    'shadow': '#f2b0cc',
    'icons': {0x68: 'health', 0x6e: 'health_empty', 0x67: 'kirby',
              0x69: 'boss_health', 0x6a: 'boss'},     # (a boss's health and icon)
}
CLEAN_GRASS = True   # the foreground foliage band, drawn clean
LEDGE_FROM_LINE = True   # ledge tiles are ground from their line down (domes stand on them)


def _k(code, *hexes):
    for h in hexes:
        TILE_KEYS[int(h, 16)] = code


TILE_KEYS = {}
# ---- Green Greens (first area) ----
_k('Y', 'b77a35')                                          # open sky
_k('E', '2943e3', '0c913b', '182a35', '2ae841', 'd76da9')  # dotted ground body, its cliff sides
_k('L', '6df7e2', '96415c', '5fa707', '6a2523')    # grassy top edges and corners
_k('E', '9fd36c')    # a ground block's side (also its top corner)
_k('G', '42f6ee', 'f62142', '77323a', 'c7d3c7', '69efb2',  # grass tufts and round flowers,
   '7316ab', 'fab5f0', '35dc1f', '3d6082', '473e45', '7a0b52')   # also standing on the ground
_k('K', '73fca6', '268420', '506a64', '735685',            # cobbled cliff face
   '6d2bd7', 'b8e15a', '6eb939')
_k('Z', '91e532', 'c2cc69', 'dc80d2', '279c1b', '5435d0',  # clouds
   '82a6f8', 'c20b4a', 'f9844b', 'f72f32', '29e336', 'da535f', '9e43af')
_k('h', 'b4c507', '7f0ec8', '5d8d11', 'a271b5', 'e35cb5',  # outline hills and arches
   '3da09a', '3a38bc', 'd6f0fc', '7adab7', 'd7d382', '03109f', 'd50847',
   'a315bd', '1d2856', 'a44b6b', '539833', '198899', '05f81e')

# ---- Green Greens, the forest (after the mini-boss) ----
_k('T', '4f8671', '278720', '8ad907', 'dd3d22', 'f582bd', 'b66c6d', '85205c', '6e8947',  # canopy
   '46c4d4', 'e78c74', 'fadab9', '8dcbca', 'c20b70', '879012', '979d13')
_k('T', 'f198e7')                                          # the dark forest behind the trunks
_k('V', 'e2d3ef', 'c48c1c')                                # trunk sides
_k('G', 'c4b78e')                                          # grass against the dark
_k('Q', 'e05657', '5dc9b0', '4b5cbb', '67a250')            # star blocks

# ---- Castle Lololo (stage 2) ----
_k('H', 'f0f4b9', 'c88bd7', '072e16', '2aff78', 'c359e4', '6848f4', '6e6855', '255ed4',   # bricks
   '1c4623', 'd9465f', '388a23', 'e8e0fd', '248824', '906886', '6e40ec')
_k('K', 'a63d53', '20329d')                                # rough stone pillars
_k('E', 'd2cafa', '4da3df')                                # the ground before the castle
_k('Z', '880190', '271059', '4dc2ee', 'cc6509', '6d17f7')  # curly clouds
_k('R', '6c1721', 'a72dd3', 'e030df', '5179f5', '366587')  # far mountains (as 'roof': the sky fill reaches their white)
_k('O', '9b6a40', '9b4c92', '99bbd1', 'd9ed10', '0a97dd', 'd65150')   # dotted platforms
_k('M', 'a7f27d', 'a7d192', 'e4d12b', '8c8829')            # balustrades, the frieze

# Labels that differ per stage (the same tile can be a forest canopy in Green
# Greens and a mountain's body at Castle Lololo): stage (D03B) -> {hash: code}
STAGE_TILE_KEYS = {1: {int('4f8671', 16): 'R',      # the solid shade: mountain body
                       **{int(h, 16): 'H' for h in ('6cac2b', '4fec53')}}}   # (door arches: in the wall)
# ... and per area: (stage, area) -> {hash: code}.
def _keys(code, *hexes):
    return {int(h, 16): code for h in hexes}


# Castle Lololo's rooms share one set of pieces (the same tiles make marble
# diamonds, striped wallpaper and a woven lattice): labelled for the whole stage.
STAGE_TILE_KEYS[1].update({
    **_keys('D', '5d0bed', 'de7c5e', '5805c7', '262bb4', '7043d8', '7773fa', '5ce987', 'dd1093'),   # garlands
    **_keys('S', '78b615', 'c3ea24', '3af699', '8002ee', 'e4bc99', 'dd3a2e',   # marble, stripes
            'f56ccf', '5ca7e1'),
    **_keys('V', '0980ac', 'f25822', 'cf113e', 'f57f7f', '14464d', '556018',   # columns
            '575615', '7d7df6', '86fcbd', '139680'),
    **_keys('M', 'ee2773', '077b3f',                              # stone beams, lattice strips
            '5e8c7e', 'c51b8d',                                   # a panel's frame
            'be208b', '211969', '019879'),                        # the gallery's shaded band
    **_keys('O', 'b7041b', 'bc9c7a'),                             # small ledges
    **_keys('Q', '87f222', 'df4523', 'ec680c', '0e3096'),         # ? blocks
    # the flooded rooms: wave lines and bubbles (water), the turrets standing in it
    **_keys('W', 'abffe5', 'af59b8', '8d9275', 'bf1f71', '1a563d'),
    **_keys('K', 'e059c3', '1a5bc6', 'b5cfd4', 'a881ac'),
})
# Float Islands (stage 2): islands on a tropical sea
STAGE_TILE_KEYS[2] = {
    **_keys('E', 'e2d925', '652b3d', '1682a8', '892873', 'a7076b', 'ed72d9'),   # island slabs (ground: not ledges, their line is below)
    **_keys('K', 'ae4602', '6342eb', 'dfee26', '89258e', '2ad33e', '0cb463',    # dark rock under them
            'c280f9', '0161d1', '88b2c5', 'b3ca1c'),                            # (and the hut's door arch)
    **_keys('V', '25a41f', 'd93e98'),                                             # palm trunks
    **_keys('T', '3c0a76', 'e1ba7a', '1cf62b', '0da6ce', '793db1', '381aa3',    # palm fronds
            '4e0bd8', '6c9165', '849f40', 'd4b46a', '92c7c5', 'b9765d', '32049e'),
    **_keys('Z', 'c9f936', '014fb4', '13d915', '9ec8c0', '0626eb', 'b62f12',    # cloud outlines, bubbles
            '1911d9', '6d03bf', '5d347d', '18b810', '1423e8', '3058cd'),
    **_keys('W', '825809', 'd49c6b', '87cee2', 'e29982'),                        # the sea, its wave crests
    **_keys('Y', '570245'),                                                      # the horizon's haze
    **_keys('Q', '7e600c', '428d2f', '110a8a', '117c36'),                        # star blocks
    # the cave: dotted rock with white rims, stalactites, columns, plank ledges
    **_keys('K', '7c1976', '6963f5', '30a30e', 'b59b54', '962dfa', 'c7ca5e', '551da2', 'f12cbb', 'cdc7d3', 'c57e31', '1eddb7',
            'b2dd93', '152b96', 'c191fd', 'f2e1d3', '8d07d5', '68ca51', 'cd62cf'),
    **_keys('O', '6e0da9', 'ca657e', 'b1622e'),
    # the ship and the wooden tower: hull and wall planks, rails and posts,
    # rigging (rope: the white between stays sky), the mast
    **_keys('F', '4ac3b1', 'ffbdce', 'fd7b02', '710145'),
    **_keys('W', '20196f', 'e1e2ed'),            # the waves along the ship's side
    **_keys('O', '176468', '60fb60', '5eb2b0', '260568', 'cf6676'),
    **_keys('R', '40b31e', 'd40f5b'),
    **_keys('V', '6fcf44'),
    # above the clouds (Kaboola's sky): cloud platforms, striped pillars
    **_keys('M', '454915', 'b68b18', '4b838a', 'a20cb5', 'd1d13a', 'edc0ef'),
    **_keys('P', '19dea5', '6b7845', '2af261', '3ee68d'),
}
# Bubbly Clouds (stage 3): the sky is the solid grey tile and the white is
# cloud (the other way round from the stages before); post_solve sorts them out
STAGE_TILE_KEYS[3] = {
    **_keys('Y', '4f8671'),                                                      # open sky
    # cloud outlines, dithered cloud edges, bubbles, cloud platforms' rims
    **_keys('Z', '66a83c', 'ce47aa', 'eaf281', 'f84eea', '946d7f', '8f3924', '3f30d3', 'a02a1f',
            '624ed5', '655764', '95d00a', 'c36951', '838c33', '9b65eb', '7e6f77', 'dba4b9',
            '3f3b5d', 'ac1b7a', '992308', '9bef37', '29c590', '48a1a6', '0ba913', '616e6d',
            '81bebf', '3fcb4f', '481303', '6b09cf', '68135e', '7fcfb8', '276eca', '727bcf',
            'b52f33', '25fffd', 'aae04c', 'e10be2', 'e8c25a', '02342b', '9e1048', '011a78',
            '5e8a3e', '7fa987'),
    # the temple: columns, balustrades, its frieze and walls, the floor along it
    **_keys('V', 'e68c88', '4fd744', '5809d8', '6cac77', 'dcfe42', '21f0a0', '7103e1', '2cc1cf', 'bde658'),
    **_keys('M', 'ee6bbb', '1a4aa7', '558e8a', 'd67120', 'fc50f3', '1986e3'),
    **_keys('S', '15cdcb', 'a9ac55', 'bfb141'),
    **_keys('F', 'd59bec', '2472a5', 'c36cce', 'ae20d4', 'b437ca'),
    # inside (areas 1, 2): friezes and balustrades, a capital, framed blocks, spikes
    **_keys('M', '77849a', '192a31', '9a65ec', 'bb510a', '3efc11', 'fd8ac1', '6e3a17', 'dd231a',
            'e29982'),
    **_keys('S', '12a131', '195f08'),       # spikes: on the wall (paint_tiles draws them in metal)
    **_keys('V', '1f2840'),
    **_keys('Q', '41fea7', '8fb839', 'c61edd', '0dd4da'),
    **_keys('S', 'bcbacd'),
    **_keys('Z', 'ee2564', 'ff717e'),
}
# Mt. DeDeDe (stage 4): King DeDeDe's castle, indoors throughout: a parquet
# wall, striped stone ceilings and floors, portraits, the bosses' doors
STAGE_TILE_KEYS[4] = {
    **_keys('S', '7a19f7', '05cc8b', 'a514bb', '676e6c'),                        # the parquet wall
    **_keys('H', 'dab5f0', 'bb5c52', 'a380bb', 'c0d645', 'aa507e', '122a79',     # striped stone, its edges
            '9544be', '8081d1', '75ae98'),
    # King DeDeDe's portraits: painted in his royal red
    **_keys('C', '1682e8', '933b96', 'd3fed3', 'd940b7', 'dda7c4', '246224', '0b8b40', '145f5e',
            'c33c1f', '2f5870', '2c4b2b', '3776de', '69c8c1', '455a13', '511f31', 'dfe2e5'),
    # a beaten boss's door: boarded up, a CLOSED board across it
    **_keys('O', '32d622', '777131', 'f384ff', 'a8ba09', '514c2c', '6b1fb9', '10ddc3', 'c40cdc',
            'ed677d', '277d2e', '2db8d4', '3d6570'),
    # King DeDeDe's ring (area 5): its white wall, dark vaulted corners, posts, ropes
    **_keys('S', 'b77a35'),
    **_keys('H', 'f198e7', '6adbba', '522926'),
    **_keys('V', 'e0cb0b', 'fa37b9', '92995e', '651004', '21317c', 'c70ed2', 'e31f93', 'ba2827',
            'baaac7', 'f931ef'),
    **_keys('M', '36e5a2'),
    # the bosses' doors: carved wood, each with its boss's picture, and the floor at their feet
    **_keys('O',
            '011e63', '059ec5', '07c988', '084b98', '17b8e8', '1a6aa0', '1ebd7b', '2060a3',
            '25e43f', '277b5e', '33fbab', '3410c3', '382572', '3b612e', '442202', '4af404',
            '4ec01e', '5445b2', '5d888d', '5eed88', '6078fd', '6e076d', '737366', '740bdb',
            '743d06', '78c9b9', '8d660c', '974c53', '986a74', '9aadf9', '9cdff9', 'a3ca50',
            'a5d871', 'b6f80a', 'c0dd25', 'cad3c0', 'd30a0f', 'd79490', 'd8f85f', 'd9fe40',
            'dd6f7d', 'deb424', 'df6f81', 'f407ad', 'f572a9', 'fa7d4d', 'fb5250'),
}
# The ending: the solid grey is the sky (white: clouds, the sun, the credits'
# band, the Extra Game page; paint_tiles keeps it white)
STAGE_TILE_KEYS[5] = {**{h: c for h, c in STAGE_TILE_KEYS[3].items() if c in 'YZ'},   # (Bubbly Clouds' sky, cloud edges)
                      # the credits' mountains, their snowy ridge
                      **_keys('R', 'f198e7', '25b205', '091084', 'd9e70f', '6cb44b', 'e6ae1e', 'f5cf5d', '38be2e',
                              'eecacf', 'ce1c1a', 'f25bae', '127a75', 'a0d1df', '6b6d4d', '070fb9', '0c539a', '6ed3fe'),
                      **_keys('Y', '211969', '77fffa', '05c87f'),      # the dithered bands of the sky
                      **_keys('X', 'ee4fac', 'd7f368', 'f75bc9', 'aedbd1', 'bd01cb', '8996b5', '59db29'),   # the credits' letters
                      # King DeDeDe's ring as it fades out (its own labels, but not its wall's white)
                      **{h: c for h, c in STAGE_TILE_KEYS[4].items() if h != int('b77a35', 16)},
                      # the castle carried off by the balloon ('S'), the balloon, its ropes, the
                      # grass strip ('Z': their grey is the sky), the credits' last trees ('R'),
                      # the box under "bye-bye" ('O'), the dark bumps ('H'), the Extra Game
                      # page's letters ('X') and its Game Boy drawing ('M')
                      **_keys('Z',
                              '7202d7', '869dfb', '28166a', '45da44', '7516e8', 'e81dbf', 'c2202a', 'ffc5d0', '3885f3', '47478b',
                              'fc33f3', '255d96', '8c27ae', '5a4c51', 'ea80a9', '6d6750', '726379', '5ded26', 'dfee51', 'bfcd46',
                              'd4b822', '40bbe7', '07d20c', '33725f', 'b84341', 'f0b765', 'd96006', '96ecf3', '406c9f', 'c44fe2',
                              'd65c9b', '4ed63b', '8cba02', '812ace', '74d17e', '01ca4c', 'fc44ec', 'f45ddd', 'a7b5a4', '9f7170',
                              'eb50bb', 'f3d402', 'f8dfb4', '35b7a8', 'f903f5', '53fedd', '5602d8', '46e28a', 'ce1ba9', 'b3caa1',
                              'c5b0ee', 'b983e5', 'c00ff8', '5d4b25', '2a88da', '40bcab', '200053', 'de3e68', 'cefa79', 'b95c88',
                              '333daf', '00edda', 'eb9d98', 'dcb1b1', 'da78ab', 'c2d234', '0272f3', 'ef03d2', '028112', 'ff56ba',
                              '5fb82b'),
                      **_keys('S',
                              'c9e370', 'afd2c3', '903067', 'a2dff8', 'ea4eac', '5ca24e', '2508f9', '345db2'),
                      **_keys('X',
                              '9a0eaa', 'cea877', '84a147', '831bf9', 'aa9864', '4d9742', '9667dd', '70a391', '5d540e', 'd078ec',
                              'be0a1d', '4c7aab', '23edfc', '726ca5', '1cd637', 'b92039', '10db0a', 'd7d375', '3f64d6', 'bb462f',
                              '0beff3', '9cb62d', 'f0f250', 'ebe610', '439950', '43770b', 'ab2962', '994b05', '061c2f', '87f323',
                              'acae0a', 'ddc472', '4a4120', '89e080', 'b5785c', '592307', '81b426', 'cc41c0', '70c12a', 'd38726',
                              '37d999', '455b8f', 'e89003', '0d3cc2', '473131', 'd5a492', 'f79092', 'ef7aac', 'db2e7b', '6ffcd0',
                              '608ce8', '86be58', '49e9bf', '9504a3', '165f82', '57c9b9', '7f8de4', '1de3e2', '488438'),
                      **_keys('R',
                              'eceadd', '244aab', 'b8f6e2', '25ff9a', 'c7761d', 'cb0384'),
                      **_keys('O',
                              '06ca25', '755fa0', 'f07f94'),
                      **_keys('H',
                              'a487c8', '4923a2', 'aac2de', '360014', 'b422f2', 'd7dc90'),
                      **_keys('M',
                              '1962bc', '817cb0', '2bbe86', '2e4a2a', '379d3a', 'de033a', '1b6316', '9257b1', '54b34f', 'ded218',
                              '5ee594', '82eca1', '32b4c9', '23d8ec', '743175', '63e71c', '66536e', '7f9092', 'd0c60d', '553da7',
                              '602fbf', '162e09', 'ba18da', 'b0aa84', 'ca819d', '07603c', '79c176', '92189d', '9aec13', '544772',
                              '114a6d', '1e1516', '6ee1bb', '1213db', '1a20fa', '6fd16c', '000716', '598c7f', '5217c8', 'b4ef82',
                              'f64908', '931f1d', '47a849', '0312fa', '4b78fd', '77798b', '66cf0d', 'fc1c4a', 'c9c442', '172fe3',
                              '4215bd', 'a19102', '7dd7cc', '7959cc', 'd97aff', 'a6c7ac', '1edd8b', '83911e', '5509a5'),
                      }
STAGE_TILE_KEYS[5].update(_keys('M', 'b983e5', 'c00ff8', '5d4b25', '200053', 'de3e68', 'cefa79', 'b95c88',   # the castle
                                  '333daf', '00edda', 'eb9d98', 'dcb1b1', 'c2d234', '0272f3', 'ef03d2', '028112'))  # in the balloon's basket
STAGE_TILE_KEYS[5].update(_keys('H', 'e97642', 'e22437', '0c62b9', '09549c', '4b85bf', 'c5bb5f'))   # (the bumps as they fade in)
ENDING_DITHER = [h for h, c in STAGE_TILE_KEYS[5].items() if c == 'Z']
# the "balloon" is Kirby himself, puffed up, carrying the castle off: pink
KIRBY_BALLOON = [int(h, 16) for h in (
    '28166a', '45da44', '7516e8', 'e81dbf', 'c2202a', 'ffc5d0', '3885f3', '47478b', 'fc33f3', '255d96',
    '8c27ae', '5a4c51', 'ea80a9', '6d6750', '726379', '5ded26', 'dfee51', 'bfcd46', 'd4b822', '40bbe7',
    '07d20c', '33725f', 'b84341', 'f0b765', 'd96006', '96ecf3', '406c9f', 'c44fe2', 'd65c9b', '4ed63b',
    '8cba02', '812ace', '74d17e', '01ca4c', 'fc44ec', 'f45ddd', 'a7b5a4', '9f7170', 'eb50bb', 'f3d402',
    'f8dfb4', '35b7a8', 'f903f5', '53fedd', '5602d8', '46e28a', 'ce1ba9', 'b3caa1', 'c5b0ee', 'b983e5',
    'c00ff8', '5d4b25', '2a88da', '40bcab', '200053', 'de3e68', 'cefa79', 'b95c88', '333daf', '00edda',
    'eb9d98', 'dcb1b1', 'da78ab', 'c2d234', '0272f3', 'ef03d2', '028112', 'ff56ba'
)]
_BASKET = [int(h, 16) for h in ('b983e5', 'c00ff8', '5d4b25', '200053', 'de3e68', 'cefa79', 'b95c88', '333daf',
                                '00edda', 'eb9d98', 'dcb1b1', 'c2d234', '0272f3', 'ef03d2', '028112',
                                '2a88da', '40bcab', 'da78ab', 'ff56ba')]     # (the castle he carries)
KIRBY_BALLOON = [h for h in KIRBY_BALLOON if h not in _BASKET]
ENDING_LAND = [h for h, c in STAGE_TILE_KEYS[5].items() if c == 'R']
# Bubbly Clouds: tiles whose grey is the open sky seen through them
SPIKE_TILES = [int(h, 16) for h in ('12a131', '195f08')]
# the starry sky (area 5): stars on the black of space, the dithered dusk band
STAR_TILES = [int(h, 16) for h in ('41ab5e', 'a132b3', '41ae54', 'b67899', '08d1df', '6c7f65')]
DUSK_TILES = [int('10e581', 16)]
# (labelled, so the generic pass skips them: paint_tiles repaints every pixel
# of space, the stars and the dusk band in the starry areas, and a doorway's
# black elsewhere on this stage)
STAGE_TILE_KEYS[3].update({h: 'K' for h in STAR_TILES + DUSK_TILES + [int('c5bb5f', 16)]})   # ('K': the sky fill leaves it alone)
# the curtains (areas 4, 7): drapes of the same striped tiles as the columns,
# told apart by hanging above their rope swags (post_solve: kind 13 cloth,
# kind 14 the gold rope)
ROPE_TILES = [int(h, 16) for h in ('512168', 'e22411', 'c20170', '4517fb', '28eb58', '19ddbc')]
DRAPE_TILES = [int(h, 16) for h in ('1f2840', 'e68c88', '192a31', 'b77a35')] + ROPE_TILES
MOON_TILES = [int(h, 16) for h in ('4fec53', '6da226')]     # (area 7; elsewhere a door's arch)
BALUSTRADE_TILES = [int(h, 16) for h in ('ee6bbb', '1a4aa7', '558e8a', 'd67120', 'fc50f3', '1986e3')]
WAVE_TILES = [int(h, 16) for h in ('d49c6b', '87cee2',      # the sea's wave crests,
                                    'af59b8', '8d9275', 'bf1f71', '1a563d',    # Castle Lololo's,
                                    '20196f', 'e1e2ed')]                        # along the ship
# the ship's hull planks: the same tile is the sea's dotted water below the
# waves along its side (post_solve makes those tiles water, kind 12)
SEA_FILL = [int('4ac3b1', 16)]
FLOAT_PLATFORM_TILES = [int(h, 16) for h in ('454915', 'b68b18', '4b838a', 'a20cb5', 'd1d13a', 'edc0ef')]   # Kaboola's cloud platforms
SHIP_WAVES = [int(h, 16) for h in ('20196f', 'e1e2ed')]
# cave tiles whose black is the cave's far wall seen through them (between
# stalactites, beside a rock edge), not an outline: painted as the wall
CAVE_VOID_TILES = [int(h, 16) for h in ('6963f5', '30a30e', 'cdc7d3', 'c57e31', 'f12cbb', 'f2e1d3', '68ca51')]
SEA_AREAS = {0, 5, 6}
DEDEDE_SEA_AREAS = {3}    # (Mt. DeDeDe's areas on Kaboola's route with the sea's horizon)     # Float Islands areas with the sea's horizon (the rest: sky only)
HORIZON_TILES = [int('570245', 16)]     # Float Islands: the haze along the sea's horizon


def _under_lines(region, line):
    """Per region of `region`: pixels with a line just above them, and just below."""
    from scipy import ndimage as ndi
    lab, n = ndi.label(region)
    under = np.zeros_like(region)
    over = np.zeros_like(region)
    for d in (1, 2):
        under[d:] |= line[:-d]
        over[:-d] |= line[d:]
    idx = np.arange(1, n + 1)
    return (lab, ndi.sum(under & region, lab, idx), ndi.sum(over & region, lab, idx),
            ndi.sum(region, lab, idx))


def _underwater(kind, at, mat, M):
    """White lying under the sea's wave crests is water (kind 12, painted by
    paint_tiles), not open sky: the shafts of Float Islands."""
    crest = np.repeat(np.repeat(np.isin(at.hashes, WAVE_TILES), 8, 0), 8, 1) & (at.shade >= 1)
    if not crest.any():
        return kind
    lab, nu, no, size = _under_lines(kind == 1, crest)
    water = np.concatenate([[False], (nu > 2 * no) & (nu >= 8)])
    kind = kind.copy()
    kind[water[lab] & (kind == 1)] = 12
    # tiles of the sea's dotted water below the ship's waves: all water
    wave = np.isin(at.hashes, SHIP_WAVES)
    if wave.any():
        below = np.maximum.accumulate(wave, axis=0) & ~wave & np.isin(at.hashes, SEA_FILL)
        kind[np.repeat(np.repeat(below, 8, 0), 8, 1)] = 12
    return kind


def _bubbly(kind, at, mat, M):
    """Bubbly Clouds: white is cloud; grey reaching the solid sky tile through
    cloud and balustrade tiles is open sky (kind 1)."""
    from scipy import ndimage as ndi
    if (mat == M['Y']).any() and np.isin(at.hashes, [int('4f8671', 16)]).any():
        kind = np.where(kind == 1, 2, kind)    # (where the grey sky is seen at all)
    kind = np.where(kind == 6, 1, kind)   # (no tree trunks either: white between columns is sky)
    kind = np.where(kind == 7, 0, kind)   # (outlines: the tiles' own shades, bold on the platforms)
    hill = (kind == 3) | (kind == 5)      # (no hills up here: cloud where white, else sky)
    kind = np.where(hill, np.where(at.shade == 0, 2, 1), kind)
    open_t = np.isin(at.hashes, BALUSTRADE_TILES) | (mat[::8, ::8] == M['Z']) | (mat[::8, ::8] == M['Y'])
    grey = np.repeat(np.repeat(open_t, 8, 0), 8, 1) & (at.shade == 1)
    lab, n = ndi.label(grey)
    if n:
        seed = np.repeat(np.repeat(mat[::8, ::8] == M['Y'], 8, 0), 8, 1) & grey
        has = np.zeros(n + 1, bool)
        has[np.unique(lab[seed])] = True
        has[0] = False
        kind[has[lab]] = 1
    dusk = np.repeat(np.repeat(np.isin(at.hashes, DUSK_TILES), 8, 0), 8, 1)
    if dusk.any():      # open sky above where night meets day is night (kind 15)
        night = np.flipud(np.maximum.accumulate(np.flipud(dusk), axis=0)) & ~dusk
        kind[night & (kind == 1)] = 15
    rope_t = np.isin(at.hashes, ROPE_TILES)
    if rope_t.any():
        up8 = lambda t: np.repeat(np.repeat(t, 8, 0), 8, 1)
        line = up8(rope_t) & (at.shade >= 2)
        cand = up8(np.isin(at.hashes, DRAPE_TILES))
        cloth = np.zeros_like(line)
        below = np.zeros(line.shape[1], bool)
        for y in range(line.shape[0] - 1, -1, -1):    # upward: above a rope, through drape tiles
            cloth[y] = below & cand[y] & ~line[y]
            below = (below | line[y]) & cand[y]
        kind[cloth] = 13
        kind[line] = 14
    return kind


def _door_trees(kind, at, mat, M):
    """A door standing in open sky between two trunk edges ('V') is in a
    hollow tree (Whispy's route on Mt. DeDeDe): the sky around it, between the
    trunks, is the trunk (kind 6)."""
    from scipy import ndimage as ndi
    door = np.isin(at.hashes, ROOM_TILES)
    if not door.any():
        return kind
    vt = mat[::8, ::8] == M['V']
    sky = (kind == 1) | (kind == 3) | (kind == 5)    # (or read as a hill, captured from further off)
    lab, n = ndi.label(sky)
    for r, c in zip(*np.nonzero(door)):
        lv = [x for x in range(c - 1, max(c - 9, -1), -1) if vt[r, x]]
        rv = [x for x in range(c + 1, min(c + 9, vt.shape[1])) if vt[r, x]]
        if not lv or not rv:
            continue
        x0, x1 = lv[0] * 8 + 8, rv[0] * 8
        band = np.zeros_like(sky)
        band[:, x0:x1] = True
        near = lab[max(r * 8 - 2, 0):r * 8 + 10, max(c * 8 - 2, 0):c * 8 + 10]
        for i in np.unique(near[near > 0]):
            kind[(lab == i) & band] = 6
        # small pockets of sky just beside the trunk (a branch stub's hollow) join it
        trunk = np.zeros_like(sky)
        trunk[:, max(x0 - 12, 0):x1 + 12] = True
        sizes = ndi.sum(sky, lab, np.arange(1, n + 1))
        for i in np.unique(lab[trunk & sky & (kind != 6)]):
            if i and sizes[i - 1] <= 200:
                kind[lab == i] = 6
    return kind


def _forest_shade(kind, at, mat, M):
    """Green Greens' look: holes in the foliage are leaves in shadow (kind 16),
    not sky: white in the canopy tiles with foliage just above it (the wedges
    along the canopy's underside), and small pockets closed off under it. The
    open white between the trunks stays sky, as in the original."""
    from scipy import ndimage as ndi
    canopy = mat == M['T']
    if not canopy.any():
        return kind
    kind = kind.copy()
    # the solid dark band under the canopy and the dark background trunks below
    # it (blue in the original): open sky, with the dark pixels joined to them
    # in the edge tiles
    dark = canopy & (at.shade == 2)
    solid = dark.reshape(dark.shape[0] // 8, 8, dark.shape[1] // 8, 8).all(axis=(1, 3))
    if solid.any():
        # (the band right under the foliage stays; a solid dark tile with open
        # white within two tiles beside it is a background trunk in the air)
        blank = (at.shade == 0).reshape(solid.shape[0], 8, solid.shape[1], 8).all(axis=(1, 3))
        near = np.zeros_like(blank)
        for d in (1, 2):
            near[:, d:] |= blank[:, :-d]
            near[:, :-d] |= blank[:, d:]
        trunk_t = solid & near
        trunk = np.repeat(np.repeat(trunk_t, 8, 0), 8, 1)
        kind[trunk] = 1
        canopy = canopy & ~trunk
    white = at.shade == 0
    leaf = canopy & ~white
    above = np.zeros_like(leaf)
    for d in range(1, 7):                 # foliage within 6 px above
        above[d:] |= leaf[:-d]
    kind[canopy & white & above & ((kind == 0) | (kind == 1))] = 16
    under = np.maximum.accumulate(canopy, axis=0) & ~canopy
    lab, n = ndi.label((kind == 1) & under)
    if n:
        sizes = ndi.sum(np.ones_like(lab), lab, np.arange(1, n + 1))
        outside = (kind == 1) & ~under
        near_out = ndi.binary_dilation(outside)
        open_ = np.zeros(n + 1, bool)
        open_[np.unique(lab[near_out & (lab > 0)])] = True
        small = np.concatenate([[False], sizes <= 96])
        kind[small[lab] & ~open_[lab]] = 16
    return kind


def post_solve(kind, at, mat, M):
    """After ugb.lineart has solved an area (Float Islands): water under the
    wave crests, and the cloud banks. Those are drawn as outlines only, are
    cut by the area's edges and reach down to the horizon, so they come out
    as open sky. Cut the white apart at the horizon's haze; above it, a region
    lying mostly under cloud outlines (a cloud's top arches over its body) is
    a cloud bank, one lying mostly over them is sky. There are no outlined
    hills here: those readings are clouds too."""
    tk = getattr(at, 'tile_keys', None) or {}
    if tk.get(int('7a19f7', 16)) == 'S':      # Mt. DeDeDe: indoors, no sky anywhere
        return np.where((kind == 1) | (kind == 2) | (kind == 3) | (kind == 5) | (kind == 6), 0, kind)
    if tk.get(int('4f8671', 16)) == 'Y':
        return _bubbly(kind, at, mat, M)
    kind = _underwater(kind, at, mat, M)
    kind = _door_trees(kind, at, mat, M)
    # (Green Greens' forest: no extra rule. Under the canopy its dark blue is
    # foliage and its white is sky, as drawn: fills tried here, of the space
    # between the trunks, the wedges along the underside and the background
    # trunks, each covered part of what the original shows open)
    if int('825809', 16) not in (getattr(at, 'tile_keys', None) or {}):
        return kind                  # (not Float Islands)
    kind = np.where(kind == 3, 2, kind)
    kind = np.where(kind == 6, 1, kind)     # (nor tree trunks: white between palm trunks is sky)
    sky = kind == 1
    hz = np.isin(at.hashes, HORIZON_TILES)
    if hz.any():
        sky[np.where(hz.any(1))[0].min() * 8:] = False
    lab, nu, no, size = _under_lines(sky, (mat == M['Z']) & (at.shade >= 2))
    cloud = np.concatenate([[False], (nu > 2 * no) & (nu >= 20) & (size >= 200)])
    kind[cloud[lab] & sky] = 2
    kind[(mat == M['M']) & (at.shade == 0) & (kind == 1)] = 2    # (Kaboola's cloud platforms: cloud, not sky)
    # the white inside palm frond tiles goes with the cloud behind it, where it touches one
    from scipy import ndimage as ndi
    leafy = (mat == M['T']) & (at.shade == 0) & (kind == 0)
    lab2, n2 = ndi.label(leafy | (kind == 2))
    if n2:
        has = np.zeros(n2 + 1, bool)
        has[np.unique(lab2[kind == 2])] = True
        has[0] = False
        kind[leafy & has[lab2]] = 2
    return kind


# The rooms with no open sky anywhere: there the blank white is plaster (open
# sky everywhere else), and so is the white inside the big arches.
INDOORS = {(1, 4), (1, 8), (1, 9), (1, 10), (1, 12), (1, 14)}
_PLASTER = _keys('D', 'b77a35', 'a9400c', '352dc3', '6611f7', '53b6d8', '279eb2', '4c6b3a')
_PLASTER.update(_keys('F', 'd2cafa', '4da3df'))     # (the dotted ground outside: a wooden floor in here)
AREA_TILE_KEYS = {k: _PLASTER for k in INDOORS}
# (the blank white is also the middle of each white diamond: there it is marble)
TILE_FOLLOWS = {'D': 'S'}
NO_EAVES = 'DSM'     # (plaster, marble and stone trim keep their white next to a floor)
_STAGE_KEYS = {}


# Mt. DeDeDe's doors lead back into the earlier stages (a boss rush): those
# areas keep the play mode of their home stage, which tells their look apart.
# The hall (area 0) keeps the mode of the last boss's route, so it and King
# DeDeDe's ring (area 5) stay Mt. DeDeDe's own.
MODE_STAGE = {0x0D: 0, 0x10: 1, 0x0E: 2, 0x0F: 3}
DEDEDE_OWN_AREAS = (0, 5)


ENDING = 5      # look_stage of the ending (after King DeDeDe): a look of its own


def look_stage(m):
    """The stage whose look an area has: its own, or on Mt. DeDeDe, the stage
    its boss's route comes from (ENDING for the ending)."""
    st = m[0xD03B]
    if st == 4 and m[0xD03C] == 0x11 and m[RAM['area']] == 5 and m[0xD160] == 0:
        return ENDING
    if st == 4 and m[RAM['area']] not in DEDEDE_OWN_AREAS:
        return MODE_STAGE.get(m[0xD03C], 4)
    return st


def has_status_bar(f):
    """No status bar on the credits (ugb.render): their bands scroll apart
    from the rest and would read as one."""
    if look_stage(f.ram) != ENDING:
        return True
    return not (f.line_maps() != f.bg_map()).any()   # (the credits; the ring fading out keeps its bar)


def tile_keys_for(m):
    """TILE_KEYS with the current stage's and area's own labels over them
    (ugb.render, ugb.lineart)."""
    st = (look_stage(m), m[0xD03B], m[RAM['area']])
    if st not in _STAGE_KEYS:
        _STAGE_KEYS[st] = {**TILE_KEYS, **STAGE_TILE_KEYS.get(st[0], {}), **AREA_TILE_KEYS.get(st[1:], {})}
    return _STAGE_KEYS[st]

# ---- rooms behind doors ----
_k('F', '92cf09', 'fca2ba', '510ae4', '4dfb68', 'd8f6a9', '38a5eb')   # the carved floor beam
_k('O', '4b7527', 'c63199')                                # a floating plank
_k('V', '464a43', '9f713f')                                # carved columns inside the tree
_k('P', 'e1c563', '319407', '81c199')                      # Whispy Woods' nose
_k('L', '1872a0', 'c9560e')                                # grassy edges seen below the tree's floor
_k('E', '8c0190', '86e646')
# The black of a room's back wall (also a doorway outdoors: ugb.lineart tells
# them apart by size) and the doorway's arch, painted by paint_tiles below
ROOM_TILES = [int(h, 16) for h in ('c5bb5f', '73782b', '935a9d', '6cac2b', '4fec53', '6f242a', 'b019a1')]
_PLANK = [int('4b7527', 16), int('c63199', 16)]
# door arches (outside and in rooms): ugb.atlas keeps a snapshot in front of each,
# and the area behind is captured before the player gets there
DOOR_TILES = [int(h, 16) for h in ('73782b', '935a9d', '6cac2b', '4fec53', '88b2c5', 'b3ca1c',
                                    '6f242a', 'b019a1')]
SWEEP['door_tiles'] = DOOR_TILES
SWEEP['each_frame'] = _keep_alive
SWEEP['tile_keys'] = lambda m: tile_keys_for(m)

# ---- title screen ----
_k('J',  # the logo (and the title's small decorations)
   '03e82e', '0405fb', '0740c4', '076698', '0bced3', '0f865e', '10d924', '130bc6',
   '1349ae', '13ba15', '1481f5', '153d23', '161334', '16d925', '18604a', '194619',
   '1a43f0', '1b0da3', '1b8f1b', '1c54cf', '1c8062', '1d5f30', '1dd483', '1e459e',
   '1e4988', '1e6bfe', '1ea832', '1f0366', '1fecbc', '21265f', '24fd70', '256d2b',
   '2a6b74', '2a8a6d', '2de3f5', '2eead6', '32be2e', '32faa7', '3300ee', '332f35',
   '33ed91', '341ed5', '3440d9', '34c087', '366753', '36de72', '38fcf4', '390391',
   '3996a9', '39b87a', '3a48c7', '3bc815', '3c8580', '3d65ff', '3de2cb', '3ec959',
   '3f472c', '41a7ce', '42a223', '4377d1', '44c8f4', '452866', '479645', '49e0e8',
   '4abc9c', '4ae5a7', '4ece6a', '511d65', '52f51c', '5615c6', '570bc9', '5e68b1',
   '5f0b09', '60a5d9', '6537c6', '665a12', '666c0c', '6c1387', '6c2090', '6e95b2',
   '6f0eed', '71bff2', '7492ca', '75a41e', '76632f', '770ac2', '789efc', '79614b',
   '7bb691', '7bbd69', '7bf640', '7c7388', '7ea06e', '808fd0', '83977a', '862f2c',
   '863877', '874966', '875fbf', '876b4f', '891a8a', '8c9a5f', '8e09be', '8e4315',
   '910ce3', '9288bc', '93d7fa', '9943f2', '99cdde', '9b667a', '9bfabb', '9c7d57',
   '9cba27', '9fa1ba', 'a16cdc', 'a1ec60', 'a2aa60', 'a50d62', 'a89450', 'abf60e',
   'ac615e', 'ad6c42', 'b0379d', 'b237a6', 'b288a7', 'b6be74', 'b7a4ba', 'b88940',
   'b8dc1d', 'bd421c', 'bde219', 'be8a59', 'c26c68', 'c35066', 'c3d109', 'c3f2e2',
   'c4eb1a', 'c4f456', 'c548ff', 'c5663d', 'c5b34a', 'c69229', 'c6bd5c', 'c80015',
   'c8010c', 'c9da93', 'ca2ae2', 'cd24f3', 'd070ec', 'd37fca', 'd65135', 'd674db',
   'd99170', 'dcc59e', 'dee6e7', 'def2a2', 'e3259b', 'e33118', 'e52471', 'e6e347',
   'e7fba7', 'ea39cb', 'eab553', 'eafc83', 'eb278c', 'ecaf23', 'f0ca4c', 'f0ddf1',
   'f299d8', 'f45471', 'f4b119', 'f93aeb', 'f96471', 'fd2540', 'fe152d', 'fe207d')
_k('X',  # copyright text
   '0d9e42', '142146', '1bc25e', '1ffb0e', '26a4f3', '2829e6', '2f8d70', '3542b4',
   '49b51f', '5f2576', '6c9296', '6ca167', '8b8767', 'aedf1f', 'c3b384', 'd79c8d',
   'dcc9a6', 'dd45ac', 'e8d12e', 'f6c959')
_k('X', '7ed80f', '262f54', '568f71')   # letters of "EXTRA GAME" not shared with the font
# The Extra Game title writes "EXTRA GAME" over row 10 of the logo. The logo's
# own tiles for that row are put back under it, and the text drawn on top.
_LOGO_ROW10 = {5: 0x47, 6: 0x57, 7: 0x67, 8: 0x77, 9: 0x82, 10: 0xa5, 11: 0x85, 12: 0x89,
               13: 0x8d, 14: 0x90}


def _wallpaper(XX, YY):
    """A room's back wall, quilted: diamond seams every 16 px with a small star
    where they cross, a little lighter toward the floor (light from below)."""
    dx, dy = np.abs(XX % 16 - 8), np.abs(YY % 16 - 8)
    d = dx + dy
    t = 0.26 + 0.14 * np.floor(np.clip(YY % 256 / 128.0, 0, 1) * 3) / 3
    t = np.where(d >= 7, t + 0.2, t)                          # seams
    t = np.where((d <= 1) | ((dx == 0) & (dy <= 2)) | ((dy == 0) & (dx <= 2)), 0.76, t)   # stars
    return t


def _grain(XX, YY):
    """The inside of a hollow tree: dark heartwood with wavy vertical grain and
    the odd ring-shaped knot."""
    w = XX + 2.0 * np.sin(YY / 9.0 + XX / 23.0)
    t = 0.3 + 0.1 * ((XX // 24) % 2)                         # broad planks
    t = np.where(w % 12 < 1.2, t - 0.16, t)                   # grain lines
    kx, ky = (XX % 48) - 30, (YY % 64) - 40
    r = kx * kx + 2 * ky * ky
    t = np.where((r > 6) & (r < 16), t - 0.18, np.where(r <= 6, t + 0.1, t))   # knots
    return t


def _ashlar(XX, YY):
    """A castle wall in shadow: big stone blocks (16 x 8, every other course
    offset) with dark joints and a faintly lit top edge."""
    course = YY // 8
    joint = (YY % 8 == 7) | ((XX + (course % 2) * 8) % 16 == 15)
    t = 0.34 + 0.06 * (((XX + (course % 2) * 8) // 16 + course) % 3 == 0)
    t = np.where(YY % 8 == 0, t + 0.14, t)
    return np.where(joint, 0.1, t)


def _night(XX, YY):
    """Space above the clouds: deep blue-violet, a faint slow ripple of
    lighter haze (no pattern: the game's own stars are the detail)."""
    return 0.32 + 0.08 * np.sin(XX / 37.0 + YY / 53.0) + 0.05 * np.sin(YY / 19.0 - XX / 71.0)


def _cave(XX, YY):
    """A cave's far wall: dark, with big irregular stones picked out by faint
    lighter tops and darker cracks."""
    w = XX + 3.0 * np.sin(YY / 7.0) + 2.0 * np.sin(YY / 3.1 + XX / 11.0)
    v = YY + 2.5 * np.sin(XX / 6.0 + 1.3)
    cell = ((w // 14) * 7 + (v // 10) * 13) % 5
    t = 0.22 + 0.04 * cell
    t = np.where((w % 14 < 1.2) | (v % 10 < 1.0), 0.06, t)        # cracks
    t = np.where((v % 10 >= 1.0) & (v % 10 < 2.0), t + 0.12, t)    # lit tops
    return t


# which wall a room has: (stage bytes, area) -> 'tree', 'gallery' (Castle
# Lololo's dark walls with arched windows: stone in shadow, sky in the
# windows), 'arcade' (the same, every arch a window), else the quilted wall
ROOM_STYLE = {(0, 0, 3): 'tree', (0, 1, 3): 'gallery', (0, 1, 7): 'arcade', (0, 2, 1): 'cave',
              (0, 2, 5): 'tree', (0, 3, 5): 'night',
              (0, 3, 3): 'night', (0, 3, 4): 'night', (0, 3, 6): 'night', (0, 3, 7): 'night',
              (0, 4, 4): 'night'}     # (Mt. DeDeDe: Kracko's route, under the stars)   # (Bubbly Clouds' starry sky: space)


_SOLID_FOR = [None, None]     # (tile labels in use, their rock and ground hashes)


MARGIN = 2     # tiles of context around a redrawn band (3 by default; 2 draws the same here, faster)


# ---- eye candy (docs/KIRBY_EYE_CANDY_PLAN.md): strengths for ugb.render ----
EYE_CANDY = {
    'twinkle': 1.0,       # the starry areas' stars pulse (anim 5)
    'glint': 1.0,         # glints on wave crests (anim 6) and on all animated water
    'glint_on': (1, 3),   # (the water anims the glints also play on)
    'caustics': 1.0,      # light ripples under water (anim 7)
    'wobble': 1.0,        # ... and its lines sway sideways, in pixels
    'sway': 1.0,          # grass tips and palm fronds sway, in pixels (anim 8/9)
    'motes': 1.0,         # drifting leaves, spray, specks of light (MOTES), share of their count
    'trail': 1.0,         # sparkles behind the warp star (TRAIL_SPRITES)
}
_LEAVES = dict(shape='leaf', n=6, colours=['#3e8a3a', '#8ccc58'], vx=-0.22, vy=0.28, amp=6, freq=0.035, par=0.9)
_SPECKS = dict(shape='speck', n=10, colours=['#ffe48a', '#ffffff'], vx=0.07, vy=-0.05, amp=3, freq=0.02,
               par=0.5, alpha=0.75)
MOTES = {
    'green_greens': _LEAVES,
    'green_greens_extra': {**_LEAVES, 'colours': ['#6a4c8c', '#e0a0b4']},
    'float': dict(shape='dot', n=8, colours=['#f0feff'], vx=0.12, vy=-0.3, amp=2, freq=0.05, par=0.9, alpha=0.6),
    'float_sky': dict(shape='dot', n=6, colours=['#f0feff'], vx=0.12, vy=-0.3, amp=2, freq=0.05, par=0.9, alpha=0.6),
    'bubbly': _SPECKS,
    'ending': _SPECKS,
    'ending_extra': {**_SPECKS, 'colours': ['#ffd8b0', '#fff4e0']},
}
# the warp star's sprite halves as it spins (and the small star)
TRAIL_SPRITES = [int(h, 16) for h in ('6d8790', 'ac6376', '51862c', '94fe5d', 'f72740', 'efdf37',
                                      'b9ff4c', '905525', 'a2f4aa')]
SEA_TILES = [int(h, 16) for h in ('825809', 'd49c6b', '87cee2', 'e29982')] + WAVE_TILES
_SWAY_FOR = {}


def _sway_tiles(m):
    """Tall grass (Green Greens' look) and palm fronds (Float Islands')."""
    ls = look_stage(m)
    if ls not in _SWAY_FOR:
        tk = tile_keys_for(m)
        codes = {0: 'G', 2: 'GT'}.get(ls, '')
        _SWAY_FOR[ls] = np.fromiter((h for h, c in tk.items() if c in codes), np.int64) if codes else np.zeros(0, np.int64)
    return _SWAY_FOR[ls]


def paint_tiles(out, anim, kd, shade, keys, XX, YY, R, f=None):
    """Kirby's own touches (_paint_tiles), then the eye candy's marks."""
    _paint_tiles(out, anim, kd, shade, keys, XX, YY, R, f)
    if f is None:
        return
    sw = _sway_tiles(f.ram)
    if len(sw):
        m = np.isin(keys, sw)
        anim[m] = np.where(anim[m] == 4, 9, 8)
    m = np.isin(keys, SEA_TILES) & (shade <= 1) & (anim == 0)    # (water already animated keeps its anim)
    anim[m] = 6
    if kd is not None:
        anim[kd == 12] = 7
        k = area_key(f.ram)
        if k and ROOM_STYLE.get(k[:3]) == 'night':
            anim[np.isin(keys, STAR_TILES) & (shade < 3)] = 5


def _paint_tiles(out, anim, kd, shade, keys, XX, YY, R, f=None):
    """Kirby's own touches after the normal paint (ugb.render calls this per
    redrawn patch): rooms. kd is the solved kind (ugb.lineart), keys the tile
    hash per pixel."""
    from ugb import fx
    if f is not None and look_stage(f.ram) == ENDING:
        m = shade == 0        # (all the background's white is white: nothing in it is sky)
        out[m] = fx.pick(R['cloud'], 0.97 - 0.04 * ((YY % 16) > 11) + 0 * XX)[m]
        anim[m] = 0
        kb = np.isin(keys, KIRBY_BALLOON)
        if kb.any():      # his body: white his outline closes off, reached from his edge tiles
            from scipy import ndimage as ndi
            lab, n = ndi.label(shade == 0)
            ids = np.unique(lab[kb & (shade == 0)])
            ids = ids[ids > 0]
            edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
            sizes = ndi.sum(shade == 0, lab, ids) if len(ids) else np.zeros(0)
            ids = ids[~np.isin(ids, edge) & (sizes <= 12000)]   # (not open to the clouds)
            # and ringed by his own outline: most of the region's border in his tiles
            keep = []
            for i in ids:
                reg = lab == i
                ring = ndi.binary_dilation(reg) & ~reg
                if ring.any() and kb[ring].mean() >= 0.7:
                    keep.append(i)
            body = np.isin(lab, keep)
            kb = (kb & (shade != 0)) | body
        m = kb & (shade == 0)         # (puffed-up Kirby: one soft pink, like his sprite)
        out[m] = fx.pick(R['kirby'], np.full(m.shape, 0.667, np.float32))[m]
        m = kb & (shade >= 2)         # (his outline: deep rose)
        out[m] = fx.pick(R['kirby'], np.where(shade == 3, 0.04, 0.3))[m]
        anim[kb & (shade != 1)] = 0
        m = np.isin(keys, ENDING_DITHER) & (shade == 1)    # (a cloud's dithered edge: the sky between)
        anim[m] = 4
        m = np.isin(keys, ENDING_LAND) & (shade == 1)      # (the sky above the mountains' ridge)
        anim[m] = 4
    if f is not None and look_stage(f.ram) == 2:
        # Kaboola's sky (solved frame by frame, no post_solve): the cloud
        # platforms' white is cloud, not the sky behind
        m = np.isin(keys, FLOAT_PLATFORM_TILES) & (shade == 0)
        if kd is not None:
            m &= (kd == 1) | (kd == 0)
        if m.any():
            out[m] = fx.pick(R['cloud'], 0.96 - 0.05 * ((YY % 16) > 11) + 0 * XX)[m]
            anim[m] = 0
    if kd is None:
        return
    wall = kd == 8
    plank = np.isin(keys, _PLANK)
    wall |= plank & (shade == 3)
    style = None
    if f is not None:
        k = area_key(f.ram)
        style = ROOM_STYLE.get(k[:3]) if k else None
        # never over rock or ground: in a cave of look-alike ledges the area
        # camera can briefly match a twin spot, and a ledge would vanish
        tk = tile_keys_for(f.ram)
        if tk is not _SOLID_FOR[0]:
            _SOLID_FOR[:] = [tk, np.fromiter((h for h, c in tk.items() if c in 'EKGLB'), np.int64)]
        wall &= ~np.isin(keys, _SOLID_FOR[1])
    if wall.any():
        if style == 'tree':
            out[wall] = fx.pick(R['heartwood'], _grain(XX, YY))[wall]
        elif style in ('gallery', 'arcade'):
            out[wall] = fx.pick(R['gallery'], _ashlar(XX, YY))[wall]
        elif style == 'cave':
            out[wall] = fx.pick(R['cave'], _cave(XX, YY))[wall]
        elif style == 'night':
            out[wall] = fx.pick(R['night'], _night(XX, YY))[wall]
        else:
            out[wall] = fx.pick(R['room'], _wallpaper(XX, YY))[wall]
        anim[wall] = 0
    m = np.isin(keys, ROOM_TILES) & (shade == 3) & ~wall
    if m.any():     # a doorway seen from outside: the room's dark plum, not black
        if style == 'tree':
            out[m] = fx.pick(R['heartwood'], _grain(XX, YY))[m]
        elif style in ('gallery', 'arcade'):
            out[m] = fx.pick(R['gallery'], _ashlar(XX, YY))[m]
        elif style == 'cave':
            out[m] = fx.pick(R['cave'], _cave(XX, YY))[m]
        elif style == 'night':
            out[m] = fx.pick(R['night'], _night(XX, YY))[m]
        else:
            out[m] = fx.pick(R['room'], np.full(m.shape, 0.08, np.float32))[m]
        anim[m] = 0
    if style == 'cave':
        # the black around stalactites and beside rock edges is the far wall
        from scipy import ndimage as ndi
        blk = (shade == 3) & (np.isin(keys, CAVE_VOID_TILES) | np.isin(keys, ROOM_TILES))
        lab, n = ndi.label(blk)
        if n:
            big = np.concatenate([[False], ndi.sum(blk, lab, np.arange(1, n + 1)) >= 10])
            v = big[lab] & np.isin(keys, CAVE_VOID_TILES)
            out[v] = fx.pick(R['cave'], _cave(XX, YY))[v]
            anim[v] = 0
    if style == 'night':
        # stars: the black around them is space, their white a warm glow, the
        # in-between shades a halo; the dusk band's black is space too
        st_ = np.isin(keys, STAR_TILES)
        sp = (st_ | np.isin(keys, DUSK_TILES)) & (shade == 3)
        out[sp] = fx.pick(R['night'], _night(XX, YY))[sp]
        g = st_ & (shade < 3)
        out[g] = fx.pick(R['star'], np.where(shade == 0, 0.95, np.where(shade == 1, 0.6, 0.3)))[g]
        dk = np.isin(keys, DUSK_TILES) & (shade < 3)     # (the band's light: lilac dusk)
        out[dk] = fx.pick(R['star'], np.where(shade == 0, 0.7, np.where(shade == 1, 0.45, 0.22)))[dk]
        anim[sp | g | dk] = 0
        if k and k[:3] in ((0, 3, 7), (0, 4, 4)):    # the crescent moon
            mt = np.isin(keys, MOON_TILES)
            ms = mt & (shade == 3)
            out[ms] = fx.pick(R['night'], _night(XX, YY))[ms]
            mg = mt & (shade < 3)
            out[mg] = fx.pick(R['star'], np.where(shade == 0, 0.98, 0.7))[mg]
            anim[ms | mg] = 0
    m = kd == 16
    if m.any():     # holes in the foliage: leaves in shadow, the canopy's own dark green
        out[m] = fx.pick(R['tree'], np.full(m.shape, 0.3, np.float32))[m]
        anim[m] = 0
    m = kd == 15
    if m.any():     # night sky (above the dusk band)
        out[m] = fx.pick(R['night'], _night(XX, YY))[m]
        anim[m] = 0
    m = kd == 13
    if m.any():     # curtains: velvet, the white its lit folds, the stripes deep ones
        t = np.where(shade == 0, 0.7, np.where(shade == 1, 0.5, np.where(shade == 2, 0.28, 0.1)))
        t = t + 0.06 * np.sin(XX * 0.9)
        out[m] = fx.pick(R['curtain'], t)[m]
        anim[m] = 0
    m = kd == 14
    if m.any():     # their swag ropes and tassels: gold
        out[m] = fx.pick(R['gold'], np.where(shade == 3, 0.25, 0.65))[m]
        anim[m] = 0
    m = np.isin(keys, SPIKE_TILES) & (shade >= 2)
    if m.any():     # spikes: steel, the outline dark, the shading mid
        out[m] = fx.pick(R['metal'], np.where(shade == 3, 0.05, 0.4))[m]
    m = kd == 12
    if m.any():     # under the sea's surface: turquoise water, deeper further down
        t = 0.62 - 0.08 * ((YY // 24) % 2) + 0 * XX
        t = t + np.where(np.isin(keys, SEA_FILL), np.where(shade == 0, 0.14, 0.0), 0.0)   # (the fill's dotted glints)
        t = t - np.where(shade >= 2, 0.12, 0.0)
        out[m] = fx.pick(R['water'], t)[m]
        anim[m] = 0
    m = kd == 11
    if m.any():     # a lit trim along the wall's foot
        out[m] = fx.pick(R['floor'], np.full(m.shape, 0.95, np.float32))[m]
        anim[m] = 0
    m = kd == 10
    if m.any() and style in ('gallery', 'arcade'):
        # tall arches are windows, the sky behind them (the backdrop); short
        # ones are doorways, lit like the others
        from scipy import ndimage as ndi
        lab, n = ndi.label(m)
        tall = np.zeros(n + 1, bool)
        for i, sl in enumerate(ndi.find_objects(lab), 1):
            tall[i] = style == 'arcade' or sl[0].stop - sl[0].start >= 30
        win = tall[lab] & m
        out[win] = fx.pick(R['sky'], np.full(m.shape, 0.6, np.float32))[win]
        anim[win] = 4
        m &= ~win
    if m.any():     # the doorway: warm light, brightest at the top
        lab_top = np.where(m, YY, 9999).min(axis=0, keepdims=True)
        t = 0.98 - 0.12 * np.floor(np.clip((YY - lab_top) / 6.0, 0, 4))
        out[m] = fx.pick(R['doorway'], t)[m]
        anim[m] = 0
    m = kd == 9
    if m.any():     # pillars: cream, lit from the left
        lit = ~fx.shift(m, 0, 3, False, True)
        out[m] = fx.pick(R['pillar'], np.where(lit, 0.82, 0.62))[m]
        anim[m] = 0
        # their outlines (painted as hill lines) take the pillar's dark tone
        ln = fx.dilate(fx.dilate(m, True), True) & ~m & (shade >= 1) & ~wall & (kd != 10)
        out[ln] = fx.pick(R['pillar'], np.where(shade[ln] >= 2, 0.05, 0.4) + 0 * YY[ln])
        anim[ln] = 0
    m = plank & (shade < 3)
    if m.any():     # the plank: a lit top edge, wood below
        out[m] = fx.pick(R['furniture'], np.choose(shade, [0.92, 0.6, 0.3, 0.0]))[m]
        anim[m] = 0


def patch_frame(f):
    """Before rendering: restore the logo under "EXTRA GAME"; returns the text
    tiles as an overlay [(map row, map column, tile number)]."""
    m = f.maps[f.bg_map()]
    if f.ram[RAM['extra_game']] != 1 or list(m[9, 2:5]) != [0x16, 0x26, 0x36]:
        return []
    over = []
    for c, t in _LOGO_ROW10.items():
        if m[10, c] != t:
            if m[10, c] != 0:
                over.append((10, c, int(m[10, c])))
            m[10, c] = t
    return over


LOGO_SPLIT = 62      # letters centred above: "KIRBY'S" (pink); below: "DREAM LAND" (gold)
TEXT_SHADOW = '#fff0f8'   # deep plum text with a light halo (it sits on pale clouds)

# The hidden Extra Game has its own skies: a night title and twilight stages.
RAMP_BY_BACKDROP = {
    # Castle Lololo: a warm afternoon, a sandstone castle, hazy violet mountains
    'lololo': {
        'wall': hx('#5a3420', '#8a5a34', '#b8844c', '#d8aa6a', '#f0cc90', '#fff0c8'),
        'rock': hx('#4a4038', '#6e6254', '#928474', '#b4a896', '#d4cab8', '#f0e8dc'),
        'roof': hx('#6a6098', '#8278b4', '#9c94c8', '#b8b0dc', '#d4cce8', '#f0ecf8'),
        'metal': hx('#5a5070', '#8a82a4', '#b8b2cc', '#dcd8e8', '#f6f4fa', '#ffffff'),
        'sky': hx('#5a70d0', '#7488e0', '#94a2ea', '#b6bcf0', '#d8d2f4', '#f4e8f4', '#fff4ec'),
        'cloud': hx('#c8a0c0', '#e0c0d8', '#f4dcea', '#fff0f6', '#ffffff'),
        # the looping hall: warm plaster, rose marble, ivory columns
        'door': hx('#6a4630', '#a07658', '#c8a078', '#e4c69c', '#f4dcb8', '#fdeed4'),
        'sign': hx('#4a1830', '#7a2a48', '#a84462', '#c86078', '#f6d6d0', '#fff0e8'),
        'pipe': hx('#4a3a5a', '#7a6a8a', '#a89cb4', '#d0c6d6', '#ece4ea', '#fffaf6'),
        'gallery': hx('#140c1e', '#22162e', '#30203e', '#40304e', '#544060', '#6a5274'),
        'water': hx('#14246a', '#1e3a8a', '#2c52a6', '#4070c0', '#5e90d6', '#90b4ea', '#d0e2fa'),
    },
    'title_night': {'text': hx('#b89cc8', '#e6d4ee', '#fff4d8', '#fffbea', '#ffffff')},
    'green_greens_extra': {
        'cloud': hx('#6a4c8c', '#a070a8', '#e0a0b4', '#ffccc0', '#ffe6d6'),
        'hill': hx('#1c4a5a', '#28606a', '#367a78', '#4a9282', '#6aac90', '#90c49e'),
        'sky': hx('#2a1c5c', '#4a2a7a', '#7a3a8a', '#b84a86', '#e86c74', '#f89a6c', '#fcc888'),
    },
}
RAMP_BY_BACKDROP['lololo_hall'] = RAMP_BY_BACKDROP['lololo']
# Float Islands: a tropical late afternoon, golden sand, coral-brown rock,
# lush palms, a turquoise sea
RAMP_BY_BACKDROP['float'] = {
    'sky': hx('#2a7ad8', '#3a92e6', '#56aaf0', '#7cc4f6', '#a6dcfa', '#d2f0fc', '#f4fcff'),
    'cloud': hx('#8ab4e0', '#b2d2f2', '#d8ecfa', '#f2faff', '#ffffff'),
    'ground': hx('#9a6430', '#c48c4c', '#e0b06c', '#f2cc8c', '#fbe4b4', '#fff6dc'),
    'dirt': hx('#7a4a24', '#a46a38', '#c88c50', '#e0aa6a', '#f0c88c'),
    'earth': hx('#6a4022', '#8e5a30', '#b07a44', '#cc985c', '#e4b87c', '#f4d8a4'),
    'rock': hx('#3a2a30', '#5a4048', '#7c5a5e', '#a07a78', '#c4a09a', '#e6ccc4'),
    'tree': hx('#0a3a2a', '#105432', '#18703c', '#2a9048', '#48b058', '#78cc6c', '#b0e890'),
    'pipe': hx('#4a2c14', '#6e4420', '#92602e', '#b48042', '#d0a060', '#ead0a0'),
    'water': hx('#0a4a7a', '#0e6a96', '#1a8cb0', '#30aec8', '#5ccede', '#a0ecf0', '#e8fcff'),
    'cave': hx('#0a0e1c', '#121a2c', '#1a263c', '#24324c', '#30405c', '#40526c'),
    'floor': hx('#3a1e10', '#5c3218', '#824a24', '#a66634', '#c4864a', '#dea866'),
    'roof': hx('#4a3018', '#7a5430', '#a87c4c', '#cca472', '#e8cc9c', '#fff0d0'),
    'metal': hx('#6a8cc0', '#98b6e0', '#c4daf2', '#e6f2fc', '#fafdff', '#ffffff'),
    'post': hx('#6a1c2c', '#a83448', '#de6474', '#f6a0a0', '#fddcd6', '#fff8f2'),
    # no outlined hills on Float Islands: a shape read as one is a cloud
    'hill': hx('#5a7ab0', '#8aa8d8', '#c0d6f0', '#e8f2fc', '#ffffff', '#ffffff'),
}
RAMP_BY_BACKDROP['float_sky'] = RAMP_BY_BACKDROP['float']
# Mt. DeDeDe: the king's castle, honey parquet and slate-blue stone, gold trim
RAMP_BY_BACKDROP['dedede'] = {
    'sign': hx('#4a2a14', '#7a4a24', '#a8703a', '#cc9654', '#e8bc7c', '#fadcaa'),
    'wall': hx('#1e2240', '#2e3560', '#465080', '#6470a0', '#8a96c0', '#b8c2de'),
    'cloth': hx('#4a0c20', '#7a1830', '#a82a40', '#d04a58', '#ec8080', '#fcc0b0'),
    'furniture': hx('#1e0a06', '#401a10', '#6a2a1a', '#924226', '#ba6638', '#de9258'),   # mahogany doors
    'water': RAMP_BY_BACKDROP['float']['water'],
}
# Bubbly Clouds: high noon above the clouds, a white marble temple
RAMP_BY_BACKDROP['bubbly'] = {
    'sky': hx('#1a4cc0', '#2a62d4', '#3e7ce2', '#5a98ec', '#7ab4f4', '#a2cefa', '#d0e8fe'),
    'cloud': hx('#1e3070', '#4c68aa', '#a8bee6', '#e4eefc', '#ffffff'),
    'hill': hx('#7e9ed8', '#a8c2ec', '#d0e0f8', '#eef4fe', '#ffffff', '#ffffff'),
    'pipe': hx('#5a6488', '#8a94b4', '#b6bed6', '#dce0ee', '#f4f6fc', '#ffffff'),
    'metal': hx('#5a6488', '#8a94b4', '#b6bed6', '#dce0ee', '#f4f6fc', '#ffffff'),
    'floor': hx('#4a4a6a', '#6e7090', '#9496b4', '#babcd4', '#dcdeee', '#f6f6fc'),
    'curtain': hx('#4a4270', '#7a72a0', '#aaa4c8', '#d4d0e6', '#f0eef8', '#fffeff'),   # white, like the temple
    'night': hx('#05041a', '#0c0a2c', '#16123e', '#221a54', '#30246c', '#423286'),
    'star': hx('#5a4c9a', '#9a8cd0', '#d8d0f4', '#fff4c8', '#fffbe8'),
    'sign': hx('#3e3460', '#6c6094', '#9c90c0', '#c8bede', '#ebe5f4', '#fffcff'),   # the temple's marble
    'roof': hx('#4a4a6a', '#6e7090', '#9496b4', '#babcd4', '#dcdeee', '#f6f6fc'),
    'water': RAMP_BY_BACKDROP['float']['water'],
    'cave': RAMP_BY_BACKDROP['float']['cave'],
}
RAMP_BY_BACKDROP['ending'] = {**RAMP_BY_BACKDROP['bubbly'],
                               'wall': RAMP_BY_BACKDROP['dedede']['wall'],          # (the ring's stone, the dark bumps)
                               'furniture': RAMP_BY_BACKDROP['dedede']['furniture'],
                               'cloth': RAMP_BY_BACKDROP['dedede']['cloth'],
                               'kirby': hx('#7a1838', '#b83a62', '#e66a8c', '#f89ab0', '#fab0c2', '#fcc4d2', '#ffe4ec')}
RAMP_BY_BACKDROP['ending_extra'] = {**RAMP_BY_BACKDROP['ending'], **RAMP_BY_BACKDROP['green_greens_extra']}
_DUSK_CLOUD = hx('#6a4c8c', '#a070a8', '#e0a0b4', '#ffccc0', '#ffe6d6')
RAMP_BY_BACKDROP['lololo_extra'] = {**RAMP_BY_BACKDROP['lololo'],
                                    'sky': hx('#06081e', '#0c1030', '#141a44', '#1e2658', '#2a346c', '#3a4480', '#4c5490'),
                                    'cloud': hx('#2a2c5a', '#4a4c80', '#7a7caa', '#aeb0d0', '#dcdcf0')}
RAMP_BY_BACKDROP['float_extra'] = {**RAMP_BY_BACKDROP['float'],
                                   'sky': hx('#2a1c5c', '#4a2a7a', '#7a3a8a', '#b84a86', '#e86c74', '#f89a6c', '#fcc888'),
                                   'cloud': _DUSK_CLOUD,
                                   'hill': hx('#6a4c8c', '#a070a8', '#e0a0b4', '#ffccc0', '#ffe6d6', '#fff2ea'),
                                   'water': hx('#1c1e4c', '#2c2e66', '#46447e', '#745c94', '#a8789e', '#d898a0', '#f4c4a0')}
RAMP_BY_BACKDROP['float_sky_extra'] = RAMP_BY_BACKDROP['float_extra']
RAMP_BY_BACKDROP['bubbly_extra'] = {**RAMP_BY_BACKDROP['bubbly'],
                                    'sky': hx('#1a1450', '#2c1c66', '#46287a', '#6a3488', '#9a4688', '#c85c80', '#ec8478'),
                                    'cloud': hx('#5a3c7c', '#9a6aa0', '#dca0b4', '#ffd0c4', '#fff0ea')}
TEXT_SHADOW_BY_BACKDROP = {'title_night': '#1a0c38'}
_TITLE_SLOT = (0, 237, int('1ffb0e', 16))   # a logo tile and where the title keeps it

def atlas_key(f):
    """Which area is on screen, for ugb.atlas (None outside play): stage bytes,
    area within the stage, and the Extra Game."""
    return area_key(f.ram)


# for ugb.lineart: tiles labelled as land that also serve as hill outlines
# (the cliff-side tile is also the side of the tall towers)
LINE_EDGE_TILES = [int('0c913b', 16)]
# double-line columns (hoop legs, a room's pillars): drawn in front of the shapes
# behind, so their lines don't vote on what those shapes are
FRONT_TILES = [int('b4c507', 16), int('7f0ec8', 16)]

STAMPS = []


# ---- parallax backdrops -------------------------------------------------------
EXTRA_BACKDROPS = ('lololo', 'float', 'float_sky', 'bubbly')


def backdrop_key(f):
    """The stage's backdrop (_backdrop_key), its Extra Game version where there is one."""
    k = _backdrop_key(f)
    if k in EXTRA_BACKDROPS and f.ram[RAM['extra_game']] == 1:
        return k + '_extra'
    return k


def _backdrop_key(f):
    """Which backdrop to show: the title screen's (a night sky in the Extra Game),
    else the stage's (Green Greens so far)."""
    if look_stage(f.ram) == ENDING:     # (before the title test: the title's logo tile is still loaded)
        return 'ending_extra' if f.ram[RAM['extra_game']] == 1 else 'ending'
    bank, slot, h = _TITLE_SLOT
    import hashlib
    extra = f.ram[RAM['extra_game']] == 1
    if int(hashlib.blake2b(f.tiles[bank, slot].tobytes(), digest_size=3).hexdigest(), 16) == h:
        return 'title_night' if extra else 'title'
    ls = look_stage(f.ram)
    if ls != f.ram[0xD03B]:       # (Mt. DeDeDe's boss rush, back in an earlier stage)
        return {0: 'green_greens', 1: 'lololo', 2: 'float' if f.ram[RAM['area']] in DEDEDE_SEA_AREAS
                else 'float_sky', 3: 'bubbly', ENDING: 'ending'}[ls]
    if f.ram[0xD03B] == 4:
        return 'dedede'
    if f.ram[0xD03B] == 3:
        return 'bubbly'
    if f.ram[0xD03B] == 2:
        return 'float' if f.ram[RAM['area']] in SEA_AREAS else 'float_sky'
    if f.ram[0xD03B] == 1:
        # (the looping hall is indoors: no sky to show, so no backdrop to compose)
        return 'lololo_hall' if (1, f.ram[RAM['area']]) in INDOORS else 'lololo'
    return 'green_greens_extra' if extra else 'green_greens'


def _bands(top, bottom, ys, steps):
    """A vertical gradient quantised into flat bands (the 16-bit look)."""
    t = np.clip((ys - top) / max(bottom - top, 1), 0, 1)
    return np.floor(t * steps) / steps


def _profile(w, base, amp, waves, seed):
    """A wrapping skyline: the sum of a few whole-number sine waves."""
    rng = np.random.default_rng(seed)
    x = np.arange(w) / w * 2 * np.pi
    y = np.full(w, float(base))
    for n, a in waves:
        y += amp * a * np.sin(n * x + rng.uniform(0, 2 * np.pi))
    return y


def _silhouette(w, h, line, top_col, body_col, rim_col, shade_col=None):
    """RGBA layer: solid below `line` (per column), lit rim on top, darker toward
    the bottom in bands."""
    ys = np.arange(h)[:, None].astype(np.float32)
    inside = ys >= line[None, :]
    depth = ys - line[None, :]
    img = np.zeros((h, w, 4), np.float32)
    t = np.clip(depth / 40.0, 0, 1)
    t = np.floor(t * 4) / 4
    col = top_col[None, None] * (1 - t[..., None]) + body_col[None, None] * t[..., None]
    if shade_col is not None:     # the slope facing away from the light is darker
        slope = np.gradient(line)[None, :, None]
        col = np.where(slope < -0.15, col * 0.75 + shade_col * 0.25, col)
    rim = inside & (depth < 1.5)
    col = np.where(rim[..., None], rim_col[None, None], col)
    img[..., :3] = col
    img[..., 3] = inside
    return img


def _clouds(w, h, seed, n, y0, y1, col, shade, alpha):
    """RGBA layer of soft round cumulus: unions of circles, shaded underneath."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    mask = np.zeros((h, w), bool)
    low = np.zeros((h, w), bool)
    for _ in range(n):
        cx, cy = rng.uniform(0, w), rng.uniform(y0, y1)
        size = rng.uniform(10, 20)
        for _ in range(5):
            bx = cx + rng.uniform(-1.6, 1.6) * size
            by = cy + rng.uniform(-0.5, 0.2) * size
            r = size * rng.uniform(0.55, 0.95)
            dx = (xx - bx + w / 2) % w - w / 2        # wraps around
            d = dx ** 2 + (yy - by) ** 2
            mask |= d < r * r
        low |= mask & (yy > cy + size * 0.15)
    img = np.zeros((h, w, 4), np.float32)
    img[..., :3] = np.where(low[..., None], shade, col)
    img[..., 3] = mask * alpha
    return img


def _title_day():
    """A bright dream morning: azure to pale aqua in flat bands, a soft white glow
    behind the logo, sun rays from the top, a few golden sparkles, and a bank of
    pink-white clouds below."""
    h, w = 160, 160
    ys = np.arange(h, dtype=np.float32)
    sky = hx('#3c86ec', '#4c98f2', '#62acf6', '#7cc0f8', '#98d2fa', '#b6e2fc', '#d4f0fd', '#ecf9ff')
    k = (_bands(0, 130, ys, len(sky) - 1) * (len(sky) - 1)).astype(int)
    img = np.zeros((h, w, 4), np.float32)
    img[..., :3] = sky[k][:, None]
    img[..., 3] = 1
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ang = np.arctan2(yy + 30, xx - 80)            # rays fanning down from above the logo
    rays = (np.floor(ang / (np.pi / 18)) % 2 == 0) & (yy < 120)
    img[rays, :3] = img[rays, :3] * 0.88 + hx('#ffffff')[0] * 0.12
    d = np.hypot((xx - 80) / 1.3, yy - 62)
    glow = np.floor(np.clip(1 - d / 78, 0, 1) * 5) / 5 * 0.55
    img[..., :3] = img[..., :3] * (1 - glow[..., None]) + hx('#fff8fc')[0] * glow[..., None]
    rng = np.random.default_rng(5)
    for _ in range(14):                        # golden sparkles
        x, y = int(rng.uniform(4, w - 4)), int(rng.uniform(4, 110))
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            img[y + dy, x + dx, :3] = hx('#fff2a0')[0] if (dx, dy) == (0, 0) else hx('#ffd84a')[0]
    clouds = _clouds(w, h, 11, 7, 132, 150, hx('#ffffff')[0], hx('#f6cce0')[0], 1.0)
    a = clouds[..., 3:4]
    img[..., :3] = img[..., :3] * (1 - a) + clouds[..., :3] * a
    return [(img, 0.0, 0.0)]


def _title_night():
    """The Extra Game's title, a dream night sky: deep indigo to violet, pink and a peach horizon in flat bands,
    a soft glow behind the logo, sparkling stars, a pastel cloud bank below."""
    h, w = 160, 160
    ys = np.arange(h, dtype=np.float32)
    sky = hx('#1c1650', '#2a1c6a', '#44247e', '#66308c', '#8e3c92', '#b84c94', '#dc6a96',
             '#f08c98', '#f8ae9c', '#fcc8a8')
    k = (_bands(0, 140, ys, len(sky) - 1) * (len(sky) - 1)).astype(int)
    img = np.zeros((h, w, 4), np.float32)
    img[..., :3] = sky[k][:, None]
    img[..., 3] = 1
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.hypot((xx - 80) / 1.3, yy - 62)
    glow = np.floor(np.clip(1 - d / 78, 0, 1) * 5) / 5 * 0.5
    img[..., :3] = img[..., :3] * (1 - glow[..., None]) + hx('#ffd6ec')[0] * glow[..., None]
    rng = np.random.default_rng(7)
    for _ in range(46):                       # stars: dots, some with a plus-shaped twinkle
        x, y = int(rng.uniform(0, w)), int(rng.uniform(0, 100))
        img[y, x, :3] = hx('#fff8e0')[0]
        if rng.random() < 0.35:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= y + dy < h:
                    img[y + dy, (x + dx) % w, :3] = hx('#ffe6f4')[0]
    clouds = _clouds(w, h, 11, 7, 132, 150, hx('#7a5aa8')[0], hx('#56408a')[0], 1.0)
    a = clouds[..., 3:4]
    img[..., :3] = img[..., :3] * (1 - a) + clouds[..., :3] * a
    return [(img, 0.0, 0.0)]


def _green_greens_twilight():
    """Green Greens in the Extra Game: sunset into twilight. Banded sky from indigo
    through magenta to a glowing orange horizon, the first stars, dark violet
    mountains, peach-lit clouds and deep teal hills."""
    h = 160
    ys = np.arange(h, dtype=np.float32)
    sky = hx('#1e1650', '#2e1c66', '#4a2678', '#702e86', '#9a3a88', '#c64a80', '#e8646c',
             '#f88c5c', '#fcb460')
    k = (_bands(0, 116, ys, len(sky) - 1) * (len(sky) - 1)).astype(int)
    grad = np.zeros((h, 160, 4), np.float32)
    grad[..., :3] = sky[k][:, None]
    grad[..., 3] = 1
    yy, xx = np.mgrid[0:h, 0:160]
    d = np.hypot(xx - 40, yy - 104)               # the setting sun, low on the left
    glow = (d < 26) * 0.25 + (d < 18) * 0.25
    grad[..., :3] = grad[..., :3] * (1 - glow[..., None]) + hx('#ffd890')[0] * glow[..., None]
    grad[d < 11, :3] = hx('#fff0c0')[0]
    rng = np.random.default_rng(9)
    for _ in range(28):                           # first stars, high up
        x, y = int(rng.uniform(0, 160)), int(rng.uniform(0, 48))
        grad[y, x, :3] = hx('#fff4e0')[0]
    layers = [(grad, 0.0, 0.0)]
    w = 640
    line = _profile(w, 92, 14, ((2, 1.0), (5, 0.5), (11, 0.25)), 1)
    layers.append((_silhouette(w, h, line, hx('#5a3a7a')[0], hx('#46306a')[0], hx('#c0709a')[0],
                               hx('#3a2860')[0]), 0.1, 0.0))
    layers.append((_clouds(768, h, 2, 9, 14, 60, hx('#ffc8b0')[0], hx('#c07ab0')[0], 0.85), 0.22, 0.0))
    w = 768
    line = _profile(w, 112, 9, ((3, 1.0), (7, 0.45), (13, 0.2)), 3)
    layers.append((_silhouette(w, h, line, hx('#2e5a66')[0], hx('#244a58')[0], hx('#e09a8a')[0],
                               hx('#1c3a4a')[0]), 0.35, 0.0))
    return layers


def _lololo(extra=False):
    """Castle Lololo: a warm late afternoon. Periwinkle sky to a peach horizon in
    flat bands and a golden sun high on the right. Just the sky: the game draws
    its own mountains and clouds in every outdoor area here, so the backdrop
    adds none (they would double up). In the Extra Game: a moonlit night."""
    h = 160
    ys = np.arange(h, dtype=np.float32)
    sky = (hx('#06081e', '#0c1030', '#141a44', '#1e2658', '#2a346c', '#3a4480', '#4c5490', '#5e5f98') if extra else
           hx('#4a62c8', '#5e76d8', '#7a8ee2', '#9ca8ea', '#c0c0ee', '#e2d2ec', '#f8e0dc', '#ffeccc'))
    k = (_bands(0, 118, ys, len(sky) - 1) * (len(sky) - 1)).astype(int)
    grad = np.zeros((h, 160, 4), np.float32)
    grad[..., :3] = sky[k][:, None]
    grad[..., 3] = 1
    yy, xx = np.mgrid[0:h, 0:160]
    d = np.hypot(xx - 126, yy - 34)
    if extra:
        rng = np.random.default_rng(11)
        for _ in range(40):                       # stars, thinning toward the horizon
            x, y = int(rng.uniform(0, 160)), int(abs(rng.normal(0, 40)))
            if y < 100:
                grad[y, x, :3] = hx('#e8e8ff' if rng.random() < 0.7 else '#fff0c0')[0]
        grad[d < 14, :3] = grad[d < 14, :3] * 0.75 + hx('#3a4a8a')[0] * 0.25    # the moon's halo
        moon = (d < 7) & ~(np.hypot(xx - 129, yy - 32) < 6)                    # a crescent
        grad[moon, :3] = hx('#f6f0d4')[0]
        return [(grad, 0.0, 0.0)]
    for r, col, a in ((15, '#f4e8fa', 0.35), (11, '#fff0c4', 0.6)):   # a lilac halo, a warm one
        m = d < r
        grad[m, :3] = grad[m, :3] * (1 - a) + hx(col)[0] * a
    grad[d < 7, :3] = hx('#fff8dc')[0]
    return [(grad, 0.0, 0.0)]


FLOAT_H, FLOAT_HZ = 344, 172    # the sea backdrop: tall, its horizon this far down (backdrop_y)


def _float_islands(with_sea=True, extra=False):
    """Float Islands: a tropical sky warming toward a low sun on the left, and
    below the horizon a turquoise sea, paler far off, with the sun's light
    broken into streaks on it. The image is tall: backdrop_y slides it so its
    horizon sits on the game's haze row wherever that is on screen. In the
    Extra Game: a sunset over a dusky violet sea."""
    sky = (hx('#2a1c5c', '#4a2a7a', '#7a3a8a', '#b84a86', '#e86c74', '#f89a6c', '#fcc888', '#ffe0a0') if extra else
           hx('#2a6ed0', '#3a86e0', '#58a2ec', '#80bef4', '#a8d6f6', '#d0e6f0', '#f6e6d0', '#ffdcb0'))
    sea = (hx('#f4c4a0', '#d898a0', '#a8789e', '#745c94', '#46447e', '#2c2e66', '#1c1e4c') if extra else
           hx('#bfeef0', '#8ad8e6', '#5cc0da', '#3aa4cc', '#2286b8', '#14689e', '#0c5286'))
    sun_halo = ('#ffb890', '#ffd8a0') if extra else ('#ffe8c8', '#fff0c0')
    sun = '#fff0c8' if extra else '#fff8dc'
    if not with_sea:     # (no horizon in sight: the sky all the way down)
        h = 160
        ys = np.arange(h, dtype=np.float32)
        grad = np.zeros((h, 160, 4), np.float32)
        k = (_bands(0, h - 16, ys, len(sky) - 1) * (len(sky) - 1)).astype(int)
        grad[..., :3] = sky[k][:, None]
        grad[..., 3] = 1
        yy, xx = np.mgrid[0:h, 0:160]
        d = np.hypot(xx - 40, yy - 104)
        for r, col, a in ((18, sun_halo[0], 0.35), (13, sun_halo[1], 0.6)):
            grad[d < r, :3] = grad[d < r, :3] * (1 - a) + hx(col)[0] * a
        grad[d < 8, :3] = hx(sun)[0]
        return [(grad, 0.0, 0.0)]
    h, hz = FLOAT_H, FLOAT_HZ
    ys = np.arange(h, dtype=np.float32)
    grad = np.zeros((h, 160, 4), np.float32)
    k = (_bands(hz - 68, hz, ys, len(sky) - 1) * (len(sky) - 1)).astype(int)
    grad[:hz, :, :3] = sky[k[:hz]][:, None]
    t = np.clip((ys - hz) / 72.0, 0, 1) ** 0.7
    ks = np.minimum((t * len(sea)).astype(int), len(sea) - 1)
    grad[hz:, :, :3] = sea[ks[hz:]][:, None]
    grad[..., 3] = 1
    yy, xx = np.mgrid[0:h, 0:160]
    d = np.hypot(xx - 40, yy - (hz - 10))
    up = yy < hz
    for r, col, a in ((18, sun_halo[0], 0.35), (13, sun_halo[1], 0.6)):
        m = (d < r) & up
        grad[m, :3] = grad[m, :3] * (1 - a) + hx(col)[0] * a
    grad[(d < 8) & up, :3] = hx(sun)[0]
    # the sun's path on the sea: short light streaks, wider and sparser further down
    rng = np.random.default_rng(7)
    near = '#ffd8a0' if extra else '#fff4d0'
    far = '#e8b0b8' if extra else '#d8f6f8'
    for y in range(hz + 1, hz + 92, 3):
        depth = (y - hz) / 92.0
        for _ in range(2):
            x = 40 + rng.normal(0, 4 + 22 * depth)
            w = int(2 + 6 * depth * rng.random())
            x0 = int(np.clip(x - w / 2, 0, 159))
            grad[y, x0:x0 + w, :3] = hx(near if depth < 0.4 else far)[0]
    return [(grad, 0.0, 0.0)]


_HZ_HASH = {}


def backdrop_y(f):
    """Which row of the backdrop sits at the top of the screen (ugb.render):
    for the Float Islands sea, its horizon on the game's haze row wherever that
    is on screen; None for the other backdrops (they don't slide)."""
    from ugb import atlas
    if not backdrop_key(f).startswith('float') or backdrop_key(f).startswith('float_sky'):
        return None
    bm = f.bg_map()
    ids = f.tile_index(f.maps[bm])
    sy, sx = int(np.bincount(f.scy).argmax()), int(np.bincount(f.scx).argmax())
    col = (sx // 8 + 4) % 32
    for r in range(-1, 19):
        mr = (sy // 8 + r) % 32
        t = f.tiles[0, ids[mr, col]]
        key = t.tobytes()
        h = _HZ_HASH.get(key)
        if h is None:
            h = _HZ_HASH[key] = atlas._hash(t)
        if h in HORIZON_TILES:
            top = (mr * 8 - sy) % 256
            if top > 200:
                top -= 256
            return FLOAT_HZ - (top + 4)
    return FLOAT_HZ - 68


def _bubbly_sky(extra=False):
    """Bubbly Clouds: high above the clouds at noon, a deep blue sky paling
    toward the cloud sea below, the sun's glow in the top corner. The game draws all
    its clouds itself, so the backdrop adds none. In the Extra Game: a high
    twilight, violet to peach, with the first stars."""
    h = 160
    ys = np.arange(h, dtype=np.float32)
    sky = (hx('#1a1450', '#2c1c66', '#46287a', '#6a3488', '#9a4688', '#c85c80', '#ec8478', '#f8b48a') if extra else
           hx('#1c48b8', '#2a5ccc', '#3c74dc', '#548ee8', '#70aaf0', '#94c4f6', '#bcdcfa', '#e2f0fe'))
    k = (_bands(0, h - 24, ys, len(sky) - 1) * (len(sky) - 1)).astype(int)
    grad = np.zeros((h, 160, 4), np.float32)
    grad[..., :3] = sky[k][:, None]
    grad[..., 3] = 1
    yy, xx = np.mgrid[0:h, 0:160]
    # the sun is just off the top, a soft glow in the corner: a disc would show
    # cut into crescents behind the game's own clouds
    d = np.hypot(xx - 132, yy + 10)
    glow = np.clip(1 - d / 70.0, 0, 1) ** 2 * 0.55
    grad[..., :3] = grad[..., :3] * (1 - glow[..., None]) + hx('#ffc8a0' if extra else '#fff6dc')[0] * glow[..., None]
    if extra:
        rng = np.random.default_rng(13)
        for _ in range(30):
            x, y = int(rng.uniform(0, 160)), int(rng.uniform(0, 56))
            grad[y, x, :3] = hx('#fff4e0')[0]
    return [(grad, 0.0, 0.0)]


def make_backdrop(key):
    """Layers for a stage, far to near: (rgba image, kx, ky); None indoors."""
    if key in ('bubbly', 'ending'):
        return _bubbly_sky()
    if key == 'bubbly_extra':
        return _bubbly_sky(extra=True)
    if key == 'lololo_extra':
        return _lololo(extra=True)
    if key == 'float_extra':
        return _float_islands(extra=True)
    if key == 'float_sky_extra':
        return _float_islands(with_sea=False, extra=True)
    if key == 'ending_extra':       # (the Extra Game's: Green Greens' twilight)
        return _green_greens_twilight()
    if key == 'float':
        return _float_islands()
    if key == 'float_sky':
        return _float_islands(with_sea=False)
    if key in ('lololo_hall', 'dedede'):
        return None
    if key == 'lololo':
        return _lololo()
    if key == 'title':
        return _title_day()
    if key == 'title_night':
        return _title_night()
    if key == 'green_greens_extra':
        return _green_greens_twilight()
    h = 160
    ys = np.arange(h, dtype=np.float32)
    # sky: deep blue at the top to pale near the horizon, in flat bands
    sky = hx('#3a78e0', '#4a8cf0', '#64a6f6', '#86c4fa', '#acdcfc', '#d6f2ff')
    k = (_bands(0, 112, ys, len(sky) - 1) * (len(sky) - 1)).astype(int)
    grad = np.zeros((h, 160, 4), np.float32)
    grad[..., :3] = sky[k][:, None]
    grad[..., 3] = 1
    # a soft morning sun glow, fixed on screen (far away), top right
    yy, xx = np.mgrid[0:h, 0:160]
    d = np.hypot(xx - 128, yy - 18)
    glow = (d < 14) * 0.45 + (d < 20) * 0.2
    grad[..., :3] = grad[..., :3] * (1 - glow[..., None]) + hx('#fff6d0')[0] * glow[..., None]
    sun = d < 9
    grad[sun, :3] = hx('#fffbe8')[0]
    layers = [(grad, 0.0, 0.0)]
    # far mountains, hazy blue
    w = 640
    line = _profile(w, 92, 14, ((2, 1.0), (5, 0.5), (11, 0.25)), 1)
    layers.append((_silhouette(w, h, line, hx('#b4dcef')[0], hx('#cdeaf4')[0], hx('#e6f6fb')[0],
                               hx('#90bcd8')[0]), 0.1, 0.0))
    # high soft clouds
    layers.append((_clouds(768, h, 2, 9, 14, 60, hx('#ffffff')[0], hx('#dce6fb')[0], 0.9), 0.22, 0.0))
    # nearer rolling hills, fresh green
    w = 768
    line = _profile(w, 112, 9, ((3, 1.0), (7, 0.45), (13, 0.2)), 3)
    layers.append((_silhouette(w, h, line, hx('#8edca0')[0], hx('#6cc88c')[0], hx('#c6f2c8')[0],
                               hx('#4ca878')[0]), 0.35, 0.0))
    return layers
