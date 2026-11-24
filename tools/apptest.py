"""Run the app headless with timed key presses (talk to Oak, open the menu), then quit."""
import os, sys, time
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pygame
from ugb import app
K = pygame
script = [(0.3, 'down', K.K_RIGHT), (1.6, 'up', K.K_RIGHT), (1.7, 'down', K.K_UP), (3.8, 'up', K.K_UP),
          (7.0, 'down', K.K_z), (7.1, 'up', K.K_z), (8.5, 'down', K.K_z), (8.6, 'up', K.K_z),
          (10.0, 'down', K.K_TAB), (11.0, 'down', K.K_TAB), (13.0, 'down', K.K_ESCAPE)]
real_get = pygame.event.get
t0 = [None]
def fake_get():
    evs = real_get()
    if t0[0] is None:
        t0[0] = time.time()
    el = time.time() - t0[0]
    while script and script[0][0] <= el:
        _, kind, key = script.pop(0)
        evs.append(pygame.event.Event(pygame.KEYDOWN if kind == 'down' else pygame.KEYUP, key=key))
    return evs
pygame.event.get = fake_get
real_caption = pygame.display.set_caption
pygame.display.set_caption = lambda s: (print(s), real_caption(s))
sys.argv = ['app', os.environ.get('UGB_ROM', 'yellow'), '--state', os.environ.get('UGB_STATE', 'states/pallet_town.state'), '--no-save']
app.main()
