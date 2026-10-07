"""ポータルのブラウザ側の純粋な関数（portal/js/util.js）を node のテストで確かめる。"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node がないため省略")
def test_portal_util_js():
    r = subprocess.run(["node", "--test", "tests/portal_js/*.test.mjs"], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
