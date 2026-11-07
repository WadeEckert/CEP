"""Start the Member CSV Cleaner desktop application.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Create the application window and start its event loop. Keep
startup separate from the GUI and the member-data business rules.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

import tkinter as tk

from member_cleaner.gui import MemberCleanerApp


def main() -> None:
    """Create one root window and keep it responsive until the user closes it."""
    root = tk.Tk()
    MemberCleanerApp(root)
    root.mainloop()


if __name__ == "__main__":
    # Importing this module for inspection must not launch a desktop window.
    main()
