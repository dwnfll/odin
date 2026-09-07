# The Odin Project — Japanese Translation Plan (日本語版)

A runbook for translating the `curriculum_ja` content into Japanese and viewing it locally.
Written so a fresh agent can execute it start-to-finish and resume mid-way.

> **DECIDED BY USER (do not re-ask):**
> 1. **Titles/nav → keep English; translate bodies only.** Do NOT translate `title` fields in the
>    fixture files. This avoids all slug/routing/unique-key issues. Only translate `description`
>    fields (display-only) and the lesson Markdown bodies. See §4d.
> 2. **External resources → translate readable articles for LOCAL VIEWING ONLY.** Mirror & translate
>    into `curriculum_ja/ja/resources/`, served locally, never republished — regardless of whether the
>    curriculum lesson translations themselves ever get published upstream. Videos/images stay as links.
>    Keep source/license/date attribution on each mirrored file. See §3.
> 3. **Rendering approach → lightweight static site, NOT the Rails app.** This machine has no Docker,
>    Ruby, or Postgres installed. The user chose "just build it and run the output html files" for this
>    private, local-only use. See §4 — the Rails/Docker path is kept only as a documented alternative.
> 4. **Scope (revised 2026-09-06) → translate everything EXCEPT `archive/`, `ruby/`, `ruby_on_rails/`.**
>    This superseded an earlier, narrower 6-course list once the workspace was reset to current upstream
>    (see §0 and the "2026-09-06 reset" note below) — that old list named courses (e.g. `html_css`) that
>    no longer exist under those names.
> 5. **`nodeJS` is deferred (skip it for now) — user instruction, 2026-09-06.** Still in scope long-term
>    (not excluded like archive/ruby/ruby_on_rails), just not being actively translated in this pass. Do
>    not spend translation effort on `nodeJS/` until the user says to resume it. See §5 Phase 7 and
>    MANIFEST.md's nodeJS section header.

**Status as of 2026-09-06: starting over after a workspace reset.** `curriculum/` and `theodinproject/`
(2020-era stale forks) were deleted entirely and replaced with fresh, current clones named `curriculum_ja/`
and `theodinproject_ja/` (forks at `github.com/dwnfll`). Everything that lived only in the old `curriculum/`
repo (translated lesson files, `GLOSSARY.md`, `MANIFEST.md`, `resources/README.md`) was lost with it — this
plan document is the only thing carried over, and has now been rewritten to match the new repos, the new
scope, and upstream's new content architecture (§0). **Net effect: zero lessons are translated; Phase 0/1
have been redone from scratch against the new repos and are done again; Phase 2 (translating content)
has not started.** `build_site.py` (repo root) has been rewritten for the new architecture, tested, and
verified against all 197 in-scope lessons — see §4 and §5.

---

## 0. Context an executing agent must load first

