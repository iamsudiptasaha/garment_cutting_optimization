"""Standalone single-file viewer: full-length original vector with simple zoom controls."""
from __future__ import annotations

from base64 import b64encode
from html import escape
from pathlib import Path
from xml.etree import ElementTree as ET


def export_viewer(source_svg: str | Path, destination: str | Path) -> Path:
    """Embed the complete SVG as an image, without any external dependencies."""
    source = Path(source_svg)
    root = ET.parse(source).getroot()
    width = root.get("data-fabric-width-in")
    length = root.get("data-fabric-length-in")
    if not width or not length:
        raise ValueError("The source must be an annotated nesting SVG")
    title = escape(f"Fabric {width} in × {length} in")
    encoded = b64encode(source.read_bytes()).decode("ascii")
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — Cutting Layout</title>
<style>
* {{ box-sizing: border-box; }}
html,body {{ margin:0; height:100%; font-family:system-ui,Arial,sans-serif; }}
body {{ display:flex; flex-direction:column; background:#e7eef1; color:#132932; }}
header {{ display:flex; align-items:center; flex-wrap:wrap; gap:8px; padding:10px;
  background:#fff; border-bottom:1px solid #bbcbd1; }}
strong {{ font-size:14px; margin-right:auto; }}
button {{ font-size:19px; min-width:46px; min-height:44px; padding:5px 12px;
  background:#fff; color:#172c37; border:1px solid #8ba9b6; border-radius:7px; }}
button:active {{ background:#dbeaf0; }}
#viewport {{ flex:1; overflow:auto; overscroll-behavior:contain; text-align:left;
  -webkit-overflow-scrolling:touch; }}
#layout {{ display:block; height:auto; max-width:none; margin:12px; background:#fff; }}
small {{ display:block; padding:5px 10px; font-size:12px; background:#fff; }}
</style>
</head>
<body>
<header>
<strong>{title}</strong>
<button id="minus" aria-label="Zoom out">−</button>
<button id="plus" aria-label="Zoom in">+</button>
<button id="fit">Fit</button>
</header>
<div id="viewport">
<img id="layout" alt="Continuous garment cutting layout"
 src="data:image/svg+xml;base64,{encoded}">
</div>
<small>Use + to read labels. Swipe to move along the continuous layout. No internet required.</small>
<script>
(() => {{
  const viewport = document.getElementById("viewport");
  const image = document.getElementById("layout");
  let zoom = 1;
  function fitWidth() {{ return Math.max(240, viewport.clientWidth - 24); }}
  function redraw(previous) {{
    const old = Math.max(1, fitWidth() * previous);
    const scale = zoom / previous;
    const cx = viewport.scrollLeft + viewport.clientWidth / 2;
    const cy = viewport.scrollTop + viewport.clientHeight / 2;
    image.style.width = Math.round(fitWidth() * zoom) + "px";
    if (scale !== 1) {{
      viewport.scrollLeft = cx * scale - viewport.clientWidth / 2;
      viewport.scrollTop = cy * scale - viewport.clientHeight / 2;
    }}
  }}
  document.getElementById("plus").onclick = () => {{
    const old = zoom; zoom = Math.min(16, zoom * 1.7); redraw(old);
  }};
  document.getElementById("minus").onclick = () => {{
    const old = zoom; zoom = Math.max(1, zoom / 1.7); redraw(old);
  }};
  document.getElementById("fit").onclick = () => {{
    const old = zoom; zoom = 1; redraw(old); viewport.scrollLeft = 0;
  }};
  window.addEventListener("resize", () => redraw(zoom));
  redraw(1);
}})();
</script>
</body>
</html>
"""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    return target
