#!/usr/bin/env python3
"""
Lightweight local viewer for the Japanese translation of The Odin Project curriculum.

Reads the course/section/lesson structure straight out of theodinproject_ja's own
fixture files (so it never drifts from the real site's navigation), converts each
lesson's Markdown to HTML (Japanese translation if present under curriculum_ja/ja/,
otherwise the English original as a fallback), and writes a small static HTML site to
./site/ that can be opened directly in a browser -- no Rails, Postgres, or Docker
required.

This is v2 of the tool, rewritten 2026-09-06 after the workspace was reset to fresh,
current (2026-09) clones of upstream, renamed curriculum_ja/ and theodinproject_ja/.
Upstream replaced db/seeds/*_course_seeds.rb (v1's data source) with a two-layer
fixture system under db/fixtures/ -- see parse_lesson_families() and parse_course_file()
below, and TRANSLATION_PLAN_JA.md section 4 for the full explanation.

Usage:
    python build_site.py

Requires:
    pip install markdown

Output:
    site/index.html                        top-level course list
    site/<course>/index.html               section + lesson nav for a course
    site/<course>/<lesson-slug>.html       one rendered lesson
    site/assets/application.css            the real site's compiled Tailwind/prose bundle
    site/assets/viewer.css                 local-viewer shell (navbar/index) styles
    site/assets/{logo.svg,icons/}          logo + note-box/anchor icons

The lesson body is wrapped in the same classes the live app uses (see
build_lesson_page and app/components/content_container_component.html.erb), so the
copied application.css styles it identically. application.css itself is a build
artifact of theodinproject_ja (`yarn build:css`); copy_static_assets() consumes it.
"""
import html
import re
from pathlib import Path

import markdown as md

ROOT = Path(__file__).resolve().parent
CURRICULUM = ROOT / "curriculum_ja"
CURRICULUM_JA = CURRICULUM / "ja"
THEODINPROJECT = ROOT / "theodinproject_ja"
FIXTURES = THEODINPROJECT / "db" / "fixtures"
SITE = ROOT / "site"

# Scope (per user, 2026-09-06): translate everything EXCEPT archive, ruby, ruby_on_rails.
# Concretely that means: the standalone "Foundations" path, plus every course in the
# "Full Stack JavaScript" path. "Full Stack Ruby on Rails" duplicates most of those same
# courses (same identifier_uuid, shared content) and adds only ruby.rb/rails.rb on top,
# so we never need to parse it -- loading it would just double-build courses we already
# have. git_lessons and shared_lessons aren't standalone courses; their lessons are
# pulled in inline by courses that reference them (e.g. Foundations' "Git Basics"
# section), same as before.
COURSES = [
    ("db/fixtures/paths/foundations/seed.rb", "foundations"),
    ("db/fixtures/paths/full_stack_javascript/courses/intermediate_html_css.rb", "intermediate_html_css"),
    ("db/fixtures/paths/full_stack_javascript/courses/advanced_html_css.rb", "advanced_html_css"),
    ("db/fixtures/paths/full_stack_javascript/courses/javascript.rb", "javascript"),
    ("db/fixtures/paths/full_stack_javascript/courses/react.rb", "react"),
    ("db/fixtures/paths/full_stack_javascript/courses/databases.rb", "databases"),
    ("db/fixtures/paths/full_stack_javascript/courses/node_js.rb", "nodeJS"),
    ("db/fixtures/paths/full_stack_javascript/courses/getting_hired.rb", "getting_hired"),
]

# Lesson-hash files to load (db/fixtures/lessons/<family>_lessons.rb, minus ruby/rails).
EXCLUDED_LESSON_FAMILIES = {"ruby", "ruby_on_rails"}

