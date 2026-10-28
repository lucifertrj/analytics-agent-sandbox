import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

LLM_MODEL = "gemini-3.5-flash-lite"
SANDBOX_BACKEND = os.getenv("SANDBOX_BACKEND", "subprocess")

CPU_SECONDS = 15
FSIZE_BYTES = 64 * 1024 * 1024
WALL_TIMEOUT = 20

DAYTONA_REMOTE_DIR = "/home/daytona"

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_CSV = DATA_DIR / "sales_data.csv"