Two sibling repos live under `C:\Users\Zain\Documents\Programming\odin\`:

- `curriculum_ja/` — the lesson content (Markdown), a fresh clone tracking current upstream
  (`TheOdinProject/curriculum`) as of 2026-09-05, forked as `github.com/dwnfll/curriculum_ja`.
  **Scope: translate every course folder except `archive/`, `ruby/`, `ruby_on_rails/`.** Concretely,
  via the fixture structure below, that resolves to 8 courses / 197 lessons:
  `foundations` (46), `intermediate_html_css` (22), `advanced_html_css` (16), `javascript` (41),
  `react` (25), `databases` (3), `nodeJS` (30), `getting_hired` (14). `git/` and `shared/` are not
  separate top-level courses — their lessons are pulled inline into the courses above (e.g. Foundations'
  "Git Basics" section) and get translated as part of whichever course references them.
  `templates/`, `markdownlint/`, and the repo-meta files (`README.md`, `CONTRIBUTING.md`,
  `LAYOUT_STYLE_GUIDE.md`, `legal_terms_of_use.md`, `license.md`) are not rendered lessons — treat as
  out of scope unless the user says otherwise.
- `theodinproject_ja/` — the Rails site that renders the content, same fork family, tracking current
  upstream (`TheOdinProject/theodinproject`) as of 2026-09-04.

**How the site actually gets its content (verified 2026-09-06, do not assume — this changed since the
last time this was checked):**

Upstream **no longer** defines course/section/lesson structure via `db/seeds/*_course_seeds.rb` files
(that mechanism is gone entirely — `db/seeds/` now only holds unrelated seed data like
`feature_flags.rb`/`success_stories.rb`). It's been replaced with a two-layer fixture system under
`theodinproject_ja/db/fixtures/`:

1. **`db/fixtures/lessons/<family>_lessons.rb`** — each defines a Ruby method (e.g. `foundation_lessons`)
   returning a flat hash: `'Lesson Key' => { title:, description:, is_project:, github_path:,
   identifier_uuid: }`. `github_path` is the old seed `url` field's replacement — a curriculum-repo-
   relative path, e.g. `/foundations/introduction/how_this_course_will_work.md`. One file per content
   family: `foundation_lessons.rb`, `git_lessons.rb`, `html_and_css_lessons.rb`, `javascript_lessons.rb`,
   `node_js_lessons.rb`, `react_lessons.rb`, `database_lessons.rb`, `getting_hired_lessons.rb`,
   `shared_lessons.rb`, plus `ruby_lessons.rb`/`ruby_on_rails_lessons.rb` (excluded from scope).
2. **`db/fixtures/paths/<path>/seed.rb`** and **`db/fixtures/paths/<path>/courses/<course>.rb`** — assemble
   `Path` → `Course` → `Section` → ordered lesson list, referencing hash #1 by
   `<family>_lessons.fetch('Lesson Key')` inside each `section.add_lessons(...)` call. There are three
   paths: `foundations` (standalone, one course, defined entirely in one `seed.rb`), `full_stack_javascript`
   (loads 7 course files — the ones enumerated above minus foundations), and `full_stack_rails` (loads the
   *same* 6 shared course files — identical `identifier_uuid`s, so identical DB rows — plus `ruby.rb`/
   `rails.rb` on top). **Only `foundations` and `full_stack_javascript` need to be parsed**; parsing
   `full_stack_rails` too would just re-process courses already covered, and its two unique files are
   out of scope anyway.
3. `Lesson#import_content_from_github` → `Github::LessonContentImporter` still fetches the actual Markdown
   body from GitHub at runtime (unchanged conceptually from before) and converts it via a Markdown
   pipeline. This still requires network + Rails + Postgres to run for real, which is why the static-site
   approach (§4) remains the right call here.

`build_site.py` reads both fixture layers directly (as plain text, via regex — no Ruby execution) to
reconstruct the exact course → section → lesson structure, in the real site's order, without needing
Rails, Postgres, or a GitHub token. All 197 lesson counts were cross-checked against raw
`grep -c '_lessons\.fetch('` counts per course file and matched exactly; every lesson's `github_path`
was confirmed to resolve to a real file under `curriculum_ja/`.

**Facts confirmed during planning (still true after the reset):**
- Curriculum `.md` files have **no YAML frontmatter** — content starts directly with `### Introduction` etc.
- Lessons share a repeated structure: `### Introduction`, `### Assignment` (wrapped in
  `<div class="lesson-content__panel" markdown="1">`), `### Additional Resources`, `### Knowledge Check`
  (wrapped in `<details><summary>…</summary>…</details>` HTML blocks).
- The site's CSS/JS depends on the literal class hooks `lesson-content__panel` and the `markdown="1"`
  attribute. **These must never be translated or altered.** `build_site.py` uses Python-Markdown's
  `md_in_html` extension specifically because it — like the real site's Markdown pipeline — respects
  `markdown="1"` on raw HTML blocks.

---

## 1. Guiding rules for translation (apply to every file)

Accuracy and fidelity over everything. Do **not** simplify, summarize, reorder, or "improve" content.

**Translate (visible Japanese-facing prose):**
- Heading text, paragraphs, list items, table cell text.
- Markdown link anchor text `[像ここ](url)` — text yes, URL no.
- `<summary>` text and `<li>`/`<p>` prose inside `<details>` Knowledge Check blocks.
- Image alt text.

**Never touch (preserve byte-for-byte):**
- Fenced code blocks ```` ``` ```` and inline code `` `like_this` ``. Comments *inside* code may be
  translated only if you are certain it doesn't break the lesson; default is leave code untouched.
- All URLs, link targets, and anchor fragments.
- HTML tags, attributes, and especially `class="lesson-content__panel"`, `markdown="1"`,
  `<details>`, `<summary>`, `<div>`.
- Technical terms that are conventionally kept in English in Japanese dev writing — see
  `curriculum_ja/ja/GLOSSARY.md`.
- Whitespace-significant Markdown structure (list indentation, the leading spaces before `1.`, blank lines).

**Tone:** preserve the original's friendly, direct, second-person voice. Use ですます (polite) form
consistently. Match the original's emphasis (`**bold**`, `*italic*`) on the corresponding Japanese words.

**Terminology consistency (required):** `curriculum_ja/ja/GLOSSARY.md` exists — consult it before
translating a new lesson, and append newly-encountered recurring terms as you go. It also fixes the
Japanese wording of recurring section headings (Introduction, Assignment, Additional Resources,
Knowledge Check, etc.) so they're rendered identically everywhere.

**Token preservation (the user asked for this explicitly):**
- Translate **one file at a time**; never re-emit files already done.
- Copy code blocks / HTML through unchanged rather than "re-typing" them from reasoning.
- Track progress in `curriculum_ja/ja/MANIFEST.md` (§6) so a restart never re-translates completed files.
- Lean on the glossary instead of re-reasoning terminology each time.

---

## 2. Directory layout for translated content

Keep originals intact. Create a **parallel Japanese tree** so the English source is never overwritten
and diffs stay reviewable:

```
curriculum_ja/
  foundations/...               # English original (unchanged)
  javascript/...                # English original (unchanged)
  ...                            # (all other in-scope course folders, unchanged)
  ja/
    GLOSSARY.md                 # terminology (Section 1)
    MANIFEST.md                 # progress tracker (Section 6)
    foundations/...             # mirror of foundations/, translated .md
    javascript/...              # mirror of javascript/, translated .md
    ...                          # mirror of every other in-scope course folder
    resources/                  # translated external resources (Section 3)
```

Mirror the **exact relative paths** used by `github_path` in the fixture files (e.g.
`curriculum_ja/ja/foundations/git_basics/introduction_to_git.md` mirrors
`curriculum_ja/foundations/git_basics/introduction_to_git.md` — note some lessons' `github_path` actually
points into `git/...` or `shared/...`, not the course folder they're taught in; mirror it at that same
path under `ja/`, e.g. `curriculum_ja/ja/git/foundations_git/introduction_to_git.md`). `resolve_source()`
in `build_site.py` looks up `curriculum_ja/ja/<github_path>` first, so getting this path exactly right is
what makes a translation actually show up.

---

## 3. External resources — pull, translate, host locally

The in-scope courses link out to many external domains (MDN, w3schools, css-tricks, javascript.info,
YouTube, imgur, GitHub, etc.) — the same general mix as before the reset, now spread across 8 courses
instead of 2.

**Before translating any readable article, check for an official Japanese version first (added
2026-09-06, per user).** Many sites already publish their own ja localization — reuse it instead of
mirroring our own translation:
- **MDN** — almost every page has a `/ja/` locale (e.g. `developer.mozilla.org/en-US/docs/Web/HTML` →
  `developer.mozilla.org/ja/docs/Web/HTML`). Try swapping the locale segment; if the ja page exists (not
  a redirect back to en-US and not machine-stub-looking), link to it directly.
- **javascript.info** — has a full community-maintained translation at `ja.javascript.info` (swap the
  `www.`/bare domain for the `ja.` subdomain on the equivalent path).
- Check other frequently-linked domains (css-tricks, w3schools, wikipedia, freecodecamp, etc.) the same
  way — look for a language switcher or a `/ja/`-style path/subdomain — before assuming none exists.
- Only mirror-and-translate ourselves (the workflow below) when no official Japanese version exists, or
  the one that exists is clearly incomplete/stubbed compared to the English original. Record which case
  applied in MANIFEST.md (e.g. "linked to official MDN ja page" vs. "mirrored, no official ja version").

**Categorize each remaining external link (no official ja version) and handle by type:**

| Type | Examples | Action |
|---|---|---|
| Readable articles (text/HTML) | MDN, css-tricks, javascript.info, learn.shayhowe.com, alistapart, wikipedia, w3schools, smashingmagazine | Fetch main content, translate, store as local HTML/Markdown under `curriculum_ja/ja/resources/<slug>.md`, rewrite the lesson link to point locally (Phase 4 serves these). |
| Videos | youtube.com, youtu.be, ted.com, twit.tv | **Cannot translate audio/video.** Keep the original link. Translate only the surrounding sentence and any on-page description. Note in MANIFEST as "video, link kept". |
| Images | i.imgur.com, imgur.com | No text translation needed. Optionally download for offline use into `curriculum_ja/ja/resources/img/` and rewrite `src`. Screenshots containing baked-in English text **cannot be translated** — leave as-is and note it. |
| Interactive/tools/repos | github.com, repl.it, codepen.io, caniuse.com, tailwindcss.com | Keep link as-is (dynamic, not translatable prose). |
| Odin-internal | theodinproject.com/courses/... | Rewrite to the local route once the local slug is known (Phase 4/5). |

**⚠️ Copyright constraint (user has decided the scope — do not republish):**
MDN, articles, and books are third-party copyrighted works. The user chose **translate for LOCAL
VIEWING ONLY**, independent of whatever the curriculum lesson translations themselves end up being used
for. Therefore:
- Mirror & translate readable articles into `curriculum_ja/ja/resources/`, served only by the local app,
  **never republished** anywhere.
- Every mirrored file must carry a header: source URL, license, retrieval date. MDN is CC-BY-SA
  (attribution + share-alike) — keep attribution.
- This "local-only, no redistribution" policy is recorded at the top of
  `curriculum_ja/ja/resources/README.md`.

**Fetch method:** use the `WebFetch` tool (load via ToolSearch) to retrieve article text; do not scrape
aggressively. For each mirrored resource create `curriculum_ja/ja/resources/<domain>__<slug>.md` with a
header block: source URL, license, retrieval date, then the translated body.

---

## 4. Rendering the Japanese content locally — `build_site.py`

**This is what's actually built and working, at repo root: [build_site.py](build_site.py).** No Docker,
Ruby, Postgres, or GitHub token required. It only needs Python 3 + `pip install markdown`. Rewritten
2026-09-06 for the new fixture-based architecture (§0) — the old version parsed
`theodinproject/db/seeds/*_course_seeds.rb`, which no longer exists.

### 4a. How it works
1. `parse_lesson_families()` reads every `theodinproject_ja/db/fixtures/lessons/*_lessons.rb` file
   (skipping `ruby_lessons.rb`/`ruby_on_rails_lessons.rb`) and regex-parses each hash entry into
   `{(family, lesson_key): {title, description, is_project, url}}`. Note: the *last* entry in each Ruby
   hash literal has no trailing comma after its closing `}` — the regex handles this (`,?`), but it's an
   easy thing to break if this parser is ever "simplified."
2. `parse_course_file()` reads one `db/fixtures/paths/**/*.rb` file (either a standalone path `seed.rb` or
   a `courses/<name>.rb` file — same parser handles both shapes) and regex-parses `course.add_section do
   |section| ... end` blocks, extracting `section.title` and every `<family>_lessons.fetch('<key>')`
   reference inside, in order, resolving each against the table from step 1.
3. `COURSES` (near the top of the file) lists exactly which 8 fixture files map to which course output
   folder — this *is* the scope decision (§0) encoded as data.
4. For each lesson's `url` (a `github_path`, e.g. `/foundations/git_basics/introduction_to_git.md`),
   `resolve_source()` prefers `curriculum_ja/ja/<url>` (translated), falls back to `curriculum_ja/<url>`
   (English original) if the translation doesn't exist yet, and renders a "source file not found" notice
   if neither exists (verified: currently 0 lessons hit this case — all 197 resolve to a real file).
5. Converts the resolved Markdown to HTML with Python-Markdown (`extra`, `md_in_html`, `sane_lists`
   extensions — `md_in_html` is what makes `<div class="lesson-content__panel" markdown="1">` and
   `<details>` blocks convert their nested Markdown correctly).
6. Writes a static HTML page per lesson plus a per-course index and a top-level index, all wired with
   relative links, into `site/` (repo root). A small embedded stylesheet (`site/assets/style.css`)
   approximates the real site's lesson styling — an approximation, not a pixel-perfect copy of the app's SCSS.
7. Each lesson page carries a badge: 日本語訳 (translated) or 未翻訳 (English fallback), and each course
   index has a colored legend so translation progress is visible at a glance without opening MANIFEST.md.

### 4b. Running it
```bash
python build_site.py
```
Then open `site/index.html` directly in a browser (works via `file://`), or serve it so relative links
behave like a normal site:
```bash
python -m http.server 8743 --directory site
# then open http://localhost:8743/
```
Re-run `python build_site.py` any time after translating more files — it's fast (regex parse + Markdown
convert, no DB) and safe to run repeatedly; it always rebuilds `site/` from current `curriculum_ja/` +
`curriculum_ja/ja/` contents.