#   - "extra" is core Markdown's bundle: fenced_code, footnotes, attr_list, def_list,
#     tables, abbr, md_in_html.
#   - "pymdownx.superfences" replaces core's fenced_code handling (it registers under
#     the same preprocessor name, so it wins over the copy bundled in "extra" -- no
#     need to unbundle "extra" to avoid a clash). Unlike core fenced_code -- which is a
#     Preprocessor requiring the opening ``` at column 0 (see FENCED_BLOCK_RE in
#     markdown.extensions.fenced_code), so it never even looks at fences indented under
#     a list item -- superfences is list/blockquote-aware and can absorb an indented
#     fence into the enclosing <li> when the indent is a multiple of Markdown's 4-space
#     tab_length. See normalize_list_continuation_indentation() below for the other
#     half of this fix: remapping the marker-width indentation CommonMark authors use
#     under "- "/"1. " onto the fixed 4-space steps python-markdown expects.
MD_EXTENSIONS = ["extra", "md_in_html", "sane_lists", "pymdownx.superfences"]

_LIST_MARKER_RE = re.compile(r"^( *)(?:[-*+]|\d{1,9}[.)])( +)")
_INDENTED_FENCE_RE = re.compile(r"^( +)(`{3,}|~{3,})")


def normalize_list_continuation_indentation(text: str) -> str:
    """Remap list indentation from CommonMark's marker-width model onto the fixed
    4-space "tab_length" steps python-markdown reasons in, so nested lists and every
    kind of list-item continuation content (paragraphs, fenced code, raw-HTML blocks
    with markdown="1", ...) are recognized as belonging to their list item instead of
    being dropped back to loose top-level content. For a fenced block that drop also
    means the fence markers themselves stop being recognized and leak through as
    literal ``` text; for a nested list it means the sublist detaches into a sibling.

    CommonMark nests by *marker width*: content continuing "- " starts at column 2,
    "1. " at column 3, and a second level of nesting a further 2-3 columns in.
    python-markdown instead only sees a continuation/nesting step at each exact
    multiple of 4. A continuation indented 3 spaces therefore sits *inside* its first
    step without *equalling* it and is invisible to the list processor. Rather than
    round each line's raw indent up independently (which mishandles genuine multi-level
    nesting, where each level's shift has to compound on top of its parent's), we track
    the open list levels on a stack and map level k's continuation column to 4*(k+1),
    shifting every line by its level's delta. Marker lines are re-indented too (a
    nested marker at column 3 -> 4), which is what lets sublists actually nest.

    Only indentation genuinely inside a list item's continuation zone is touched --
    top-level content that merely happens to be indented for other reasons is left
    alone (so it can't be misread as "should be a code block" once shifted). Shifts
    only ever *add* leading whitespace to in-scope lines; the file on disk is never
    modified, and a fenced block is shifted as a unit so the code's own interior
    indentation is preserved. Column-0 fences are inherently out of scope and pass
    through untouched, so a code sample that itself contains lines looking like an
    indented fence is never misinterpreted."""
    lines = text.split("\n")
    out = []
    # One entry per open list level: (cont_orig, cont_new). cont_orig is the column
    # where that level's continuation content begins in the source (marker-width
    # based); cont_new is where it should begin for python-markdown (always a multiple
    # of 4), so depth 0,1,2,... maps to continuation columns 4,8,12,... whatever
    # marker widths were actually used.
    stack = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]

        if line.strip() == "":
            out.append(line)
            i += 1
            continue

        indent = len(line) - len(line.lstrip(" "))

        m = _LIST_MARKER_RE.match(line)
        if m:
            marker_orig = len(m.group(1))
            while stack and marker_orig < stack[-1][0]:
                stack.pop()
            marker_new = stack[-1][1] if stack else marker_orig
            stack.append((len(m.group(0)), marker_new + 4))
            out.append((" " * marker_new) + line[marker_orig:])
            i += 1
            continue

        if indent == 0:
            stack.clear()
            out.append(line)
            i += 1
            continue

        while stack and indent < stack[-1][0]:
            stack.pop()

        if not stack:
            out.append(line)
            i += 1
            continue

        cont_orig, cont_new = stack[-1]
        delta = (cont_new + (indent - cont_orig)) - indent
        pad = " " * delta

        m_fence = _INDENTED_FENCE_RE.match(line)
        if m_fence:
            fence = m_fence.group(2)
            close_re = re.compile(r"^ {" + str(indent) + "}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$")
            out.append(pad + line if delta else line)
            i += 1
            while i < n and not close_re.match(lines[i]):
                out.append(pad + lines[i] if delta else lines[i])
                i += 1
            if i < n:
                out.append(pad + lines[i] if delta else lines[i])
                i += 1
            continue

        # Any other continuation block (a paragraph, a raw-HTML line, ...): shift this
        # line and the directly-following lines of the same block by the same delta,
        # stopping at a blank line, a dedent out of the block, or a nested list marker
        # (which the main loop must handle so it gets its own depth-correct remapping).
        while (
            i < n
            and lines[i].strip() != ""
            and (len(lines[i]) - len(lines[i].lstrip(" "))) >= indent
            and not _LIST_MARKER_RE.match(lines[i])
        ):
            out.append(pad + lines[i] if delta else lines[i])
            i += 1

    return "\n".join(out)


