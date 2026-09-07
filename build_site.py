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
    site/assets/style.css                  static stylesheet
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
#     half of this fix: nudging list-continuation content indented to a *marker-width*
#     multiple (2-3 spaces, as valid CommonMark authors it under "- "/"1. ") up to a
#     tab_length multiple so it's actually recognized as part of the list item.
MD_EXTENSIONS = ["extra", "md_in_html", "sane_lists", "pymdownx.superfences"]

_LIST_MARKER_RE = re.compile(r"^( *)(?:[-*+]|\d{1,9}[.)])( +)")
_TOP_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
_INDENTED_FENCE_RE = re.compile(r"^( +)(`{3,}|~{3,})")


def normalize_list_continuation_indentation(text: str) -> str:
    """Re-indent list-item continuation content (paragraphs, fenced code, anything
    else) so python-markdown's list processor -- which reasons in fixed 4-space
    "tab_length" steps, unlike CommonMark's marker-width-based model -- recognizes it
    as part of the list item instead of dropping it back to loose top-level content
    (which, for a fenced block specifically, also means the fence marker itself no
    longer gets recognized and leaks through as literal text).

    Continuation content indented 2-3 spaces -- correct, valid CommonMark under "- "
    or "1. " -- sits *inside* python-markdown's first 4-space indent step but doesn't
    *equal* it, so it's invisible to the list processor; the same is true one level
    deeper at 5-7 spaces, and so on. Rounding such an indent up to the next multiple
    of 4 (2,3->4; 5,6,7->8; ...) is what makes each level of nesting land on a step
    boundary the list processor actually checks for, while an indent that's already
    an exact multiple of 4 is left untouched.

    This tracks open list levels by column (pushed on each marker line, popped on
    dedent) purely so it only ever touches indentation that's actually inside a list
    item's continuation zone -- never top-level content that merely happens to be
    indented for other reasons (which could otherwise be misread as "should be a
    code block" once nudged to a 4-space multiple). It only ever adds whitespace
    ahead of lines already identified as being in-scope -- it never touches file
    contents on disk, and column-0 fences are left completely alone (handled
    correctly already, and copied through verbatim so a code sample that itself
    *contains* example lines looking like an indented fence is never misread)."""
    lines = text.split("\n")
    out = []
    stack = []  # ascending list of open list levels' continuation-start columns
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
            marker_col = len(m.group(1))
            while stack and marker_col < stack[-1]:
                stack.pop()
            cont_col = len(m.group(0))
            if not stack or stack[-1] != cont_col:
                stack.append(cont_col)
            out.append(line)
            i += 1
            continue

        if indent == 0:
            stack.clear()
            out.append(line)
            i += 1
            continue

        while stack and indent < stack[-1]:
            stack.pop()

        if not stack or indent % 4 == 0:
            out.append(line)
            i += 1
            continue

        new_indent = -(-indent // 4) * 4  # ceil to next multiple of 4
        delta = new_indent - indent
        pad = " " * delta

        m_fence = _INDENTED_FENCE_RE.match(line)
        if m_fence:
            fence = m_fence.group(2)
            close_re = re.compile(r"^ {" + str(indent) + "}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$")
            out.append(pad + line)
            i += 1
            while i < n and not close_re.match(lines[i]):
                out.append(pad + lines[i])
                i += 1
            if i < n:
                out.append(pad + lines[i])
                i += 1
            continue

        # Any other continuation block (a paragraph, most commonly): shift this line
        # and every directly-following line indented at least this much -- i.e. the
        # same block, including any of its own further-nested content -- stopping at
        # a blank line or a dedent back out of it.
        while i < n and lines[i].strip() != "" and (len(lines[i]) - len(lines[i].lstrip(" "))) >= indent:
            out.append(pad + lines[i])
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


PAGE_TEMPLATE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{css_path}">
</head>
<body>
<header class="site-header">
  <a class="site-header__home" href="{home_path}">The Odin Project 日本語版 (ローカルプレビュー)</a>
</header>
{body}
</body>
</html>
"""


def write_page(path: Path, title: str, body: str, css_path: str, home_path: str, lang="ja"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        PAGE_TEMPLATE.format(
            lang=lang, title=html.escape(title or ""), body=body, css_path=css_path, home_path=home_path
        ),
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

    body = f"""
<div class="lesson">
  <div class="lesson-header">
    <p class="lesson-header__course"><a href="index.html">{html.escape(course_slug)}</a></p>
    <h1 class="lesson-header__title">{html.escape(lesson['title'] or '')} {badge}</h1>
    {'<p class="lesson-header__desc">' + html.escape(lesson['description']) + '</p>' if lesson['description'] else ''}
  </div>
  <div class="lesson-content">
    {content_html}
  </div>
</div>
"""
    write_page(out_path, lesson["title"] or slug, body, "../assets/style.css", "../index.html", lang=lang)
    return slug


def build_course_index(course_key: str, course: dict, out_dir: Path):
    rows = []
    for section in course["sections"]:
        items = []
        for lesson in section["lessons"]:
            _, lang = resolve_source(lesson["url"])
            slug = slug_for(lesson["url"]) if lesson["url"] else re.sub(r"\W+", "_", lesson["title"] or "untitled") + ".html"
            badge_class = "done" if lang == "ja" else ("fallback" if lang == "en" else "missing")
            project_tag = " 🛠" if lesson["is_project"] else ""
            items.append(
                f'<li class="nav-lesson nav-lesson--{badge_class}">'
                f'<a href="{slug}">{html.escape(lesson["title"] or slug)}{project_tag}</a></li>'
            )
        rows.append(
            f'<section class="nav-section"><h2>{html.escape(section["title"] or "")}</h2>'
            f'<ul>{"".join(items)}</ul></section>'
        )

    body = f"""
<div class="course-index">
  <h1>{html.escape(course['title'] or course_key)}</h1>
  <p class="legend">
    <span class="nav-lesson--done">■</span> 翻訳済み &nbsp;
    <span class="nav-lesson--fallback">■</span> 未翻訳 (英語) &nbsp;
    <span class="nav-lesson--missing">■</span> ファイルが見つかりません
  </p>
  {''.join(rows)}
</div>
"""
    write_page(out_dir / "index.html", course["title"] or course_key, body, "../assets/style.css", "../index.html")


def build_top_index(built_courses):
    items = "".join(
        f'<li><a href="{key}/index.html">{html.escape(course["title"] or key)}</a></li>'
        for key, course in built_courses
    )
    body = f"""
<div class="top-index">
  <h1>The Odin Project — 日本語版 (ローカルプレビュー)</h1>
  <p>これは翻訳作業を確認するためのローカル専用プレビューです。公開・配布はしないでください。</p>
  <ul>{items}</ul>
</div>
"""
    write_page(SITE / "index.html", "The Odin Project 日本語版", body, "assets/style.css", "index.html")


CSS = """
:root {
  --bg: #ffffff; --fg: #24292e; --muted: #6a737d; --panel: #f3f3f3;
  --accent: #1e5a8a; --border: #e1e4e8; --done: #2e8b57; --fallback: #b8860b; --missing: #c0392b;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font-family: system-ui, "Segoe UI", "Yu Gothic", "Hiragino Sans", sans-serif;
  line-height: 1.7;
}
.site-header {
  padding: 12px 24px; border-bottom: 1px solid var(--border); background: #fafbfc;
}
.site-header__home { color: var(--accent); text-decoration: none; font-weight: 600; }
.top-index, .course-index, .lesson { max-width: 840px; margin: 0 auto; padding: 32px 24px 80px; }
h1 { font-size: 1.8em; }
.legend { color: var(--muted); font-size: 0.9em; }
.nav-lesson--done, .nav-lesson--fallback, .nav-lesson--missing { font-weight: bold; }
.nav-lesson--done { color: var(--done); }
.nav-lesson--fallback { color: var(--fallback); }
.nav-lesson--missing { color: var(--missing); }
.nav-lesson--done a { color: var(--fg); }
.nav-lesson--fallback a { color: var(--fg); }
.nav-lesson--missing a { color: var(--muted); }
.nav-section ul { list-style: none; padding-left: 0; }
.nav-section li { padding: 4px 0; }
.lesson-header__course a { color: var(--muted); text-decoration: none; font-size: 0.9em; }
.lesson-header__title { margin-bottom: 4px; }
.lesson-header__desc { color: var(--muted); }
.lang-badge { font-size: 0.5em; padding: 2px 8px; border-radius: 10px; vertical-align: middle; }
.lang-badge--ja { background: #e6f4ea; color: var(--done); }
.lang-badge--en { background: #fdf3d8; color: var(--fallback); }
.lesson-content h3 { margin-top: 2.2em; font-size: 1.4em; }
.lesson-content h3:first-child { margin-top: 0; }
.lesson-content h4 { font-size: 1.1em; }
.lesson-content pre {
  background: #282c34; color: #eee; padding: 14px 16px; overflow-x: auto; border-radius: 6px;
}
.lesson-content code { background: var(--panel); padding: 0.15em 0.4em; border-radius: 4px; }
.lesson-content pre code { background: none; padding: 0; }
.lesson-content img { max-width: 100%; }
.lesson-content .lesson-content__panel {
  background: var(--panel); padding: 1.4em 1.6em; margin: 20px 0 40px; border-radius: 6px;
}
.lesson-content details {
  border: 1px solid var(--border); border-radius: 6px; padding: 10px 16px; margin: 10px 0;
}
.lesson-content summary { cursor: pointer; font-weight: 600; }
.notice { padding: 14px 18px; border-radius: 6px; }
.notice--missing { background: #fdecea; color: var(--missing); }
"""


def main():
    SITE.mkdir(exist_ok=True)
    (SITE / "assets").mkdir(exist_ok=True)
    (SITE / "assets" / "style.css").write_text(CSS, encoding="utf-8")

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
