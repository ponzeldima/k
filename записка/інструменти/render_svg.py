"""SVG -> PNG через headless Chrome (масштаб 3×) для рисунків записки.

Запуск: python render_svg.py рисунок.svg [рисунок.png]
Шлях до Chrome можна задати змінною середовища CHROME.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = os.environ.get("CHROME", r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def render(svg: Path, out: Path, scale: int = 3) -> None:
    head = svg.read_text(encoding="utf-8")[:400]
    w, h = map(float, re.search(r'width="([\d.]+)" height="([\d.]+)"', head).groups())
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "svg.html"
        html.write_text(f'<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;padding:0;'
                        f'background:#fff}}img{{display:block}}</style></head><body><img src="{svg.as_uri()}" '
                        f'width="{w:g}" height="{h:g}"></body></html>', encoding="utf-8")
        profile = Path(tmp) / "profile"
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                        f"--force-device-scale-factor={scale}", f"--window-size={int(w)},{int(h)}",
                        f"--screenshot={out}", "--allow-file-access-from-files", html.as_uri()],
                       check=True, capture_output=True, timeout=120)


def main() -> None:
    svg = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else svg.with_suffix(".png")
    render(svg, out)
    print(f"-> {out}")


if __name__ == "__main__":
    main()