def extract_field(block: str, name: str):
    """Hash-literal style: `name: 'value',` or `name: "value",` -- used inside
    db/fixtures/lessons/*.rb entries."""
    m = re.search(rf"^[ \t]*{re.escape(name)}:\s*(['\"])((?:\\.|(?!\1).)*?)\1", block, re.MULTILINE)
    return m.group(2) if m else None


def extract_bool_field(block: str, name: str):
    m = re.search(rf"^[ \t]*{re.escape(name)}:\s*(true|false)", block, re.MULTILINE)
    return bool(m and m.group(1) == "true")


def extract_attr(block: str, obj: str, name: str):
    """Ruby attr-assignment style: `obj.name = 'value'` -- used in db/fixtures/paths/**/*.rb."""
    m = re.search(
        rf"^[ \t]*{re.escape(obj)}\.{re.escape(name)}\s*=\s*(['\"])((?:\\.|(?!\1).)*?)\1",
        block,
        re.MULTILINE,
    )
    return m.group(2) if m else None


# Trailing comma after the closing "}" is optional: the last entry in each hash
# literal omits it (Ruby style), so `,?` here matters -- don't drop it.
LESSON_ENTRY_RE = re.compile(r"'((?:\\.|[^'])*)'\s*=>\s*\{(.*?)\n[ \t]*\},?", re.DOTALL)


def parse_lesson_families():
    """Parse every db/fixtures/lessons/<family>_lessons.rb into
    {(family, lesson_key): {title, description, is_project, url}}."""
    table = {}
    for path in sorted((FIXTURES / "lessons").glob("*_lessons.rb")):
        family = path.stem[: -len("_lessons")]
        if family in EXCLUDED_LESSON_FAMILIES:
            continue
        text = path.read_text(encoding="utf-8")
        for m in LESSON_ENTRY_RE.finditer(text):
            key, block = m.group(1), m.group(2)
            table[(family, key)] = {
                "title": extract_field(block, "title"),
                "description": extract_field(block, "description") or "",
                "is_project": extract_bool_field(block, "is_project"),
                "url": extract_field(block, "github_path"),
            }
    return table


SECTION_RE = re.compile(r"course\.add_section do \|section\|\n(.*?)\nend\b", re.DOTALL)
FETCH_RE = re.compile(r"(\w+)_lessons\.fetch\(\s*(['\"])((?:\\.|(?!\2).)*?)\2\s*\)")


def parse_course_file(rel_path: str, lesson_table: dict):
    """Parse a db/fixtures/paths/**/*.rb file (either a standalone path seed.rb that
    also embeds its one course, or a courses/<name>.rb file) into
    {title, sections: [{title, lessons: [...]}]}."""
    text = (THEODINPROJECT / rel_path).read_text(encoding="utf-8")
    course_title = extract_attr(text, "course", "title")

    sections = []
    for sm in SECTION_RE.finditer(text):
        body = sm.group(1)
        section_title = extract_attr(body, "section", "title")
        lessons = []
        for fm in FETCH_RE.finditer(body):
            family, _, key = fm.group(1), fm.group(2), fm.group(3)
            lesson = lesson_table.get((family, key))
            if lesson is None:
                lesson = {"title": key, "description": "", "is_project": False, "url": None}
            lessons.append(lesson)
        sections.append({"title": section_title, "lessons": lessons})

    return {"title": course_title, "sections": sections}


