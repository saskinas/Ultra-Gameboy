"""Ultra Game Boy's front door for players: a small window to pick a game and
play it. The packaged app (tools/build_windows.py) starts here.

It remembers the last few games (recent.json in the data folder, see
ugb.paths), shows the controls, and opens the game in the usual player
(ugb.app). Errors go to a message box and to error.log there.
"""
import json
import os
import sys
import traceback

from ugb.paths import data_dir, data_path

CONTROLS = (
    'Arrow keys - move        Z - A button        X - B button\n'
    'Enter - Start        Backspace - Select\n'
    'Tab - original / enhanced look        E - effects on / off\n'
    'Space (hold) - fast forward\n'
    'F2 - quick save        F4 - quick load        F12 - screenshot\n'
    'Esc - quit (your in-game save is kept)'
)


def _recent_file():
    return os.path.join(data_dir(), 'recent.json')


def load_recent():
    try:
        with open(_recent_file(), encoding='utf-8') as f:
            return [p for p in json.load(f) if os.path.exists(p)]
    except (OSError, ValueError):
        return []


def remember(path):
    games = [path] + [p for p in load_recent() if os.path.normcase(p) != os.path.normcase(path)]
    with open(_recent_file(), 'w', encoding='utf-8') as f:
        json.dump(games[:8], f, indent=1)


def pick_game():
    """Show the picker; the chosen ROM's path, or None if the window was closed."""
    import tkinter as tk
    from tkinter import filedialog

    chosen = {'path': None}
    root = tk.Tk()
    root.title('Ultra Game Boy')
    root.resizable(False, False)
    pad = dict(padx=14, pady=6)

    tk.Label(root, text='Ultra Game Boy', font=('Segoe UI', 18, 'bold')).pack(**pad)
    tk.Label(root, text='Play your Game Boy and Game Boy Color games with a 16-bit look.\n'
                        'Choose a game file you own (.gb or .gbc).',
             justify='center').pack(**pad)

    recent = load_recent()
    box = tk.Listbox(root, width=60, height=min(max(len(recent), 3), 8), activestyle='dotbox')
    for p in recent:
        box.insert('end', os.path.basename(p))
    if recent:
        tk.Label(root, text='Recent games:', anchor='w').pack(fill='x', padx=14)
        box.pack(padx=14)
        box.selection_set(0)

    def play(path):
        chosen['path'] = path
        root.destroy()

    def choose():
        path = filedialog.askopenfilename(
            title='Choose a Game Boy game',
            filetypes=[('Game Boy games', '*.gb *.gbc *.GB *.GBC'), ('All files', '*.*')])
        if path:
            play(path)

    def play_selected(_=None):
        sel = box.curselection()
        if sel:
            play(recent[sel[0]])

    box.bind('<Double-Button-1>', play_selected)
    row = tk.Frame(root)
    row.pack(**pad)
    tk.Button(row, text='Choose a game...', width=18, command=choose).pack(side='left', padx=6)
    play_btn = tk.Button(row, text='Play', width=12, command=play_selected,
                         state='normal' if recent else 'disabled')
    play_btn.pack(side='left', padx=6)
    root.bind('<Return>', play_selected)

    tk.Label(root, text=CONTROLS, justify='left', fg='#444', font=('Segoe UI', 9)).pack(padx=14, pady=(8, 4))
    tk.Label(root, text='Saves, quick saves and screenshots are kept in:\n' + data_dir(),
             justify='center', fg='#777', font=('Segoe UI', 8)).pack(padx=14, pady=(0, 10))
    root.mainloop()
    return chosen['path']


def _report(exc_text):
    with open(data_path('error.log'), 'a', encoding='utf-8') as f:
        f.write(exc_text + '\n')
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror('Ultra Game Boy',
                             'Something went wrong:\n\n' + exc_text.strip().splitlines()[-1]
                             + '\n\nDetails are in ' + data_path('error.log'))
        r.destroy()
    except Exception:
        pass


def main():
    path = sys.argv[1] if len(sys.argv) > 1 and os.path.exists(sys.argv[1]) else None
    if path is None:
        path = pick_game()
        if not path:
            return
    try:
        remember(path)
        from ugb import app
        sys.argv = [sys.argv[0], path]
        app.main()
    except SystemExit:
        pass
    except Exception:
        _report(traceback.format_exc())


if __name__ == '__main__':
    main()
