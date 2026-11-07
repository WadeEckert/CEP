"""Build the Member CSV Cleaner and prepare the Windows handoff ZIP.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Run the project's tests, bundle the GUI with its Python and Tk
runtime, and ship the editable template and practice file beside the app.

AI disclosure: This build script was generated with OpenAI ChatGPT for
developer review and adaptation.
"""

from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import venv
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
APP_NAME = "Member_CSV_Cleaner"
PYINSTALLER = "pyinstaller==6.22.3"
HANDOFF_FILES = ("README.txt", "crm_template.csv", "fictional_members_practice.csv")


def run(*command: str) -> None:
    """Stop on an error so the next build step cannot use an incomplete result."""
    subprocess.run(command, cwd=ROOT, check=True)


def verify_windows_executable(path: Path) -> None:
    """Check the generated file has a Windows executable header."""
    with path.open("rb") as file:
        if file.read(2) != b"MZ":
            raise ValueError("The build did not produce a Windows executable.")
        file.seek(0x3C)
        offset = int.from_bytes(file.read(4), byteorder="little")
        file.seek(offset)
        if file.read(4) != b"PE\x00\x00":
            raise ValueError("The build did not produce a valid Windows executable header.")


def make_release(executable: Path, handoff: Path, output: Path) -> Path:
    """Write the four handoff files together without replacing an earlier build."""
    verify_windows_executable(executable)
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="zip-", dir=output) as temporary:
        archive_path = Path(temporary) / "handoff.zip"
        with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
            archive.write(executable, arcname=f"{APP_NAME}.exe")
            for name in HANDOFF_FILES:
                archive.write(handoff / name, arcname=name)
        with ZipFile(archive_path) as archive:
            damaged_file = archive.testzip()
            if damaged_file is not None:
                raise ValueError(f"The handoff ZIP could not be verified: {damaged_file}")

        sequence = 1
        while True:
            suffix = "" if sequence == 1 else f"_{sequence}"
            destination = output / f"{APP_NAME}_Windows{suffix}.zip"
            if not destination.exists():
                try:
                    # On Windows, rename fails if the destination already exists.
                    return archive_path.rename(destination)
                except FileExistsError:
                    pass
            sequence += 1


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Run this build kit with Python on Windows to create the .exe.")
    if not (3, 10) <= sys.version_info[:2] < (3, 16):
        raise SystemExit("Use Python 3.10 through 3.15 on Windows for this build kit.")

    handoff = ROOT / "handoff"
    required = (ROOT / "main.py", *(handoff / name for name in HANDOFF_FILES))
    for path in required:
        if not path.is_file():
            raise SystemExit(f"Missing {path.relative_to(ROOT)}. Extract the full build kit and try again.")

    print("Checking Tk and running the project tests...", flush=True)
    # Fail early if this Windows Python installation cannot create a window.
    run(sys.executable, "-c", "import tkinter as tk; root = tk.Tk(); root.destroy()")
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests")

    # Build in a fresh environment so unrelated packages do not get bundled.
    with TemporaryDirectory(prefix="member-csv-build-") as temporary:
        build = Path(temporary)
        print("Installing the build tool in a temporary Python environment...", flush=True)
        environment = build / "venv"
        venv.create(environment, with_pip=True)
        python = str(environment / "Scripts" / "python.exe")
        run(python, "-m", "pip", "install", "--disable-pip-version-check", PYINSTALLER)

        print("Building the standalone Windows executable...", flush=True)
        dist = build / "dist"
        run(
            python, "-m", "PyInstaller", "--noconfirm", "--clean", "--noupx",
            "--onefile", "--windowed", "--name", APP_NAME,
            "--distpath", str(dist), "--workpath", str(build / "work"),
            "--specpath", str(build), str(ROOT / "main.py"),
        )
        release = make_release(dist / f"{APP_NAME}.exe", handoff, ROOT / "release")

    print(f"\nCreated: {release}")
    print("Extract that ZIP and launch the .exe for the check in BUILD_ON_WINDOWS.txt.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Build stopped: {error}") from None
