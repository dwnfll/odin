# The Odin Project — Japanese translation, local viewer

This folder holds the tooling to view an in-progress Japanese translation of The Odin
Project curriculum locally, without needing Rails, Postgres, Docker, or a GitHub token.

It does **not** contain the curriculum content or the site itself — those are two
separate git repos, cloned as siblings of this folder. This folder just holds the glue:
[build_site.py](build_site.py), which reads both repos and generates a static HTML site
you can open in a browser.

## Setup (fresh clone)

Requires Python 3.9+ and Git.

1. Clone the two content repos as siblings of this folder (i.e. `curriculum_ja/` and
   `theodinproject_ja/` end up next to `build_site.py`, not inside this repo):
   ```bash
   git clone https://github.com/dwnfll/curriculum_ja.git
   git clone https://github.com/dwnfll/theodinproject_ja.git
   ```
2. Install the one Python dependency:
   ```bash
   pip install -r requirements.txt
   ```
3. Build the site:
   ```bash
   python build_site.py
   ```
4. Open `site/index.html` directly in a browser, or serve it so relative links behave
   normally:
   ```bash
   python -m http.server 8000 --directory site
   ```
   then visit `http://localhost:8000/`.

Re-run `python build_site.py` any time after pulling new translations (in `curriculum_ja`)
or new upstream content (in either repo) — it's fast and safe to run repeatedly; it always
rebuilds `site/` from the current contents of both repos.

## What's tracked where

- **This folder** (its own git repo, `odin/`): `build_site.py`, `requirements.txt`, this
  README, and [TRANSLATION_PLAN_JA.md](TRANSLATION_PLAN_JA.md) (the full translation
  runbook — process, style rules, scope, architecture notes). `site/` (generated output)
  and the two cloned repos are gitignored here — see `.gitignore`.
- **`curriculum_ja/`** (separate repo, fork of `TheOdinProject/curriculum`): the English
  curriculum content, plus the Japanese translations under `curriculum_ja/ja/` — that's
  where translation work actually gets committed. Also holds
  [curriculum_ja/ja/GLOSSARY.md](curriculum_ja/ja/GLOSSARY.md) and
  [curriculum_ja/ja/MANIFEST.md](curriculum_ja/ja/MANIFEST.md) (translation progress
  tracker).
- **`theodinproject_ja/`** (separate repo, fork of `TheOdinProject/theodinproject`): the
  Rails site, used here read-only as the source of course/section/lesson structure (see
  `db/fixtures/`). Nothing in it is ever modified by this project.

## For translators / agents

See [TRANSLATION_PLAN_JA.md](TRANSLATION_PLAN_JA.md) for the full process, scope,
style/terminology rules, and current status.
