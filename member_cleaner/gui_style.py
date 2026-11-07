"""Shared Tkinter appearance for the main window and batch review screens.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Keep the application's color, typography and control states in
one place, using only the Tk widgets bundled with Python.

AI disclosure: This code was generated with OpenAI ChatGPT for developer
review and adaptation.
"""

import tkinter as tk
from tkinter import font, ttk


PAGE = "#f0f4f8"
SURFACE = "#ffffff"
INK = "#172c45"
MUTED = "#4c6177"
BORDER = "#b6c4d3"
ACCENT = "#20569a"
INFO_BG = "#e7f0fc"
SUCCESS_BG = "#e3f3eb"
SUCCESS_INK = "#17583d"
PRIMARY_BUTTON = "Primary.TButton"


def configure_theme(root: tk.Misc) -> None:
    """Use a bundled theme that honors color and keyboard focus on Windows."""
    style = ttk.Style(root)
    style.theme_use("clam")
    default = font.nametofont("TkDefaultFont", root=root)
    family = default.actual("family")
    size = max(10, default.actual("size"))
    default.configure(size=size)
    bold = (family, size, "bold")
    heading = (family, size + 3, "bold")
    root.configure(background=PAGE)

    style.configure(".", font="TkDefaultFont", background=SURFACE, foreground=INK,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    style.configure("Page.TFrame", background=PAGE)
    style.configure("Title.TLabel", background=PAGE, font=(family, size + 9, "bold"))
    style.configure("Subtitle.TLabel", background=PAGE, foreground=MUTED)
    style.configure("Heading.TLabel", font=heading)
    style.configure("Strong.TLabel", font=bold)
    style.configure("Notice.TLabel", background=PAGE, font=bold)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("TLabelframe", relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", font=bold)
    for name, background, foreground in (
        ("Info", INFO_BG, INK), ("Success", SUCCESS_BG, SUCCESS_INK),
    ):
        style.configure(f"{name}.TFrame", background=background)
        style.configure(f"{name}.TLabel", background=background, foreground=foreground)
        style.configure(f"{name}.Heading.TLabel", background=background,
                        foreground=foreground, font=heading)

    for name, normal, hover, pressed, foreground in (
        ("TButton", SURFACE, INFO_BG, "#d6e5f7", INK),
        (PRIMARY_BUTTON, ACCENT, "#194781", "#123666", SURFACE),
    ):
        style.configure(name, background=normal, foreground=foreground, padding=(10, 5),
                        focusthickness=2, focuscolor=foreground)
        style.map(name,
                  background=[("disabled", "#e8edf3"), ("pressed", pressed), ("active", hover)],
                  foreground=[("disabled", "#5f7186")],
                  bordercolor=[("disabled", BORDER), ("focus", ACCENT)],
                  lightcolor=[("disabled", BORDER), ("!disabled", normal)],
                  darkcolor=[("disabled", BORDER), ("!disabled", normal)])

    for name in ("TEntry", "TCombobox"):
        style.configure(name, padding=(6, 4), fieldbackground=SURFACE,
                        selectbackground=ACCENT, selectforeground=SURFACE)
        style.map(name, fieldbackground=[("disabled", "#e8edf3"), ("readonly", SURFACE)],
                  foreground=[("disabled", "#5f7186")],
                  bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
                  darkcolor=[("focus", ACCENT)])
    root.option_add("*TCombobox*Listbox.font", "TkDefaultFont")
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", SURFACE)

    style.configure("Treeview", fieldbackground=SURFACE, rowheight=default.metrics("linespace") + 7)
    style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", SURFACE)])
    style.configure("Treeview.Heading", font=bold, background=INFO_BG,
                    padding=(6, 5), relief="flat")
    style.configure("TScrollbar", background="#d1dbe6", troughcolor=PAGE,
                    arrowcolor=MUTED, arrowsize=12)
    style.configure("TNotebook.Tab", padding=(12, 6))
    style.map("TNotebook.Tab", background=[("selected", SURFACE), ("!selected", PAGE)])


def style_text(widget: tk.Text) -> None:
    """Match a text pane (including ScrolledText) to the surrounding controls."""
    widget.configure(font="TkDefaultFont", background=SURFACE, foreground=INK,
                     selectbackground=ACCENT, selectforeground=SURFACE, insertbackground=INK,
                     relief="flat", borderwidth=0, highlightthickness=1,
                     highlightbackground=BORDER, highlightcolor=ACCENT, padx=8, pady=6)