### 4c. Changing scope later
Scope lives entirely in two places: the `COURSES` list (which course files get parsed) and
`EXCLUDED_LESSON_FAMILIES` (which lesson-hash files get skipped), both near the top of `build_site.py`.
To add e.g. Ruby back into scope, add `("db/fixtures/paths/full_stack_rails/courses/ruby.rb", "ruby")`
and `("db/fixtures/paths/full_stack_rails/courses/rails.rb", "rails")` to `COURSES`, and remove `"ruby"`/
`"ruby_on_rails"` from `EXCLUDED_LESSON_FAMILIES`. No other code changes needed — the parser is generic
over any fixture file following the same shape (all of them do).

### 4d. Translate the navigation metadata (descriptions)
`build_site.py` displays each lesson's `description:` field (from the fixture file) under the lesson
title. Per the user's decision, `title` stays English; `description` values may be translated for a more
complete Japanese experience — **but note**: if you translate descriptions, do it in a way the build
script reads without editing `theodinproject_ja/db/fixtures/**` in place (keep that repo as pristine,
reusable fixture data). A clean way to do this later: let `build_site.py` optionally read an override file
`curriculum_ja/ja/descriptions.yml` (`github_path: 翻訳した説明文`) and prefer it over the fixture's
description when present. Not yet built — add it if/when descriptions are translated.