def slug_for(url: str) -> str:
    """Turn a lesson url like /foundations/git_basics/introduction_to_git.md into a
    flat, filesystem-safe html filename: git_basics__introduction_to_git.html"""
    parts = url.strip("/").split("/")[1:]  # drop the course folder, kept separately
    stem = "__".join(parts)
    return re.sub(r"\.md$", ".html", stem)


def resolve_source(url):
    """Return (path, lang) for a lesson url: prefer the Japanese translation, else
    fall back to the English original. Returns (None, None) if url is missing or
    neither file exists."""
    if not url:
        return None, None
    ja_path = CURRICULUM_JA / url.lstrip("/")
    if ja_path.is_file():
        return ja_path, "ja"
    en_path = CURRICULUM / url.lstrip("/")
    if en_path.is_file():
        return en_path, "en"
    return None, None


def render_markdown(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = normalize_list_continuation_indentation(text)
    return md.Markdown(extensions=MD_EXTENSIONS).convert(text)


# The <head>/<body> shell mirrors theodinproject_ja's app/views/layouts/application.html.erb:
# the same Inter webfont, the compiled Tailwind + prose + custom_styles bundle
# (assets/application.css), a light-mode <html> (dark styles are gated on .dark, which we
# never set), and Prism for the exact same code-token colors the real site ships. viewer.css
# adds only the surrounding shell (navbar / index pages). {prefix} is "" for the top page and
# "../" for pages one directory deep, so every asset href resolves under file://.
PAGE_TEMPLATE = """<!doctype html>
<html lang="{lang}" class="light scroll-smooth">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} | The Odin Project 日本語版</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@100;200;300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{prefix}assets/application.css">
<link rel="stylesheet" href="{prefix}assets/viewer.css">
</head>
<body class="h-full bg-gray-50 text-gray-600">
<nav class="tvp-nav">
  <div class="tvp-nav__inner">
    <a class="tvp-nav__brand" href="{prefix}index.html">
      <img class="tvp-nav__logo" src="{prefix}assets/logo.svg" alt="The Odin Project">
    </a>
    <div class="tvp-nav__links">
      <a href="{prefix}index.html">All Paths</a>
      <span class="tvp-badge">日本語版 · ローカルプレビュー</span>
    </div>
  </div>
</nav>
{body}
<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-core.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/autoloader/prism-autoloader.min.js"></script>
</body>
</html>
"""


def write_page(path: Path, title: str, body: str, prefix: str, lang="ja"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        PAGE_TEMPLATE.format(lang=lang, title=html.escape(title or ""), body=body, prefix=prefix),
        encoding="utf-8",
    )


def build_lesson_page(course_slug: str, lesson: dict, out_dir: Path):
    src_path, lang = resolve_source(lesson["url"])
    slug = slug_for(lesson["url"]) if lesson["url"] else re.sub(r"\W+", "_", lesson["title"] or "untitled") + ".html"
    out_path = out_dir / slug

    if src_path is None:
        content_html = (
            f'<div class="notice notice--missing">'
            f"Source file not found on disk for <code>{html.escape(lesson['url'] or '(no github_path)')}</code>. "
            f"See curriculum_ja/ja/MANIFEST.md &quot;Known issues&quot;.</div>"
        )
        lang = "en"
    else:
        content_html = render_markdown(src_path)

    badge = {
        "ja": '<span class="lang-badge lang-badge--ja">日本語訳</span>',
        "en": '<span class="lang-badge lang-badge--en">未翻訳 (English fallback)</span>',
    }.get(lang, "")

    # The inner wrapper uses the SAME classes as theodinproject_ja's
    # app/components/content_container_component.html.erb, so the compiled application.css
    # styles this prose exactly as it does on the live site (link/code/pre variants, note
    # boxes, the lesson-content__panel assignment box, sub-numbered lists, etc.). Everything
    # outside it (title, breadcrumb) is our own tvp-* shell.
    body = f"""
<main class="tvp-main">
  <div class="tvp-lesson">
    <header>
      <div class="tvp-lesson__head">
        <h1 class="tvp-lesson__title">{html.escape(lesson['title'] or '')}</h1>
        {badge}
      </div>
      <p class="tvp-breadcrumb"><a href="index.html">← {html.escape(course_slug)}</a></p>
    </header>
    {'<p class="tvp-lesson__desc">' + html.escape(lesson['description']) + '</p>' if lesson['description'] else ''}
    <article>
      <div class="lesson-content prose prose-gray prose-a:text-blue-800 prose-a:visited:text-purple-800 prose-code:bg-gray-100 prose-code:p-1 prose-code:font-normal prose-code:rounded-md break-words line-numbers prose-pre:rounded-xl prose-pre:bg-slate-800 prose-pre:shadow-lg" data-controller="syntax-highlighting">
        {content_html}
      </div>
    </article>
  </div>
</main>
"""
    write_page(out_path, lesson["title"] or slug, body, "../", lang=lang)
    return slug


def build_course_index(course_key: str, course: dict, out_dir: Path):
    rows = []
    for section in course["sections"]:
        items = []
        for lesson in section["lessons"]:
            _, lang = resolve_source(lesson["url"])
            slug = slug_for(lesson["url"]) if lesson["url"] else re.sub(r"\W+", "_", lesson["title"] or "untitled") + ".html"
            badge_class = "done" if lang == "ja" else ("fallback" if lang == "en" else "missing")
            project_tag = ' <span class="tvp-proj">🛠 Project</span>' if lesson["is_project"] else ""
            items.append(
                f'<li class="nav-lesson nav-lesson--{badge_class}">'
                f'<a href="{slug}">{html.escape(lesson["title"] or slug)}</a>{project_tag}</li>'
            )
        rows.append(
            f'<section class="tvp-section"><h2>{html.escape(section["title"] or "")}</h2>'
            f'<ul class="tvp-lessons">{"".join(items)}</ul></section>'
        )

    body = f"""
<main class="tvp-main">
  <div class="tvp-index">
    <div class="tvp-hero">
      <h1>{html.escape(course['title'] or course_key)}</h1>
      <p class="tvp-legend">
        <span><span class="dot dot--done"></span>翻訳済み</span>
        <span><span class="dot dot--fallback"></span>未翻訳 (英語)</span>
        <span><span class="dot dot--missing"></span>ファイルが見つかりません</span>
      </p>
    </div>
    {''.join(rows)}
  </div>
</main>
"""
    write_page(out_dir / "index.html", course["title"] or course_key, body, "../")


def build_top_index(built_courses):
    items = "".join(
        f'<li><a href="{key}/index.html">{html.escape(course["title"] or key)}</a></li>'
        for key, course in built_courses
    )
    body = f"""
<main class="tvp-main">
  <div class="tvp-index">
    <div class="tvp-hero">
      <h1>The Odin Project — 日本語版</h1>
      <p>これは翻訳作業を確認するためのローカル専用プレビューです。公開・配布はしないでください。</p>
    </div>
    <ul class="tvp-course-list">{items}</ul>
  </div>
</main>
"""
    write_page(SITE / "index.html", "The Odin Project 日本語版", body, "")


# Where the real app keeps the compiled stylesheet and its image assets. application.css
# is produced by theodinproject_ja's `yarn build:css` (Tailwind v4 CLI) -- we consume it as
# a build artifact rather than recompiling it here.
TAILWIND_BUILD = THEODINPROJECT / "app" / "assets" / "builds" / "application.css"
APP_IMAGES = THEODINPROJECT / "app" / "assets" / "images"
# Icons the compiled CSS references as mask-image: url('/icons/<name>.svg') for the
# lesson-note boxes and heading anchor links. We copy them next to application.css and
# rewrite the absolute '/icons/' to a relative 'icons/' so they resolve under file://.
NOTE_ICONS = [
    "link.svg",
    "pencil-square-solid.svg",
    "light-bulb-solid.svg",
    "exclamation-triangle-solid.svg",
    "exclamation-circle-solid.svg",
]

# Only the surrounding shell (navbar / breadcrumb / index pages). The lesson body itself is
# styled by the copied application.css. See site/assets/viewer.css comments for rationale.
VIEWER_CSS = """\
/* Local-viewer chrome for the Odin Project JA preview.
   The lesson BODY is styled entirely by application.css (the real, compiled
   Tailwind + @tailwindcss/typography "prose" + the app's own custom_styles).
   This file only styles the surrounding shell -- navbar, breadcrumb, lesson
   header, and the index/course listing pages -- using plain CSS classes
   (tvp-*) so it never depends on Tailwind having scanned these generated
   pages. Colors/spacing here mirror the real site's palette. */

:root {
  --tvp-border: #e5e7eb; --tvp-gray-900: #111827; --tvp-gray-800: #1f2937;
  --tvp-gray-700: #374151; --tvp-gray-600: #4b5563; --tvp-gray-500: #6b7280;
  --tvp-canvas: #f9fafb; --tvp-gold: #ce973e; --tvp-gold-600: #a9792b;
  --tvp-gold-50: #f3e6d0; --tvp-gold-800: #503914;
}

body { font-family: Inter, "Helvetica Neue", Helvetica, Arial, "Yu Gothic",
       "Hiragino Sans", "Noto Sans JP", sans-serif; background: var(--tvp-canvas); }

/* Navbar */
.tvp-nav { background: #fff; border-bottom: 1px solid var(--tvp-border);
           position: sticky; top: 0; z-index: 50; }
.tvp-nav__inner { max-width: 80rem; margin: 0 auto; padding: 0.5rem 1.5rem;
                  display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.tvp-nav__brand { display: flex; align-items: center; }
.tvp-nav__logo { height: 2.75rem; width: auto; display: block; }
.tvp-nav__links { display: flex; align-items: center; gap: 1.25rem; font-size: 0.9rem; }
.tvp-nav__links a { color: var(--tvp-gray-600); text-decoration: none; font-weight: 500; }
.tvp-nav__links a:hover { color: var(--tvp-gray-900); }
.tvp-badge { background: var(--tvp-gold-50); color: var(--tvp-gold-800);
             font-size: 0.72rem; font-weight: 600; padding: 0.25rem 0.6rem;
             border-radius: 9999px; white-space: nowrap; }

/* Shared page containers */
.tvp-main { padding: 2.5rem 1.5rem 5rem; }
.tvp-lesson { max-width: 70ch; margin: 0 auto; }
.tvp-index { max-width: 64rem; margin: 0 auto; }

/* Lesson header */
.tvp-lesson__head { display: flex; align-items: center; gap: 0.75rem;
                    flex-wrap: wrap; margin-bottom: 0.5rem; }
.tvp-lesson__title { font-size: 1.875rem; line-height: 2.35rem; font-weight: 600;
                     color: var(--tvp-gray-800); margin: 0; }
.tvp-breadcrumb { margin: 0 0 2rem; font-size: 0.85rem; }
.tvp-breadcrumb a { color: var(--tvp-gray-500); text-decoration: none; }
.tvp-breadcrumb a:hover { color: var(--tvp-gold-600); }
.tvp-lesson__desc { color: var(--tvp-gray-500); margin: 0 0 2rem; }

.lang-badge { font-size: 0.72rem; padding: 0.2rem 0.6rem; border-radius: 9999px; font-weight: 600; }
.lang-badge--ja { background: #e6f4ea; color: #2e8b57; }
.lang-badge--en { background: #fdf3d8; color: #b8860b; }

/* Top index (course list) */
.tvp-hero h1 { font-size: 2rem; font-weight: 700; color: var(--tvp-gray-800); margin: 0 0 0.5rem; }
.tvp-hero p { color: var(--tvp-gray-500); margin: 0; }
.tvp-course-list { list-style: none; padding: 0; margin: 2rem 0 0; display: grid; gap: 0.75rem; }
.tvp-course-list a { display: block; padding: 1rem 1.25rem; border: 1px solid var(--tvp-border);
                     border-radius: 0.75rem; background: #fff; text-decoration: none;
                     color: var(--tvp-gray-800); font-weight: 600;
                     transition: border-color 0.15s, box-shadow 0.15s; }
.tvp-course-list a:hover { border-color: var(--tvp-gold); box-shadow: 0 1px 3px rgba(0,0,0,0.08); }

/* Course index (sections + lessons) */
.tvp-section { margin-top: 2.5rem; }
.tvp-section > h2 { font-size: 1.25rem; font-weight: 600; color: var(--tvp-gray-800);
                    padding-bottom: 0.5rem; border-bottom: 1px solid var(--tvp-border); margin: 0; }
.tvp-lessons { list-style: none; padding: 0; margin: 0.75rem 0 0; }
.tvp-lessons li { padding: 0.35rem 0; }
.tvp-lessons a { text-decoration: none; }
.tvp-lessons a:hover { text-decoration: underline; }
.nav-lesson--done a { color: var(--tvp-gray-800); }
.nav-lesson--fallback a { color: var(--tvp-gray-600); }
.nav-lesson--missing a { color: var(--tvp-gray-500); }
.tvp-proj { color: var(--tvp-gold-600); font-size: 0.8rem; }
.tvp-legend { color: var(--tvp-gray-500); font-size: 0.85rem; display: flex;
              gap: 1.25rem; flex-wrap: wrap; margin-top: 0.75rem; }
.dot { display: inline-block; width: 0.7rem; height: 0.7rem; border-radius: 2px;
       vertical-align: middle; margin-right: 0.3rem; }
.dot--done { background: #2e8b57; }
.dot--fallback { background: #b8860b; }
.dot--missing { background: #c0392b; }

/* Misc */
.notice { padding: 1rem 1.25rem; border-radius: 0.5rem; }
.notice--missing { background: #fdecea; color: #c0392b; }
"""


def copy_static_assets():
    """Populate site/assets/ so a clean `rm -rf site && python build_site.py` fully
    reproduces the styled site: the real compiled Tailwind bundle (with '/icons/' rewritten
    to a file://-relative 'icons/'), our viewer.css shell, the Odin logo, and the note-box /
    anchor icons. application.css is a prerequisite artifact -- if it's missing we still
    build (pages just render unstyled) and print how to produce it."""
    assets = SITE / "assets"
    icons = assets / "icons"
    icons.mkdir(parents=True, exist_ok=True)

    (assets / "viewer.css").write_text(VIEWER_CSS, encoding="utf-8")

    if TAILWIND_BUILD.is_file():
        css = TAILWIND_BUILD.read_text(encoding="utf-8").replace("url('/icons/", "url('icons/")
        (assets / "application.css").write_text(css, encoding="utf-8")
    else:
        print(
            "WARNING: compiled Tailwind not found at\n"
            f"  {TAILWIND_BUILD}\n"
            "Lesson pages will render unstyled. Build it once with bun (Node 15 can't run\n"
            "the Tailwind v4 CLI):\n"
            "  cd theodinproject_ja && bun install && \\\n"
            "    bun node_modules/@tailwindcss/cli/dist/index.mjs \\\n"
            "      -i app/assets/stylesheets/application.tailwind.css \\\n"
            "      -o app/assets/builds/application.css"
        )

    logo = APP_IMAGES / "logo.svg"
    if logo.is_file():
        (assets / "logo.svg").write_bytes(logo.read_bytes())
    for name in NOTE_ICONS:
        src = APP_IMAGES / "icons" / name
        if src.is_file():
            (icons / name).write_bytes(src.read_bytes())


def main():
    SITE.mkdir(exist_ok=True)
    copy_static_assets()

    lesson_table = parse_lesson_families()

    built = []
    for course_rel, course_key in COURSES:
        course = parse_course_file(course_rel, lesson_table)
        out_dir = SITE / course_key
        for section in course["sections"]:
            for lesson in section["lessons"]:
                build_lesson_page(course_key, lesson, out_dir)
        build_course_index(course_key, course, out_dir)
        built.append((course_key, course))
        n_lessons = sum(len(s["lessons"]) for s in course["sections"])
        n_ja = sum(
            1
            for s in course["sections"]
            for l in s["lessons"]
            if resolve_source(l["url"])[1] == "ja"
        )
        print(f"[{course_key}] {n_lessons} lessons, {n_ja} translated, {n_lessons - n_ja} pending")

    build_top_index(built)
    print(f"\nDone. Open: {(SITE / 'index.html').resolve()}")


if __name__ == "__main__":
    main()
