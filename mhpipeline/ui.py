"""Terminal UI helpers: banner, colored messages, prompts, confirms, numeric
menu, and the overwrite-warning block. Thin wrappers over ``art`` + ``colorama``
so the rest of the wrapper stays presentation-free.
"""

import sys

from art import tprint
from colorama import Fore, Style
from colorama import init as _colorama_init

_colorama_init()

YELLOW = Fore.YELLOW
GREEN = Fore.GREEN
RED = Fore.RED
CYAN = Fore.CYAN
RESET = Fore.RESET
BRIGHT = Style.BRIGHT
NORMAL = Style.NORMAL


def banner(text="MH SAVE CONVERT"):
    tprint(text, font="tarty1")


def info(msg):
    print(f"{GREEN}[i]{RESET} {msg}")


def warn(msg):
    print(f"{YELLOW}[!]{RESET} {msg}")


def error(msg):
    print(f"{RED}[x]{RESET} {msg}")


def prompt(msg):
    """Read a line; Ctrl-C / EOF exits cleanly."""
    try:
        return input(f"{CYAN}{msg}{RESET} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def confirm(msg, default=False):
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        ans = prompt(f"{msg} {suffix}").lower()
        if not ans:
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        warn("Please answer y or n.")


def menu(title, options):
    """Render a numbered menu and return the chosen 1-based index.

    ``options`` is a list of label strings.
    """
    while True:
        print()
        print(f"{BRIGHT}{title}{RESET}")
        for i, label in enumerate(options, 1):
            print(f"  [{YELLOW}{i}{RESET}] {label}")
        raw = prompt(">")
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw)
        warn(f"Enter a number between 1 and {len(options)}.")


def overwrite_warning(target_desc):
    """Loud, unmissable warning before any destructive in-place write."""
    line = "=" * 64
    print()
    print(f"{RED}{BRIGHT}{line}{RESET}")
    print(f"{RED}{BRIGHT}  WARNING — this will OVERWRITE your existing save:{RESET}")
    print(f"{RED}{BRIGHT}    {target_desc}{RESET}")
    print(f"{RED}{BRIGHT}{line}{RESET}")
    print(f"{YELLOW}  A timestamped backup is taken automatically first, but you")
    print(f"  should ALSO keep your own backup before continuing.{RESET}")
    print(f"{RED}{BRIGHT}{line}{RESET}")
    print()