### 4e. Alternative: the real Rails app (documented, not built)
If full production fidelity (real nav chrome, auth, progress tracking, exact CSS) is wanted later, the
proper approach is to override `theodinproject_ja/app/models/github/lesson_content_importer.rb` (or
wherever it lives — re-verify the exact path/class name post-reset, it may have moved under `app/models/
github/`) to read `curriculum_ja/ja/<lesson.github_path>` from disk (falling back to English, then to the
live GitHub fetch it already does) behind an env flag, mount `curriculum_ja` into the Docker container,
and run `db:seed` + the content-import rake task. This requires installing Docker Desktop (or WSL2 +
native Ruby/Postgres) on this machine first — not done, since the user opted for the static-site approach.

---

## 5. Execution phases (ordered, resumable)

**Phase 0 — Setup. ✅ DONE (2026-09-06, redone after the workspace reset).**
Created `curriculum_ja/ja/`, `curriculum_ja/ja/GLOSSARY.md` (terminology + section-heading conventions),
`curriculum_ja/ja/MANIFEST.md` (full per-file checklist for all 8 in-scope courses / 197 lessons,
generated programmatically from the fixture parser so it can't drift from what `build_site.py` actually
builds — all rows `todo`), and `curriculum_ja/ja/resources/README.md` (local-only-viewing policy).

