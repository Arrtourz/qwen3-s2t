"""Smart paste: terminal detection, multiline handling, Wayland/X11 support."""

import os
import subprocess
import time


def _find_tool(name: str):
    import shutil, sys
    found = shutil.which(name)
    if found:
        return found
    conda_bin = os.path.join(os.path.dirname(sys.executable), name)
    if os.path.isfile(conda_bin):
        return conda_bin
    return None


def _session_type() -> str:
    return os.environ.get('XDG_SESSION_TYPE', '').lower()



def _is_terminal() -> bool:
    """Return True if the active window belongs to a terminal emulator."""
    try:
        xdotool = _find_tool('xdotool')
        if not xdotool:
            return False
        win_id = subprocess.run(
            [xdotool, 'getactivewindow'],
            capture_output=True, text=True, timeout=0.5,
        ).stdout.strip()
        if not win_id:
            return False

        # WM_CLASS: check if Electron IDE (Cursor/VSCode)
        cls = subprocess.run(
            ['xprop', '-id', win_id, 'WM_CLASS'],
            capture_output=True, text=True, timeout=0.5,
        ).stdout.lower()

        return any(k in cls for k in ('term', 'console', 'kitty', 'alacritty',
                                       'tilix', 'hyper', 'wezterm',
                                       'cursor', 'code', 'codium'))
    except Exception:
        return False


def _set_clipboard(text: str):
    xclip = _find_tool('xclip')
    if xclip:
        subprocess.run([xclip, '-selection', 'clipboard'],
                       input=text.encode('utf-8'), check=True)
        return
    xsel = _find_tool('xsel')
    if xsel:
        subprocess.run([xsel, '--clipboard', '--input'],
                       input=text.encode('utf-8'), check=True)
        return
    raise RuntimeError('Neither xclip nor xsel found')


def _press_key(combo: str):
    """Simulate a key combo via xdotool (X11) or wtype (Wayland)."""
    if _session_type() == 'wayland':
        parts = combo.split('+')
        args = ['wtype']
        for p in parts[:-1]:
            args += ['-M', p]
        args += ['-k', parts[-1]]
        for p in parts[:-1]:
            args += ['-m', p]
        subprocess.run(args, check=False)
    else:
        xdotool = _find_tool('xdotool')
        if xdotool:
            subprocess.run([xdotool, 'key', '--clearmodifiers', combo], check=False)


def _paste_block(text: str, terminal: bool):
    _set_clipboard(text)
    time.sleep(0.05)
    _press_key('ctrl+shift+v' if terminal else 'ctrl+v')


def paste_text(text: str):
    """Paste text into the active window with smart strategy."""
    terminal = _is_terminal()

    if terminal or '\n' not in text:
        _paste_block(text, terminal)
        return

    # Multiline in non-terminal: paste line by line with Shift+Return
    # to avoid accidental submit in chat apps (Slack, Teams, etc.)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line:
            _paste_block(line, terminal=False)
        if i < len(lines) - 1:
            time.sleep(0.03)
            _press_key('shift+Return')
            time.sleep(0.02)
