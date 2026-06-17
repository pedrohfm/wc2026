# Putting the dashboard online

The dashboard is one self-contained HTML file, so it's already a static website —
no server, database, or build step. `python scripts/publish.py` regenerates it
and copies it to `site/index.html`; point any host below at that folder (or that
file). Pick by how much you want to set up.

## Option A — instant share, zero setup (Netlify Drop)
Best for "send my friends a link" today.
1. `python scripts/publish.py`
2. Go to <https://app.netlify.com/drop> and **drag the `site/` folder** onto the page.
3. You get a public URL instantly (e.g. `random-name.netlify.app`). Done.
To update: drag the folder again (or connect the git repo for auto-deploys).

## Option B — a real, auto-updating site (GitHub Pages)  ← recommended
Best for a permanent URL that updates when you push.
1. Put the project in a GitHub repo (if it isn't already):
   `git init && git add . && git commit -m "init" && git branch -M main`
   then create a repo on github.com and `git remote add origin <url> && git push -u origin main`.
2. The included workflow `.github/workflows/pages.yml` deploys the `site/` folder.
   In the repo: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. From then on your update loop is:
   ```
   python scripts/publish.py --git     # build site/ + commit + push
   ```
   GitHub builds and serves it at `https://<username>.github.io/<repo>/` within a minute.

## Option C — drag-to-deploy with a dashboard (Cloudflare Pages / Vercel)
Similar to Netlify: create a project, connect the repo (or upload `site/`), set the
output directory to `site`. Free tier, custom domains supported.

## Option D — one command from the terminal (surge.sh)
```
npm install -g surge
cd site && surge          # pick a name; gives you name.surge.sh
```

## Option E — no hosting at all
Since it's a single file, you can just **send `outputs/dashboard.html`** to friends
(email, AirDrop, Slack). They double-click it and it opens in their browser — the
data is already inside. Nothing to install.

## Custom domain (make it feel official)
Any of A–C let you attach a domain you own (e.g. `myworldcupmodel.com`): buy one
(Namecheap, Cloudflare, Google Domains), then in the host's dashboard add the
domain and follow its DNS instructions. HTTPS is automatic on all of them.

---

## Two things to keep in mind

- **It's public.** Anyone with the URL sees it. That's fine — the dashboard holds
  only forecasts and public odds, no secrets. But **never commit your
  `ODDS_API_KEY`** (it's only ever an environment variable / CI secret, never in a
  file). A `.gitignore` is included that keeps caches and local junk out of the repo.
- **Updating = re-publish.** The site is a snapshot. Your daily loop becomes:
  ```
  python scripts/fetch_odds.py
  python scripts/build_and_forecast.py
  python scripts/publish.py --git       # rebuild + deploy (Option B)
  ```
  Want it to update on a schedule without you running anything? That's a CI job that
  runs the whole pipeline in the cloud — doable, but it needs your historical data and
  odds key wired in as repo secrets. Say the word and I'll set that up.
