"""Stamp a new version on the site's JS and CSS so browsers never mix old and new files.

Browsers cache ES modules; after a change they can load a new main.js with an old stage.js.
index.html therefore loads every module through an import map that adds ?v=<version>, and the
stylesheet and entry script carry the same version. Run this after changing anything in js/ or
css/ (before pushing):

    python3 viz/bump_version.py
"""
import json
import re
from datetime import datetime
from pathlib import Path

VIZ = Path(__file__).resolve().parent
version = datetime.now().strftime("%Y%m%d%H%M")
modules = sorted(p.relative_to(VIZ).as_posix() for p in (VIZ / "js").rglob("*.js"))
imports = {f"./{m}": f"./{m}?v={version}" for m in modules}
block = ('<script type="importmap">\n' + json.dumps({"imports": imports}, indent=2) + "\n  </script>")

html = (VIZ / "index.html").read_text()
html = re.sub(r'<script type="importmap">.*?</script>\n  ', "", html, flags=re.S)
html = re.sub(r'<link rel="stylesheet" href="css/style\.css(\?v=\d+)?">', f'<link rel="stylesheet" href="css/style.css?v={version}">', html)
html = re.sub(r'<script type="module" src="js/main\.js(\?v=\d+)?"></script>',
              f'{block}\n  <script type="module" src="js/main.js?v={version}"></script>', html)
(VIZ / "index.html").write_text(html)
print(f"index.html: version {version}, {len(modules)} modules")
