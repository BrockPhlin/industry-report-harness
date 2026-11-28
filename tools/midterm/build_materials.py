"""Build the submitted design report and presentation from their editable sources."""
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main():
    for script in ("build_design_report.py", "build_deck.py"):
        subprocess.run([sys.executable, str(HERE / script)], cwd=HERE.parents[1], check=True)


if __name__ == "__main__":
    main()
