"""Fallback for games without a preset: no game knowledge at all.

The renderer then works only from what any Game Boy game exposes: tile pixels,
palettes and sprites. See render.Enhancer's generic path.
"""
from ugb.fx import hx

TITLE = None
RAM = {}
TILESETS = {}
STAMPS = []
UI_FIRST_TILE = 256      # no text-box tiles known
RAMPS = {'neutral': hx('#202028', '#505060', '#8a8a98', '#c8c8d0', '#f4f4f8')}
SPRITE_SLOT = {}
SPRITE_PIC = {}
NPC_CYCLE = []