**Phase 1 — Get a working render pipeline before translating anything. ✅ DONE (2026-09-06, rewritten
after the reset).** Rewrote `build_site.py` for the new fixture architecture (§4) and verified: all 197
lesson counts match raw `grep -c` counts per course file exactly (46/22/16/41/25/3/30/14), all 197
`github_path`s resolve to a real file on disk (0 missing), and the site builds cleanly end-to-end.
**Currently renders 100% English fallback** since no lessons are translated yet — expected, and the
correct baseline to translate against.

**Phase 2 — Translate `foundations/` (46 lessons).** For each file: read English → produce
`curriculum_ja/ja/<its github_path>` following §1 rules → update GLOSSARY.md + MANIFEST.md status →
re-run `python build_site.py` periodically to check rendering. Follow the order shown in MANIFEST.md
(already listed in real site order, grouped by section). Note: some Foundations-section lessons have a
`github_path` under `git/...` (Git Basics section) rather than under `foundations/...` — mirror the path
exactly as MANIFEST.md lists it. Translate projects (marked `project` in MANIFEST) with the same rigor.

**Phase 3 — Translate `intermediate_html_css/` (22) and `advanced_html_css/` (16).** Same process.

**Phase 4 — External resources.** Walk the links per translated file; handle by §3's table; write
translated mirrors into `curriculum_ja/ja/resources/`; rewrite the corresponding links in the translated
Markdown to point at the local mirror.

**Phase 5 — QA pass.** Run `python build_site.py`, open `site/index.html`, and click through translated
lessons: badges show 日本語訳 (not 未翻訳) for every translated file, no broken panels/`<details>`, code
blocks intact, links resolve, terminology consistent with GLOSSARY.md, no accidental English left in
prose, MANIFEST.md statuses all `verified`.

