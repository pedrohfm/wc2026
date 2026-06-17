"""
Prepare the dashboard for hosting as a static website.

Because outputs/dashboard.html is fully self-contained (data baked in, no
dependencies), "publishing" just means regenerating it and copying it to a
clean site/ folder named index.html — which every static host (GitHub Pages,
Netlify, Cloudflare Pages, Vercel, surge) serves directly.

    python scripts/publish.py            # build dashboard -> site/index.html
    python scripts/publish.py --git      # also commit & push site/ (if a git remote is set up)

Then point any host at the site/ folder (see HOSTING.md).
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SITE = os.path.join(ROOT, "site")


def main():
    # 1. regenerate the dashboard from the latest forecasts
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_dashboard.py")], check=True)

    # 2. assemble the static site folder
    os.makedirs(SITE, exist_ok=True)
    shutil.copy(os.path.join(ROOT, "outputs", "dashboard.html"), os.path.join(SITE, "index.html"))
    shutil.copy(os.path.join(ROOT, "outputs", "about.html"), os.path.join(SITE, "about.html"))
    open(os.path.join(SITE, ".nojekyll"), "w").close()   # tell GitHub Pages to serve as-is
    print(f"  site ready -> {os.path.relpath(os.path.join(SITE, 'index.html'), ROOT)}")

    # 3. optional git deploy
    if "--git" in sys.argv:
        import datetime as _dt
        try:
            subprocess.run(["git", "-C", ROOT, "add", "-A"], check=True)   # results, odds, forecast, site
            msg = "Update forecast & dashboard " + _dt.date.today().isoformat()
            r = subprocess.run(["git", "-C", ROOT, "commit", "-m", msg])
            if r.returncode != 0:
                print("  (nothing new to commit)")
            subprocess.run(["git", "-C", ROOT, "push"], check=True)
            print("  pushed to your git remote -> GitHub Pages will redeploy in ~1 min.")
        except subprocess.CalledProcessError as e:
            print(f"  [!] git step failed ({e}). Set up a repo + remote first (see HOSTING.md).")
    else:
        print("  next: see HOSTING.md to put site/ online (10-second option: drag it onto netlify.com/drop).")


if __name__ == "__main__":
    main()
