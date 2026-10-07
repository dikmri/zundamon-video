"""プロジェクト相対のパス定義。既定のユーザーディレクトリには何も置かない。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime"
LOGS = ROOT / "logs"
ASSETS = ROOT / "assets"
CHARACTERS = ASSETS / "characters"
TEMPLATE = ROOT / "template"
PROJECTS = ROOT / "projects"
OUT = ROOT / "out"
CACHE = RUNTIME / "cache"
VOICEVOX_DIR = RUNTIME / "voicevox" / "windows-cpu"
SOZAI_SRC = RUNTIME / "sozai_src"
PLAYWRIGHT_BROWSERS = RUNTIME / "ms-playwright"
