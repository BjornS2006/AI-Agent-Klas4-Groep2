import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent  # goes up from tools/ to project root
PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
CONFIG = Path(__file__).parent / "config.ini"

subprocess.Popen([str(PYTHON), "-m", "radicale", "--config", str(CONFIG), "--hosts", "127.0.0.1:5232"])