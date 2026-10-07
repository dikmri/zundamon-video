"""同梱の Claude Code スキル（skill/zundamon-video）を ~/.claude/skills へ入れる。

    uv run python -m zvideo.install_skill            # ~/.claude/skills/zundamon-video に入れる
    uv run python -m zvideo.install_skill --dest <dir>

SKILL.md の {{ZVIDEO_HOME}} を、このリポジトリの場所に置き換えて書き出す。
"""
import argparse
import shutil
from pathlib import Path

from .log import log
from .paths import ROOT

PLACEHOLDER = "{{ZVIDEO_HOME}}"


def install(dest):
    src = ROOT / "skill" / "zundamon-video"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    for md in dest.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        if PLACEHOLDER in text:
            md.write_text(text.replace(PLACEHOLDER, str(ROOT)), encoding="utf-8")
    log("install_skill", {"dest": str(dest)}, f"home={ROOT}")
    return dest


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=str(Path.home() / ".claude" / "skills" / "zundamon-video"))
    a = ap.parse_args(argv)
    dest = install(Path(a.dest))
    print("installed:", dest)


if __name__ == "__main__":
    main()
