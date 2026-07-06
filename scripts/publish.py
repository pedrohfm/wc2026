"""
Prepare the website for hosting in a clean site/ folder.

Two layers:
  * DATA — regenerated every run by build_dashboard.py into outputs/WCData.js
    (window.WC_DATA), which the design pages read for fresh forecasts.
  * DESIGN — the Claude-Design pages "Forecast Tracker.dc.html" and
    "Methodology.dc.html" plus support.js (the design runtime). These are static
    assets you only change when you redesign.

Deployment assembles site/ from the design pages + the fresh WCData.js, renaming
to clean URLs (index.html, methodology.html) and rewriting the cross-page links.
If the design files are absent it falls back to the legacy self-contained
dashboard, so nothing breaks either way.

    python scripts/publish.py            # build data + assemble site/
    python scripts/publish.py --git      # also commit & push (GitHub Pages)
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "outputs")
SITE = os.path.join(ROOT, "site")

TRACKER_SRC = os.path.join(OUT, "Forecast Tracker.dc.html")
METHOD_SRC = os.path.join(OUT, "Methodology.dc.html")
SUPPORT_SRC = os.path.join(OUT, "support.js")
WCDATA_SRC = os.path.join(OUT, "WCData.js")

# rewrite the design's internal links to the clean deployed filenames
LINK_FIXES = {"Forecast Tracker.dc.html": "index.html",
              "Forecast%20Tracker.dc.html": "index.html",
              "Methodology.dc.html": "methodology.html"}


def _write_fixed(src, dest):
    html = open(src, encoding="utf-8").read()
    for a, b in LINK_FIXES.items():
        html = html.replace(a, b)
    html = inject_pwa(html)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(html)


def deploy_new_design():
    # WCData.js is loaded by index.html with a runtime timestamp (?t=Date.now()),
    # so every page load / F5 fetches fresh data even from a cached HTML shell.
    # support.js (the design runtime) changes rarely -> content-hash cache-bust.
    import hashlib
    sver = hashlib.md5(open(SUPPORT_SRC, "rb").read()).hexdigest()[:10]
    html = open(TRACKER_SRC, encoding="utf-8").read()
    for a, b in LINK_FIXES.items():
        html = html.replace(a, b)
    html = html.replace('src="./support.js"', 'src="./support.js?v=%s"' % sver)
    html = html.replace('src="support.js"', 'src="support.js?v=%s"' % sver)
    html = inject_pwa(html)
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    _write_fixed(METHOD_SRC, os.path.join(SITE, "methodology.html"))
    shutil.copy(SUPPORT_SRC, os.path.join(SITE, "support.js"))
    shutil.copy(WCDATA_SRC, os.path.join(SITE, "WCData.js"))
    # keep old /about.html links alive -> redirect to the new methodology page
    with open(os.path.join(SITE, "about.html"), "w", encoding="utf-8") as f:
        f.write('<!doctype html><meta charset="utf-8">'
                '<meta http-equiv="refresh" content="0; url=methodology.html">'
                '<link rel="canonical" href="methodology.html">'
                '<a href="methodology.html">Methodology</a>')
    print("  deployed NEW design -> site/index.html, methodology.html, support.js, WCData.js")


# Vercel serves site/ as the project root (Root Directory = site). Pinning the
# config inside the folder means the Vercel dashboard settings can't drift out of
# sync (outputDirectory "." = this folder itself). Regenerated every build.
VERCEL_JSON = '''{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "outputDirectory": ".",
  "cleanUrls": true,
  "trailingSlash": false,
  "headers": [
    {
      "source": "/WCData.js",
      "headers": [{ "key": "Cache-Control", "value": "no-store, max-age=0" }]
    },
    {
      "source": "/index.html",
      "headers": [{ "key": "Cache-Control", "value": "no-cache" }]
    }
  ]
}
'''


def write_vercel_config():
    with open(os.path.join(SITE, "vercel.json"), "w", encoding="utf-8") as f:
        f.write(VERCEL_JSON)


# --- installable web-app (Add to Home Screen) --------------------------------
# Head tags injected into every page so iOS/Android treat the site as an app:
# custom icon, full-screen standalone launch, name, and theme colour.
PWA_HEAD = (
    '<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">'
    '<link rel="icon" type="image/png" sizes="512x512" href="/icons/icon-512.png">'
    '<link rel="icon" type="image/png" sizes="192x192" href="/icons/icon-192.png">'
    '<link rel="icon" type="image/png" sizes="64x64" href="/icons/favicon-64.png">'
    '<link rel="manifest" href="/manifest.webmanifest">'
    '<meta name="apple-mobile-web-app-capable" content="yes">'
    '<meta name="mobile-web-app-capable" content="yes">'
    '<meta name="apple-mobile-web-app-status-bar-style" content="default">'
    '<meta name="apple-mobile-web-app-title" content="WC2026">'
    '<meta name="theme-color" content="#1a1a1f">'
)

MANIFEST = '''{
  "name": "WC2026 Forecast Tracker",
  "short_name": "WC2026",
  "description": "FIFA World Cup 2026 Monte-Carlo forecast tracker",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "#f3f1ea",
  "theme_color": "#1a1a1f",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "/icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
'''


def inject_pwa(html):
    """Insert the installable-app head tags right before </head> (once)."""
    return html.replace("</head>", PWA_HEAD + "</head>", 1)


def write_pwa_assets():
    """Copy the committed app icons into site/icons/ and write the manifest."""
    icons_dir = os.path.join(SITE, "icons")
    os.makedirs(icons_dir, exist_ok=True)
    src = os.path.join(ROOT, "assets", "pwa")
    if os.path.isdir(src):
        for fn in os.listdir(src):
            if fn.endswith(".png"):
                shutil.copy(os.path.join(src, fn), os.path.join(icons_dir, fn))
    with open(os.path.join(SITE, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        f.write(MANIFEST)


def deploy_legacy():
    shutil.copy(os.path.join(OUT, "dashboard.html"), os.path.join(SITE, "index.html"))
    shutil.copy(os.path.join(OUT, "about.html"), os.path.join(SITE, "about.html"))
    print("  [!] design files not found -> deployed LEGACY self-contained dashboard.")


def main():
    # 1. regenerate the data (WCData.js) + legacy fallback
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_dashboard.py")], check=True)

    # 2. assemble site/
    os.makedirs(SITE, exist_ok=True)
    have_design = all(os.path.exists(p) for p in (TRACKER_SRC, METHOD_SRC, SUPPORT_SRC, WCDATA_SRC))
    if have_design:
        deploy_new_design()
    else:
        deploy_legacy()
    open(os.path.join(SITE, ".nojekyll"), "w").close()   # serve as-is on GitHub Pages
    write_vercel_config()                                # pin Vercel static config
    write_pwa_assets()                                   # app icons + manifest
    print(f"  site ready -> {os.path.relpath(SITE, ROOT)}/")

    # 3. optional git deploy
    if "--git" in sys.argv:
        import datetime as _dt
        try:
            subprocess.run(["git", "-C", ROOT, "add", "-A"], check=True)
            msg = "Update forecast & site " + _dt.date.today().isoformat()
            r = subprocess.run(["git", "-C", ROOT, "commit", "-m", msg])
            if r.returncode != 0:
                print("  (nothing new to commit)")
            subprocess.run(["git", "-C", ROOT, "push"], check=True)
            print("  pushed to your git remote -> GitHub Pages will redeploy in ~1 min.")
        except subprocess.CalledProcessError as e:
            print(f"  [!] git step failed ({e}). Set up a repo + remote first (see HOSTING.md).")
    else:
        print("  next: see HOSTING.md to put site/ online.")


if __name__ == "__main__":
    main()
