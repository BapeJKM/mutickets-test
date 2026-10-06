import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
        cwd=ROOT,
    )
    code = subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