**Phase 6 — (optional) descriptions + real Rails app.** If wanted later: translate fixture `description`
fields via the override-file approach in §4d, and/or build the full Rails/Docker path in §4e for
production-fidelity rendering. Neither is required for the core deliverable.

**Phase 7 — Remaining courses.** Repeat Phases 2–5 for `javascript/` (41), `react/` (25), `databases/`
(3), `getting_hired/` (14) — same rules, same `curriculum_ja/ja/` layout, same MANIFEST.md/GLOSSARY.md
workflow. **`nodeJS/` (30) is deferred — skip it for now (user instruction, 2026-09-06); do not translate
it until told to resume.** `archive/`, `ruby/`, `ruby_on_rails/` are **out of scope** — do not translate
them (re-confirm with the user before expanding scope further).

---

## 6. Progress tracking (`curriculum_ja/ja/MANIFEST.md`)

Generated programmatically (grouped by course, then by section, in real site order) so it can't drift
from what `build_site.py` actually builds. Update the `status` column as each lesson is processed:
`todo` → `translated` → `resources-done` → `verified`. Re-generate it (or hand-edit rows) as needed; if
regenerating from scratch, re-run the generation snippet used originally (parse via `build_site.py`'s own
`parse_lesson_families`/`parse_course_file`, so it never drifts from the real course list) rather than
retyping 197 rows by hand.

---

## 7. Decisions locked / remaining risks

**Locked by the user:**
1. **Titles/nav stay English; only bodies + descriptions are translated (§4d).** No `title:` edits in
   fixture files.
2. **External resources: translate for LOCAL VIEWING ONLY (§3),** with source/license/date attribution;
   never republished — independent of the curriculum content's own eventual disposition.
3. **Scope: everything except `archive/`, `ruby/`, `ruby_on_rails/`** — 8 courses, 197 lessons (§0).
4. **Rendering: static site via `build_site.py`, not the Rails app (§4).**
5. **`nodeJS/` deferred (skip for now, 2026-09-06)** — still in scope, just not being actively worked on;
   resume only when the user asks.

**Residual risks / notes:**
- **Videos & baked-in-text screenshots are not translatable** — links/images kept as-is (unavoidable).
- The repos are forks named `curriculum_ja`/`theodinproject_ja` under `github.com/dwnfll` — this naming
  suggests the translation may eventually be intended for more than purely local/private use. This has
  **not** been confirmed with the user; until it is, the local-viewing-only rule for third-party external
  resources (§3) stays in force regardless, since that's a separate copyright question from whether the
  curriculum's own (Odin-licensed) prose gets shared.
- `git status` in both `curriculum_ja/` and `theodinproject_ja/` will show nothing until lessons are
  actually translated — they are pristine, unmodified clones right now. Translation output lands inside
  `curriculum_ja/` (under `ja/`), so it'll show up in `git status` run **inside `curriculum_ja/`**, not
  inside `theodinproject_ja/` (never modified — read-only reference for fixture/structure data) or at the
  top-level `odin/` folder (not a git repo itself — `build_site.py`, `site/`, and this plan file live there
  as loose files outside any repo).
- Some resources may be paywalled/removed (several links may use `web.archive.org`); use the archived
  copy when the live one is dead, and note it in the MANIFEST.

---

## 8. Quick reference — key files

- **Build/view script (the thing you actually run): [build_site.py](build_site.py)** — `python build_site.py`,
  then open `site/index.html` or serve `site/` with `python -m http.server`.
- Fixtures (source of truth for structure/titles, read-only input to the script):
  `theodinproject_ja/db/fixtures/lessons/*_lessons.rb`,
  `theodinproject_ja/db/fixtures/paths/foundations/seed.rb`,
  `theodinproject_ja/db/fixtures/paths/full_stack_javascript/**`
- Content source: `curriculum_ja/<course>/` for each of the 8 in-scope courses.
- Translations land in: `curriculum_ja/ja/…` (mirrors the same `github_path`-relative paths).
- Progress tracking: [curriculum_ja/ja/MANIFEST.md](curriculum_ja/ja/MANIFEST.md)
- Terminology: [curriculum_ja/ja/GLOSSARY.md](curriculum_ja/ja/GLOSSARY.md)
- Not used (documented alternative only, §4e): theodinproject_ja's GitHub content importer, Docker setup.
