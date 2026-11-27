"""Ultra Game Boy for players: opens the game picker (ugb.launcher).

Double-click the packaged app, or run `python UltraGameBoy.py [game.gb]`.
"""
import multiprocessing

if __name__ == '__main__':
    # (the packaged app runs its background workers as copies of itself)
    multiprocessing.freeze_support()
    from ugb.launcher import main
    main()
