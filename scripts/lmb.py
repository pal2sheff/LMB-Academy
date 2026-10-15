"""Инструменты LMB Академии: проверка контента, сборка, предпросмотр, утверждение.

Требуется только Python 3.9+ (стандартная библиотека). Запуск из корня проекта:

    python scripts/lmb.py check                 проверка контента (ошибки -> код возврата 1)
    python scripts/lmb.py status                сводка по темам и вариантам
    python scripts/lmb.py build                 производственная сборка в dist/ (только утверждённое)
    python scripts/lmb.py preview               локальный предпросмотр с черновиками в preview/
    python scripts/lmb.py serve preview|dist    локальный сервер (по умолчанию порт 8000)
    python scripts/lmb.py new-lesson MODULE LESSON --title "..."
    python scripts/lmb.py checksum LESSON doctors|admins
    python scripts/lmb.py approve LESSON doctors|admins --reviewer "ФИО" [--date ГГГГ-ММ-ДД]

Команду approve запускает редактор только после решения ответственного врача.
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent

VARIANTS = [("doctors", "Врачам"), ("admins", "Администраторам")]
VARIANT_IDS = [v for v, _ in VARIANTS]
EDITORIAL_STATUSES = {"draft", "needs_clarification", "in_review", "approved", "archived"}
CONTENT_KINDS = {"outline", "summary"}
COVERAGE = {"concept", "safety", "clinical", "interpretation"}
# Порядок и ID 14 направлений из ТЗ (раздел 3). Новые направления добавляются после них.
CANONICAL_MODULE_IDS = ["mito", "infusion", "peptide", "hormone", "ozone", "lymph", "aging", "men", "women",
                        "pellets", "genetics", "estrogen-metabolites", "hms-osipov", "organic-acids"]
# Направления, добавленные после первоначальных 14 и обязательные в каталоге.
REQUIRED_EXTRA_MODULE_IDS = ["steroid-saliva"]
# Группы каталога в порядке показа (LMB_Audit_v2.md, раздел 3).
GROUPS = [("diagnostics", "Диагностика"), ("interventions", "Вмешательства"), ("foundations", "Основы и клинические направления")]
# Ключи встроенных иконок из site/app.js; неизвестный ключ показывается нейтральной иконкой документа.
ICON_KEYS = {"mitochondrion", "dna", "saliva-tube", "urine-molecule", "chromatogram", "urine-cycle", "infusion-bag",
             "peptide-chain", "hormone-receptor", "pellet-implant", "ozone-molecule", "lymph-vessel", "cell-clock", "male", "female", "doc"}
PUBLIC_SOURCE_FIELDS ={"id", "title", "author", "year", "type", "url", "note"}
SITE_FILES = ["index.html", "app.js", "styles.css"]
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TEST_REVIEWER_RE = re.compile(r"(^TEST-|ТЕСТ|фикстур)", re.I)


# ---------------------------------------------------------------- загрузка

class Report:
    def __init__(self):
        self.errors, self.warnings, self.notes = [], [], []

    def error(self, where, msg): self.errors.append(f"{where}: {msg}")
    def warn(self, where, msg): self.warnings.append(f"{where}: {msg}")
    def note(self, where, msg): self.notes.append(f"{where}: {msg}")

    def print(self, verbose=False):
        for e in self.errors: print("ОШИБКА  " + e)
        for w in self.warnings: print("ВНИМАНИЕ " + w)
        if verbose:
            for n in self.notes: print("ИНФО    " + n)
        print(f"Итого: ошибок {len(self.errors)}, предупреждений {len(self.warnings)}")


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_text(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_json(path, data):
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def read_body(lesson_dir, name):
    with open(lesson_dir / name, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


class Project:
    def __init__(self, root):
        self.root = Path(root)
        self.content = self.root / "content"
        self.modules = read_json(self.content / "modules.json")
        self.sources = {s["id"]: s for s in read_json(self.content / "sources" / "public.json")}
        syn = self.content / "synonyms.json"
        self.synonyms = read_json(syn)["groups"] if syn.exists() else []
        self.lessons = {}
        lessons_dir = self.content / "lessons"
        for d in sorted(p for p in lessons_dir.iterdir() if p.is_dir()):
            meta_path = d / "metadata.json"
            if meta_path.exists():
                self.lessons[d.name] = read_json(meta_path)

    def lesson_dir(self, lesson_id):
        return self.content / "lessons" / lesson_id

    def body(self, lesson_id, variant):
        v = self.lessons[lesson_id]["variants"].get(variant) or {}
        if not v.get("body"):
            return None
        p = self.lesson_dir(lesson_id) / v["body"]
        return read_body(self.lesson_dir(lesson_id), v["body"]) if p.exists() else None

    def extras(self, lesson_id, variant):
        v = self.lessons[lesson_id]["variants"].get(variant) or {}
        return collect_extras(self, lesson_id, v, self.body(lesson_id, variant))

    def checksum(self, lesson_id, variant):
        return compute_checksum(self.lessons[lesson_id], variant, self.body(lesson_id, variant), self.extras(lesson_id, variant))

    def approval_problem(self, lesson_id, variant):
        return approval_problem(self.lessons[lesson_id], variant, self.body(lesson_id, variant), self.extras(lesson_id, variant))


# ---------------------------------------------------------------- контрольная сумма

CHECKSUM_FIELDS = ["version", "contentKind", "coverage", "goal", "takeaway", "scope", "subtitle", "editorialSections",
                   "sources", "claims", "derivedFrom"]
# Необязательные поля учебного пакета. В контрольную сумму входят, только если заполнены,
# поэтому суммы прежних тем без этих полей не меняются.
PACKAGE_FIELDS = ["intro", "brief", "infographic", "media", "quiz"]
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
FILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
FIG_RE = re.compile(r'^!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)\s*$')
QUIZ_QUESTIONS = 5
SECRET_QUERY_RE = re.compile(r"(^|[?&])(token|access_token|key|api_key|apikey|password|pass|pwd|secret|sig|signature|auth)=", re.I)
YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def figure_names(md):
    return [m.group(2) for m in (FIG_RE.match(line.strip()) for line in (md or "").split("\n")) if m]


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def media_dir(project, lid):
    return project.content / "media" / lid


def collect_extras(project, lid, v, body, r=None, where=""):
    """Тексты и файлы учебного пакета варианта, входящие в контрольную сумму: введение, выжимка,
    тест и хеши иллюстраций. Пустой словарь, если пакет не заполнен."""
    d, ex = project.lesson_dir(lid), {}
    for key in ("intro", "brief", "quiz"):
        name = v.get(key)
        if not name:
            continue
        if not FILE_NAME_RE.match(name):
            if r: r.error(where, f"{key}: нужно имя файла в папке темы, а не путь: «{name}»")
            continue
        if not (d / name).exists():
            if r: r.error(where, f"{key}: файл «{name}» не найден")
            continue
        if key == "quiz":
            try:
                ex["quiz"] = read_json(d / name)
            except ValueError as e:
                if r: r.error(where, f"quiz: файл «{name}» не является корректным JSON ({e})")
        else:
            ex[key] = read_body(d, name)
    names = set(figure_names(body)) | set(figure_names(ex.get("intro"))) | set(figure_names(ex.get("brief")))
    if isinstance(v.get("infographic"), dict) and v["infographic"].get("src"):
        names.add(v["infographic"]["src"])
    images = {}
    for name in sorted(names):
        p = media_dir(project, lid) / name
        if FILE_NAME_RE.match(name) and p.suffix.lower() in MEDIA_EXT and p.exists():
            images[name] = file_sha256(p)
    if images:
        ex["images"] = images
    return ex


def split_sections(md):
    """[(заголовок ## или None для вступления, текст фрагмента)]"""
    parts, title, buf = [], None, []
    for line in md.replace("\r\n", "\n").split("\n"):
        m = re.match(r"^##\s+(.+?)\s*#*\s*$", line)
        if m and not line.startswith("###"):
            parts.append((title, "\n".join(buf)))
            title, buf = m.group(1), [line]
        else:
            buf.append(line)
    parts.append((title, "\n".join(buf)))
    return [p for p in parts if p[0] is not None or p[1].strip()]


def learning_view(md, editorial):
    """Текст учебного представления: без разделов, отмеченных в editorialSections. Исходник не меняется."""
    hidden = set(editorial or [])
    return "\n".join(text for title, text in split_sections(md) if title not in hidden).strip("\n") + "\n"


def compute_checksum(lesson_meta, variant, body_text, extras=None):
    """SHA-256 текста Markdown, клинически значимых метаданных варианта и учебного пакета
    (введение, выжимка, тест, описания и хеши иллюстраций, видео и ссылки)."""
    v = lesson_meta["variants"][variant]
    meta = {k: v.get(k) for k in CHECKSUM_FIELDS}
    meta.update({k: v[k] for k in PACKAGE_FIELDS if v.get(k)})
    payload = {
        "lessonId": lesson_meta["lessonId"], "title": lesson_meta["title"], "variant": variant,
        "meta": meta,
        "body": (body_text or "").replace("\r\n", "\n"),
    }
    if extras:
        payload["extras"] = extras
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def approval_problem(lesson_meta, variant, body_text, extras=None):
    """None, если запись утверждения действительна для текущего содержимого; иначе причина."""
    v = lesson_meta["variants"][variant]
    a = v.get("approval")
    if v.get("editorialStatus") != "approved":
        return "статус не approved"
    if not a:
        return "нет записи утверждения"
    if not (a.get("reviewer") or "").strip():
        return "в записи утверждения нет рецензента"
    if not DATE_RE.match(str(a.get("date") or "")):
        return "в записи утверждения нет даты ГГГГ-ММ-ДД"
    if a.get("version") != v.get("version"):
        return f"утверждена версия {a.get('version')}, текущая {v.get('version')}"
    if a.get("checksum") != compute_checksum(lesson_meta, variant, body_text, extras):
        return "содержимое изменено после утверждения (контрольная сумма не совпадает)"
    if TEST_REVIEWER_RE.search(a["reviewer"]) and os.environ.get("LMB_TEST_FIXTURES") != "1":
        return "рецензент из тестовой фикстуры недопустим в рабочем контенте"
    return None


def history_snapshots(project, lesson_id, variant):
    """Ранее утверждённые версии из history/, от новой к старой; только с действительной суммой."""
    hdir = project.lesson_dir(lesson_id) / "history"
    found = []
    if not hdir.exists():
        return found
    for meta_path in hdir.glob(f"{variant}-*.json"):
        snap = read_json(meta_path)
        md_path = meta_path.with_suffix(".md")
        body = read_body(hdir, md_path.name) if md_path.exists() else ""
        lesson_like = {"lessonId": lesson_id, "title": snap["title"], "variants": {variant: snap["variant"]}}
        extras = snap.get("extras") or {}
        valid = approval_problem(lesson_like, variant, body, extras) is None
        # Изображения не хранятся в снимке: версия пригодна, только если файлы не изменились.
        for name, sha in (extras.get("images") or {}).items():
            p = media_dir(project, lesson_id) / name
            if not p.exists() or file_sha256(p) != sha:
                valid = False
        found.append({"version": snap["variant"]["version"], "meta": snap, "body": body, "valid": valid, "extras": extras,
                      "checksum": snap["variant"]["approval"]["checksum"] if snap["variant"].get("approval") else None})
    found.sort(key=lambda s: tuple(int(x) for x in s["version"].split(".")), reverse=True)
    return found


# ---------------------------------------------------------------- Markdown

INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


class MarkdownError(Exception):
    pass


def render_inline(text, link_check):
    out, pos = [], 0
    for m in INLINE_LINK_RE.finditer(text):
        out.append(_inline_fmt(text[pos:m.start()]))
        label, url = m.group(1), m.group(2)
        href = link_check(url)
        ext = href.startswith("https://") or href.startswith("http://")
        attrs = ' target="_blank" rel="noopener noreferrer"' if ext else ""
        out.append(f'<a href="{html.escape(href)}"{attrs}>{_inline_fmt(label)}{" ↗" if ext else ""}</a>')
        pos = m.end()
    out.append(_inline_fmt(text[pos:]))
    return "".join(out)


def _inline_fmt(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", s)
    return s


def figure_html(url, alt, caption):
    a = html.escape(alt)
    cap = f"<figcaption>{html.escape(caption)}</figcaption>" if caption else ""
    return (f'<figure class="figure"><button type="button" class="zoom" data-zoom="{html.escape(url)}" aria-label="Увеличить рисунок: {a}">'
            f'<img src="{html.escape(url)}" alt="{a}" loading="lazy"></button>{cap}</figure>')


def render_markdown(md, link_check, image_check=None):
    """Небольшое подмножество Markdown: ##/### заголовки, абзацы, списки, таблицы, цитаты,
    **жирный**, *курсив*, `код`, [ссылки](url) и рисунок отдельной строкой ![описание](файл "подпись").
    HTML внутри текста экранируется."""
    lines = md.replace("\r\n", "\n").split("\n")
    out, toc, i, n = [], [], 0, len(lines)
    section_no = 0

    def is_table_sep(s):
        return bool(re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$", s))

    def cells(s):
        s = s.strip()
        if s.startswith("|"): s = s[1:]
        if s.endswith("|"): s = s[:-1]
        return [c.strip() for c in s.split("|")]

    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1; continue
        h = re.match(r"^(#{1,4})\s+(.+?)\s*#*\s*$", line)
        if h:
            level = len(h.group(1))
            if level == 1:
                raise MarkdownError(f"строка {i + 1}: заголовок первого уровня «# » не используется в теле, начните с «## »")
            title = h.group(2)
            if level == 2:
                section_no += 1
                sid = f"section-{section_no}"
                toc.append({"id": sid, "title": title})
                out.append(f'</section><section class="text-section" id="{sid}"><h2>{render_inline(title, link_check)}</h2>')
            else:
                out.append(f"<h{level}>{render_inline(title, link_check)}</h{level}>")
            i += 1; continue
        fig = FIG_RE.match(line.strip())
        if fig:
            if image_check is None:
                raise MarkdownError(f"строка {i + 1}: рисунки в этом тексте не поддерживаются")
            out.append(figure_html(image_check(fig.group(2), fig.group(1), fig.group(3)), fig.group(1), fig.group(3)))
            i += 1; continue
        if line.lstrip().startswith("|") and i + 1 < n and is_table_sep(lines[i + 1]):
            head = cells(line); i += 2
            rows = []
            while i < n and lines[i].lstrip().startswith("|"):
                rows.append(cells(lines[i])); i += 1
            th = "".join(f"<th>{render_inline(c, link_check)}</th>" for c in head)
            tb = "".join("<tr>" + "".join(f"<td>{render_inline(c, link_check)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f'<div class="table-wrap" tabindex="0"><table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>')
            continue
        lm = re.match(r"^(\s*)([-*]|\d+[.)])\s+(.*)$", line)
        if lm:
            ordered = lm.group(2)[0].isdigit()
            items = []
            while i < n:
                m2 = re.match(r"^(\s*)([-*]|\d+[.)])\s+(.*)$", lines[i])
                if m2 and m2.group(2)[0].isdigit() == ordered:
                    items.append(m2.group(3)); i += 1
                elif lines[i].startswith("  ") and lines[i].strip() and items:
                    items[-1] += " " + lines[i].strip(); i += 1
                else:
                    break
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{render_inline(t, link_check)}</li>" for t in items) + f"</{tag}>")
            continue
        if line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(lines[i][1:].strip()); i += 1
            out.append(f"<blockquote><p>{render_inline(' '.join(buf), link_check)}</p></blockquote>")
            continue
        buf = []
        while i < n and lines[i].strip() and not re.match(r"^(#{1,4}\s|>|\s*([-*]|\d+[.)])\s)", lines[i]) \
                and not FIG_RE.match(lines[i].strip()) \
                and not (lines[i].lstrip().startswith("|") and i + 1 < n and is_table_sep(lines[i + 1])):
            buf.append(lines[i].strip()); i += 1
        para = " ".join(buf)
        if "![" in para:
            raise MarkdownError(f"строка {i}: рисунок должен стоять отдельной строкой: ![описание](файл.png \"подпись\")")
        out.append(f"<p>{render_inline(para, link_check)}</p>")
    body = "".join(out)
    if body.startswith("</section>"):
        body = body[len("</section>"):]
    else:
        body = '<section class="text-section">' + body
    return body + "</section>", toc


def html_to_text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


# ---------------------------------------------------------------- проверка

def check_project(project, report=None):
    r = report or Report()
    mods = project.modules
    ids = [m.get("id") for m in mods]
    present = [i for i in ids if i in CANONICAL_MODULE_IDS]
    for cid in CANONICAL_MODULE_IDS + REQUIRED_EXTRA_MODULE_IDS:
        if cid not in ids:
            r.error("modules.json", f"отсутствует постоянное направление «{cid}»")
    group_titles = [t for _, t in GROUPS]
    seen_order = set()
    for m in mods:
        where = f"modules.json/{m.get('id')}"
        if m.get("category") not in group_titles:
            r.error(where, f"category должна быть одной из групп: {', '.join(group_titles)}")
        if not isinstance(m.get("displayOrder"), int) or isinstance(m.get("displayOrder"), bool):
            r.error(where, "displayOrder должен быть целым числом")
        elif (m.get("category"), m["displayOrder"]) in seen_order:
            r.error(where, f"displayOrder {m['displayOrder']} уже занят в группе «{m.get('category')}»")
        seen_order.add((m.get("category"), m.get("displayOrder")))
        if m.get("icon") not in ICON_KEYS:
            r.warn(where, f"неизвестный ключ иконки «{m.get('icon')}»; будет показана нейтральная иконка")
    if present != [c for c in CANONICAL_MODULE_IDS if c in ids]:
        r.error("modules.json", "нарушен порядок постоянных направлений из ТЗ")
    seen_ids, seen_n, owner = set(), set(), {}
    for m in mods:
        where = f"modules.json/{m.get('id')}"
        for f in ("id", "n", "title", "category", "lead", "lessons"):
            if not m.get(f):
                r.error(where, f"не заполнено поле {f}")
        if m.get("id") in seen_ids: r.error(where, "повторяющийся ID направления")
        if m.get("n") in seen_n: r.error(where, "повторяющийся номер направления")
        seen_ids.add(m.get("id")); seen_n.add(m.get("n"))
        if m.get("id") and not ID_RE.match(m["id"]): r.error(where, "ID должен состоять из латиницы, цифр и дефисов")
        for lid in m.get("lessons", []):
            if lid not in project.lessons:
                r.error(where, f"тема «{lid}» не найдена в content/lessons/{lid}/metadata.json")
            elif lid in owner:
                r.error(where, f"тема «{lid}» уже привязана к направлению «{owner[lid]}»; для вторичных ссылок используйте alsoInModules")
            else:
                owner[lid] = m["id"]
    for lid, meta in project.lessons.items():
        check_lesson(project, lid, meta, owner, r)
    used = {s["id"] for meta in project.lessons.values() for v in meta["variants"].values() if v for s in v.get("sources", [])}
    for sid, s in project.sources.items():
        extra = set(s) - PUBLIC_SOURCE_FIELDS
        if extra: r.error(f"sources/public.json/{sid}", f"недопустимые поля {sorted(extra)} (внутренние сведения хранятся в private/source-register.json)")
        if not s.get("title") or not s.get("type"): r.error(f"sources/public.json/{sid}", "нужны title и type")
        url = s.get("url")
        if url and not url.startswith("https://"): r.error(f"sources/public.json/{sid}", "ссылка должна быть внешней https://")
        if sid not in used: r.note(f"sources/public.json/{sid}", "источник нигде не используется")
    return r


def make_link_check(project, where, r):
    def check(url):
        if url.startswith("https://") or url.startswith("http://"):
            if url.startswith("http://"): r.warn(where, f"ссылка без https: {url}")
            return url
        m = re.match(r"^(?:lesson:|#lesson/)([a-z0-9-]+)$", url)
        if m:
            if m.group(1) not in project.lessons: r.error(where, f"ссылка на несуществующую тему «{m.group(1)}»")
            return f"#lesson/{m.group(1)}"
        m = re.match(r"^(?:module:|#module/)([a-z0-9-]+)$", url)
        if m:
            if m.group(1) not in {x["id"] for x in project.modules}: r.error(where, f"ссылка на несуществующее направление «{m.group(1)}»")
            return f"#module/{m.group(1)}"
        if url.startswith("#section-"):
            return url
        r.error(where, f"недопустимая ссылка «{url}»: разрешены https://, lesson:ID, module:ID")
        return "#"
    return check


def check_image_file(project, lid, name, where, r):
    """Иллюстрация из публичной папки content/media/<тема>/: имя, тип, наличие, безопасный SVG."""
    if not FILE_NAME_RE.match(name or ""):
        r.error(where, f"иллюстрация: нужно имя файла из content/media/{lid}/, а не путь или адрес: «{name}»"); return False
    p = media_dir(project, lid) / name
    if p.suffix.lower() not in MEDIA_EXT:
        r.error(where, f"иллюстрация «{name}»: допустимы {', '.join(sorted(MEDIA_EXT))}"); return False
    if not p.exists():
        r.error(where, f"иллюстрация «{name}» не найдена в content/media/{lid}/"); return False
    if p.stat().st_size > 3 * 1024 * 1024:
        r.warn(where, f"иллюстрация «{name}» больше 3 МБ; уменьшите размер для телефона")
    if p.suffix.lower() == ".svg" and re.search(r"<script|<foreignObject|\son\w+\s*=|javascript:|<iframe|xlink:href\s*=\s*[\"']https?:",
                                                p.read_text(encoding="utf-8", errors="replace"), re.I):
        r.error(where, f"иллюстрация «{name}»: SVG содержит сценарии, внешние ссылки или встроенный HTML")
        return False
    return True


def make_image_check(project, lid, where, r, used):
    def check(name, alt, caption):
        if not (alt or "").strip():
            r.error(where, f"у рисунка «{name}» нет текстового описания: ![описание](файл)")
        if check_image_file(project, lid, name, where, r):
            used.add(name)
        return f"media/{lid}/{name}"
    return check


def media_item(item, where, r):
    """Видео или внешний материал: только https, без учётных данных; для YouTube — проверенный ID."""
    from urllib.parse import urlparse, parse_qs
    if not isinstance(item, dict) or not (item.get("title") or "").strip():
        r.error(where, "media: у каждого элемента нужно название (title)"); return None
    url = (item.get("url") or "").strip()
    try:
        u = urlparse(url)
    except ValueError:
        u = None
    if not u or u.scheme != "https" or not u.hostname:
        r.error(where, f"media «{item.get('title')}»: нужен адрес https://"); return None
    if u.username or u.password or SECRET_QUERY_RE.search("?" + (u.query or "")):
        r.error(where, f"media «{item.get('title')}»: в ссылке не должно быть паролей, токенов и ключей доступа"); return None
    host = u.hostname.lower()
    yid, start = None, None
    q = parse_qs(u.query)
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        if u.path == "/watch":
            yid = (q.get("v") or [None])[0]
        else:
            m = re.match(r"^/(embed|shorts|live)/([^/?#]+)", u.path)
            yid = m.group(2) if m else None
    elif host == "youtu.be":
        yid = u.path.lstrip("/").split("/")[0]
    if yid is not None and not YOUTUBE_ID_RE.match(yid):
        r.error(where, f"media «{item.get('title')}»: не удалось распознать видео YouTube"); yid = None
    t = (q.get("t") or q.get("start") or [None])[0]
    if yid and t:
        m = re.match(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$", t)
        if m and any(m.groups()):
            start = int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)
    return {"title": item["title"].strip(), "url": url, "note": item.get("note"), "duration": item.get("duration"),
            "youtubeId": yid, "start": start}


def check_quiz(quiz, where, r):
    if not isinstance(quiz, dict) or not str(quiz.get("version") or "").strip():
        r.error(where, "quiz: нужна версия теста (version)"); return False
    qs = quiz.get("questions")
    if not isinstance(qs, list) or len(qs) != QUIZ_QUESTIONS:
        r.error(where, f"quiz: тест должен содержать {QUIZ_QUESTIONS} вопросов"); return False
    ok = True
    for i, q in enumerate(qs, 1):
        opts = q.get("options") if isinstance(q, dict) else None
        if not isinstance(q, dict) or not str(q.get("question") or "").strip():
            r.error(where, f"quiz: вопрос {i} без формулировки"); ok = False; continue
        if not isinstance(opts, list) or not 2 <= len(opts) <= 6 or not all(isinstance(o, str) and o.strip() for o in opts):
            r.error(where, f"quiz: вопрос {i} — нужно от 2 до 6 непустых вариантов"); ok = False; continue
        if not isinstance(q.get("answer"), int) or isinstance(q.get("answer"), bool) or not 0 <= q["answer"] < len(opts):
            r.error(where, f"quiz: вопрос {i} — answer должен быть номером варианта от 0 до {len(opts) - 1}"); ok = False
        if not str(q.get("explanation") or "").strip():
            r.error(where, f"quiz: вопрос {i} без пояснения (explanation)"); ok = False
    return ok


def check_package(project, lid, vname, v, body, extras, r, w):
    """Необязательные блоки учебного пакета варианта."""
    used = set()
    for key in ("intro", "brief"):
        if key in extras:
            try:
                render_markdown(extras[key], make_link_check(project, w, r), make_image_check(project, lid, w, r, used))
            except MarkdownError as e:
                r.error(w, f"{key}: {e}")
    info = v.get("infographic")
    if info is not None:
        if not isinstance(info, dict) or not info.get("src"):
            r.error(w, "infographic: нужен src — имя файла в content/media/<тема>/")
        else:
            check_image_file(project, lid, info["src"], w, r)
            if not (info.get("alt") or "").strip():
                r.error(w, "infographic: нужно короткое текстовое описание (alt)")
            if not (info.get("description") or "").strip():
                r.warn(w, "infographic: нет развёрнутого текстового описания (description)")
    if v.get("media") is not None:
        if not isinstance(v["media"], list):
            r.error(w, "media: нужен список")
        else:
            for item in v["media"]:
                media_item(item, w, r)
    if "quiz" in extras:
        check_quiz(extras["quiz"], w, r)


def check_lesson(project, lid, meta, owner, r):
    where = f"lessons/{lid}"
    if meta.get("lessonId") != lid: r.error(where, "lessonId не совпадает с именем папки")
    if not ID_RE.match(lid): r.error(where, "ID темы должен состоять из латиницы, цифр и дефисов")
    if lid not in owner: r.warn(where, "тема не указана ни в одном направлении modules.json и не будет показана")
    elif meta.get("moduleId") != owner[lid]: r.error(where, f"moduleId «{meta.get('moduleId')}» не совпадает с направлением «{owner[lid]}»")
    if not meta.get("title"): r.error(where, "нет названия темы")
    module_ids = {m["id"] for m in project.modules}
    for mid in meta.get("alsoInModules", []):
        if mid not in module_ids: r.error(where, f"alsoInModules: неизвестное направление «{mid}»")
    for rel in meta.get("relatedLessonIds", []):
        if rel not in project.lessons: r.error(where, f"relatedLessonIds: неизвестная тема «{rel}»")
    variants = meta.get("variants", {})
    for vname in variants:
        if vname not in VARIANT_IDS: r.error(where, f"неизвестный вариант «{vname}»")
    for vname in VARIANT_IDS:
        v = variants.get(vname)
        if v is None:
            continue
        w = f"{where}/{vname}"
        if v.get("editorialStatus") not in EDITORIAL_STATUSES: r.error(w, f"неизвестный editorialStatus «{v.get('editorialStatus')}»")
        if v.get("contentKind") not in CONTENT_KINDS: r.error(w, f"неизвестный contentKind «{v.get('contentKind')}»")
        if not VERSION_RE.match(str(v.get("version", ""))): r.error(w, "версия должна иметь вид 1.0.0")
        for c in v.get("coverage", []):
            if c not in COVERAGE: r.error(w, f"неизвестное значение coverage «{c}»")
        for f in ("updatedAt", "nextReviewAt"):
            if v.get(f) and not DATE_RE.match(v[f]): r.error(w, f"{f} должен иметь вид ГГГГ-ММ-ДД")
        for s in v.get("sources", []):
            if s.get("id") not in project.sources: r.error(w, f"неизвестный источник «{s.get('id')}» (нет в content/sources/public.json)")
        for c in v.get("claims", []):
            if c.get("sourceId") not in project.sources: r.error(w, f"утверждение «{c.get('id')}» ссылается на неизвестный источник «{c.get('sourceId')}»")
            if not c.get("locator"): r.warn(w, f"утверждение «{c.get('id')}» без страницы, слайда или времени")
        body = None
        if v.get("body"):
            name = v["body"]
            if "/" in name or "\\" in name or name.startswith("."):
                r.error(w, f"body должен быть именем файла в папке темы, а не путём: «{name}»")
            elif not (project.lesson_dir(lid) / name).exists():
                r.error(w, f"файл текста «{name}» не найден")
            else:
                body = read_body(project.lesson_dir(lid), name)
                try:
                    render_markdown(body, make_link_check(project, w, r), make_image_check(project, lid, w, r, set()))
                except MarkdownError as e:
                    r.error(w, str(e))
                titles = {t for t, _ in split_sections(body) if t}
                for t in v.get("editorialSections") or []:
                    if t not in titles:
                        r.error(w, f"editorialSections: в тексте нет раздела «## {t}»")
        elif v.get("contentKind") == "summary":
            r.error(w, "у саммари нет файла текста (body)")
        extras = collect_extras(project, lid, v, body, r, w)
        check_package(project, lid, vname, v, body, extras, r, w)
        if v.get("editorialStatus") == "approved":
            prob = approval_problem(meta, vname, body, extras)
            if prob: r.error(w, f"утверждение недействительно: {prob}. Производственная сборка остановлена")
        elif v.get("approval"):
            r.warn(w, "есть запись утверждения, но статус не approved")
        if vname == "doctors" and v.get("contentKind") == "summary" and v.get("editorialStatus") != "approved":
            r.note(w, f"черновик ({v.get('editorialStatus')}) — только в предпросмотре")
        if v.get("contentKind") == "summary" and not v.get("sources"):
            r.warn(w, "у саммари не указаны источники")
        if v.get("contentKind") == "summary" and v.get("sources") and all(not s.get("locator") for s in v["sources"]):
            r.note(w, "у источников нет локаторов (страница, слайд, время)")
    adm = variants.get("admins")
    if adm and adm.get("body"):
        sync = admin_sync_state(project, lid)
        if sync == "missing":
            r.error(f"{where}/admins", "нет derivedFrom: административная версия должна ссылаться на точную врачебную версию")
        elif sync == "needs_sync":
            r.warn(f"{where}/admins", "врачебная версия изменилась после создания выжимки — требуется сверка")
        if adm.get("editorialStatus") == "approved" and not doctors_version_was_approved(project, lid, adm.get("derivedFrom") or {}):
            r.error(f"{where}/admins", "выжимка утверждена на основе врачебной версии, у которой нет действительного утверждения")


def admin_sync_state(project, lid):
    meta = project.lessons[lid]
    adm = meta["variants"].get("admins") or {}
    if not adm.get("body"):
        return None
    d = adm.get("derivedFrom")
    if not d or not d.get("checksum") or not d.get("version"):
        return "missing"
    doc = meta["variants"].get("doctors") or {}
    current = project.checksum(lid, "doctors")
    if d.get("lessonId", lid) != lid or d["version"] != doc.get("version") or d["checksum"] != current:
        return "needs_sync"
    return "ok"


def doctors_version_was_approved(project, lid, derived):
    meta = project.lessons[lid]
    if project.approval_problem(lid, "doctors") is None:
        a = meta["variants"]["doctors"]["approval"]
        if a["version"] == derived.get("version") and a["checksum"] == derived.get("checksum"):
            return True
    return any(s["valid"] and s["version"] == derived.get("version") and s["checksum"] == derived.get("checksum")
               for s in history_snapshots(project, lid, "doctors"))


# ---------------------------------------------------------------- сборка

def resolve_variant(project, lid, vname, mode, r):
    """Что показывать на сайте для варианта темы в данном режиме сборки."""
    meta = project.lessons[lid]
    v = meta["variants"].get(vname)
    hidden = set((v or {}).get("editorialSections") or [])
    base = {"state": "pending", "program": [p for p in (v or {}).get("program") or [] if p not in hidden],
            "programNote": (v or {}).get("programNote")}
    if not v:
        return base
    if v.get("withdrawn"):
        return {"state": "withdrawn", "program": [], "withdrawnNote": v["withdrawn"].get("note") if isinstance(v["withdrawn"], dict) else None}
    if v.get("editorialStatus") == "archived":
        return {"state": "withdrawn", "program": []}
    body = project.body(lid, vname)
    extras = collect_extras(project, lid, v, body)
    approved_ok = body is not None and approval_problem(meta, vname, body, extras) is None
    chosen, fallback_version = None, None
    if v.get("contentKind") == "outline" and body is not None:
        chosen = ("outline", v, body, extras)
    elif v.get("contentKind") == "summary" and body is not None:
        if approved_ok:
            chosen = ("approved", v, body, extras)
        elif mode == "preview":
            chosen = ("draft", v, body, extras)
        else:
            for snap in history_snapshots(project, lid, vname):
                if snap["valid"]:
                    chosen = ("approved", snap["meta"]["variant"], snap["body"], snap["extras"])
                    fallback_version = snap["version"]
                    break
    if not chosen:
        return base
    state, vv, body, extras = chosen
    where = f"lessons/{lid}/{vname}"
    # HTML, оглавление, текст поиска и программа строятся из одного учебного представления.
    hidden = set(vv.get("editorialSections") or [])
    used = set()
    link_check, image_check = make_link_check(project, where, r), make_image_check(project, lid, where, r, used)
    body_html, toc = render_markdown(learning_view(body, hidden), link_check, image_check)
    package = {}
    if state != "outline":
        for key in ("intro", "brief"):
            if extras.get(key):
                package[key + "Html"] = render_markdown(extras[key], link_check, image_check)[0]
        info = vv.get("infographic")
        if isinstance(info, dict) and info.get("src") and check_image_file(project, lid, info["src"], where, r):
            used.add(info["src"])
            package["infographic"] = {"src": f"media/{lid}/{info['src']}", "alt": info.get("alt") or "",
                                      "caption": info.get("caption"), "description": info.get("description")}
        items = [x for x in (media_item(i, where, r) for i in vv.get("media") or []) if x]
        if items:
            package["media"] = items
        quiz = extras.get("quiz")
        if quiz and check_quiz(quiz, where, Report()):
            package["quiz"] = {"version": str(quiz["version"]), "questions": [
                {k: q[k] for k in ("question", "options", "answer", "explanation")} for q in quiz["questions"]]}
    text_parts = [html_to_text(package.get("introHtml", "")), html_to_text(body_html), html_to_text(package.get("briefHtml", ""))]
    out = {
        "state": state, "version": vv["version"], "updatedAt": vv.get("updatedAt"), "nextReviewAt": vv.get("nextReviewAt"),
        "goal": vv.get("goal"), "takeaway": vv.get("takeaway"), "scope": vv.get("scope"), "subtitle": vv.get("subtitle"),
        "coverage": vv.get("coverage", []),
        "html": body_html, "toc": toc,
        "program": [p for p in vv.get("program") or [] if p not in hidden] or [t["title"] for t in toc],
        "sources": [{"id": s["id"], "locator": s.get("locator"), "supports": s.get("supports")} for s in vv.get("sources", [])],
        "text": " ".join(t for t in text_parts if t),
        **package,
    }
    out["_images"] = sorted(used)
    if state == "approved":
        a = vv["approval"]
        out["approval"] = {"reviewer": a["reviewer"], "date": a["date"], "version": a["version"]}
    if fallback_version:
        out["fallbackNote"] = f"Показана ранее утверждённая версия {fallback_version}; новая редакция готовится."
    if state == "draft":
        out["editorialStatus"] = vv.get("editorialStatus")
    if vname == "admins":
        d = vv.get("derivedFrom") or {}
        out["derivedFrom"] = {"version": d.get("version")}
        out["needsSync"] = admin_sync_state(project, lid) == "needs_sync"
    return out


def build_data(project, mode, r, images=None):
    """images: множество (тема, файл) иллюстраций, на которые ссылается публикуемое представление."""
    lessons = {}
    for m in project.modules:
        for lid in m["lessons"]:
            meta = project.lessons.get(lid)
            if not meta:
                continue
            variants = {vn: resolve_variant(project, lid, vn, mode, r) for vn in VARIANT_IDS}
            for v in variants.values():
                for name in v.pop("_images", []):
                    if images is not None:
                        images.add((lid, name))
            lessons[lid] = {
                "id": lid, "moduleId": m["id"], "title": meta["title"], "order": meta.get("order", 1),
                "keywords": meta.get("keywords", []), "related": meta.get("relatedLessonIds", []),
                "alsoIn": meta.get("alsoInModules", []),
                "variants": variants,
            }
    used = {s["id"] for l in lessons.values() for v in l["variants"].values() for s in v.get("sources", [])}
    sources = {sid: {k: s.get(k) for k in ("title", "author", "year", "type", "url")} for sid, s in project.sources.items() if sid in used}
    return {
        "build": {"mode": mode, "builtAt": dt.date.today().isoformat()},
        "variants": [{"id": v, "label": label} for v, label in VARIANTS],
        "groups": [{"id": gid, "title": title} for gid, title in GROUPS],
        "modules": [{k: m.get(k) for k in ("id", "n", "title", "category", "displayOrder", "icon", "lead", "keywords", "lessons")}
                    for m in project.modules],
        "lessons": lessons, "sources": sources, "synonyms": project.synonyms,
    }


def build(project, mode, out_dir=None, allowed_parent=None):
    """mode: production -> dist/, preview -> preview/. Возвращает (Report, путь).
    Состав сборки: index.html, app.js, styles.css, data.js и только те иллюстрации из content/media/,
    на которые ссылается публикуемое представление."""
    r = check_project(project)
    if r.errors and mode == "production":
        return r, None
    out = Path(out_dir) if out_dir else project.root / ("dist" if mode == "production" else "preview")
    parent = Path(allowed_parent or project.root).resolve()
    if out.resolve() == parent or parent not in out.resolve().parents:
        raise SystemExit("Каталог сборки должен находиться внутри проекта")
    images = set()
    data = build_data(project, mode, r, images)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for f in SITE_FILES:
        shutil.copyfile(project.root / "site" / f, out / f)
    media_root = (project.content / "media").resolve()
    for lid, name in sorted(images):
        src = (media_dir(project, lid) / name).resolve()
        if media_root not in src.parents:
            r.error("сборка", f"иллюстрация вне content/media: {src}"); continue
        (out / "media" / lid).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, out / "media" / lid / name)
    js = "window.LMB_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    write_text(out / "data.js", js)
    expected = set(SITE_FILES) | {"data.js"} | {f"media/{lid}/{name}" for lid, name in images}
    actual = {str(p.relative_to(out)).replace("\\", "/") for p in out.rglob("*") if p.is_file()}
    if actual != expected:
        r.error("сборка", f"непредусмотренный состав файлов: {sorted(actual ^ expected)}")
    return r, out


# ---------------------------------------------------------------- команды

def cmd_check(project, args):
    r = check_project(project)
    r.print(verbose=args.verbose)
    return 1 if r.errors else 0


PACKAGE_LABELS = [("intro", "введение"), ("brief", "за 2 минуты"), ("infographic", "инфографика"), ("media", "видео"), ("quiz", "тест")]


def cmd_status(project, args):
    """Сводка для редактора; для саммари перечисляет незаполненные блоки учебного пакета."""
    print(f"{'Тема':32} {'Врачи':34} {'Администраторы':30}")
    for m in project.modules:
        print(f"{m['n']} {m['title']}")
        for lid in m["lessons"]:
            meta = project.lessons.get(lid)
            if not meta:
                print(f"   {lid:29} НЕТ МЕТАДАННЫХ"); continue
            cols = []
            for vn in VARIANT_IDS:
                v = meta["variants"].get(vn) or {}
                if not v.get("body"):
                    cols.append("материал готовится"); continue
                ok = project.approval_problem(lid, vn) is None
                s = f"{v.get('contentKind')} {v.get('version')} {v.get('editorialStatus')}{' ✓' if ok else ''}"
                if v.get("contentKind") == "summary":
                    missing = [label for key, label in PACKAGE_LABELS if not v.get(key)]
                    s += " · нет: " + ", ".join(missing) if missing else " · пакет полный"
                if vn == "admins" and admin_sync_state(project, lid) == "needs_sync":
                    s += " ТРЕБУЕТ СВЕРКИ"
                cols.append(s)
            print(f"   {lid:29} {cols[0]:34} {cols[1]}")
    return 0


def cmd_build(project, args, mode):
    r, out = build(project, mode)
    r.print(verbose=args.verbose)
    if out is None or r.errors and mode == "production":
        print("Сборка не выполнена: исправьте ошибки.")
        return 1
    data = read_data(out)
    counts = {}
    for l in data["lessons"].values():
        for vn, v in l["variants"].items():
            counts[(vn, v["state"])] = counts.get((vn, v["state"]), 0) + 1
    print(f"Готово: {out}")
    for (vn, st), c in sorted(counts.items()):
        print(f"   {vn:8} {st:10} {c}")
    return 0


def read_data(out):
    txt = (Path(out) / "data.js").read_text(encoding="utf-8")
    return json.loads(txt[len("window.LMB_DATA = "):].rstrip().rstrip(";"))


def cmd_bundle(project, args):
    """Однофайловая страница из готовой сборки (для закрытого просмотра на других устройствах).
    Результат — фрагмент без <!doctype>/<html>/<head>/<body>, все ресурсы встроены."""
    src = project.root / args.target
    if not (src / "data.js").exists():
        print(f"Нет сборки в {src}"); return 1
    page = (src / "index.html").read_text(encoding="utf-8")
    css = (src / "styles.css").read_text(encoding="utf-8")
    data = (src / "data.js").read_text(encoding="utf-8")
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml"}

    def inline(m):
        p = src / "media" / m.group(1) / m.group(2)
        if not p.exists():
            return m.group(0)
        import base64
        return f"data:{mime[p.suffix.lower()]};base64," + base64.b64encode(p.read_bytes()).decode("ascii")
    # Однофайловая страница не может ссылаться на соседние файлы: иллюстрации встраиваются.
    data = re.sub(r"media/([a-z0-9-]+)/([A-Za-z0-9][A-Za-z0-9._-]*)", inline, data).replace("</", "<\\/")
    app = (src / "app.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    body = page[page.index("<body>") + len("<body>"): page.index("</body>")]
    title = re.search(r"<title>(.*?)</title>", page).group(1).split(" — ")[0]
    out = (f"<title>{title}</title>\n<meta name=\"robots\" content=\"noindex, nofollow\">\n<style>\n:root{{color-scheme:light}}\n{css}</style>\n"
           f"{body.strip()}\n<script>window.LMB_EMBEDDED = true;\n{data}</script>\n<script>\n{app}</script>\n")
    dest = project.root / "bundle" / f"lmb-academy-{args.target}.html"
    write_text(dest, out)
    print(f"Готово: {dest} ({len(out.encode('utf-8')) // 1024} КБ)")
    return 0


def cmd_serve(project, args):
    import functools
    import http.server
    target = project.root / ("demo/site" if args.target == "demo" else args.target)
    if not (target / "index.html").exists():
        print(f"Нет сборки в {target}. Сначала выполните: python scripts/lmb.py {'build' if args.target == 'dist' else 'preview'}")
        return 1
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(target))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as srv:
        print(f"Открыть: http://127.0.0.1:{args.port}/  (Ctrl+C — остановить)")
        srv.serve_forever()


def cmd_checksum(project, args):
    print(project.checksum(args.lesson, args.variant))
    return 0


def cmd_demo(project, args):
    """Локальная демонстрация шаблона на нейтральной технической фикстуре tests/fixtures/demo-lesson.
    Результат — demo/site (вне dist/ и preview/, не публикуется). Медицинского содержания не создаёт."""
    fixture = project.root / "tests" / "fixtures" / "demo-lesson"
    demo = project.root / "demo"
    src = demo / "src"
    if demo.exists():
        shutil.rmtree(demo)
    for d in ("content", "site", "templates"):
        shutil.copytree(project.root / d, src / d)
    module = read_json(fixture / "module.json")
    mods = read_json(src / "content" / "modules.json")
    module["n"] = f"{max(int(m['n']) for m in mods) + 1:02d}"
    module["displayOrder"] = max(m["displayOrder"] for m in mods if m["category"] == module["category"]) + 1
    mods.append(module)
    write_json(src / "content" / "modules.json", mods)
    lid = module["lessons"][0]
    shutil.copytree(fixture / "lesson", src / "content" / "lessons" / lid)
    shutil.copytree(fixture / "media", src / "content" / "media" / lid)
    r, out = build(Project(src), "preview", demo / "site", allowed_parent=demo)
    r.print()
    print(f"Демонстрация: {out}\nОткрыть: python scripts/lmb.py serve demo  →  http://127.0.0.1:8000/#lesson/{lid}")
    return 1 if r.errors else 0


def cmd_approve(project, args):
    lid, vn = args.lesson, args.variant
    meta = project.lessons.get(lid)
    if not meta or not (meta["variants"].get(vn) or {}).get("body"):
        print("Тема или текст варианта не найдены"); return 1
    v = meta["variants"][vn]
    if v.get("contentKind") != "summary":
        print("Утверждается только саммари (contentKind = summary)"); return 1
    if not args.reviewer.strip():
        print("Укажите рецензента"); return 1
    if vn == "admins":
        d = v.get("derivedFrom") or {}
        if not doctors_version_was_approved(project, lid, d):
            print("Отказ: derivedFrom должен указывать на утверждённую врачебную версию (version и checksum)."); return 1
    r = check_project(project)
    own = [e for e in r.errors if e.startswith(f"lessons/{lid}/{vn}") and "утверждение недействительно" not in e]
    if own:
        print("Отказ: сначала исправьте ошибки темы:"); [print("   " + e) for e in own]; return 1
    body = project.body(lid, vn)
    extras = project.extras(lid, vn)
    date = args.date or dt.date.today().isoformat()
    v["editorialStatus"] = "approved"
    v["approval"] = {"version": v["version"], "checksum": compute_checksum(meta, vn, body, extras), "reviewer": args.reviewer.strip(),
                     "date": date, "note": args.note}
    d = project.lesson_dir(lid)
    write_json(d / "metadata.json", meta)
    hist = d / "history"
    write_text(hist / f"{vn}-{v['version']}.md", body)
    # Снимок хранит тексты пакета; иллюстрации проверяются по хешам при использовании снимка.
    write_json(hist / f"{vn}-{v['version']}.json", {"title": meta["title"], "variant": v, "extras": extras})
    print(f"Утверждено: {lid}/{vn} {v['version']} — {args.reviewer} {date}")
    print(f"Контрольная сумма: {v['approval']['checksum']}")
    return 0


def cmd_new_lesson(project, args):
    mod = next((m for m in project.modules if m["id"] == args.module), None)
    if not mod:
        print(f"Нет направления «{args.module}»"); return 1
    if not ID_RE.match(args.lesson) or args.lesson in project.lessons:
        print("ID темы занят или содержит недопустимые символы"); return 1
    d = project.lesson_dir(args.lesson)
    tpl = (project.root / "templates" / "doctor_summary.md").read_text(encoding="utf-8")
    body = tpl[tpl.index("## "):]
    body = body[:body.index("Редакторские вопросы")].rstrip() + "\n" if "Редакторские вопросы" in body else body
    write_text(d / "doctors.md", body)
    empty = {"version": "0.0.0", "editorialStatus": "draft", "contentKind": "outline", "coverage": [], "body": None,
             "updatedAt": None, "nextReviewAt": None, "goal": None, "takeaway": None, "scope": None, "subtitle": None, "program": [],
             "sources": [], "claims": [], "approval": None}
    meta = {"schemaVersion": 1, "lessonId": args.lesson, "moduleId": args.module, "title": args.title,
            "order": len(mod["lessons"]) + 1, "keywords": [], "relatedLessonIds": [], "alsoInModules": [],
            "variants": {"doctors": {**empty, "version": "0.1.0", "contentKind": "summary", "body": "doctors.md",
                                     "updatedAt": dt.date.today().isoformat()},
                         "admins": {**empty, "derivedFrom": None}}}
    write_json(d / "metadata.json", meta)
    mod["lessons"].append(args.lesson)
    write_json(project.content / "modules.json", project.modules)
    print(f"Создана тема {d}. Заполните doctors.md и метаданные, затем: python scripts/lmb.py check")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lmb", description="Инструменты LMB Академии")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="корень проекта (по умолчанию — папка над scripts/)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check"); p.add_argument("-v", "--verbose", action="store_true")
    sub.add_parser("status")
    p = sub.add_parser("build"); p.add_argument("-v", "--verbose", action="store_true")
    p = sub.add_parser("preview"); p.add_argument("-v", "--verbose", action="store_true")
    p = sub.add_parser("serve"); p.add_argument("target", choices=["preview", "dist", "demo"]); p.add_argument("--port", type=int, default=8000)
    sub.add_parser("demo")
    p = sub.add_parser("bundle"); p.add_argument("target", choices=["preview", "dist"])
    p = sub.add_parser("checksum"); p.add_argument("lesson"); p.add_argument("variant", choices=VARIANT_IDS)
    p = sub.add_parser("approve"); p.add_argument("lesson"); p.add_argument("variant", choices=VARIANT_IDS)
    p.add_argument("--reviewer", required=True); p.add_argument("--date"); p.add_argument("--note")
    p = sub.add_parser("new-lesson"); p.add_argument("module"); p.add_argument("lesson"); p.add_argument("--title", required=True)
    args = ap.parse_args(argv)
    project = Project(args.root)
    if args.cmd == "check": return cmd_check(project, args)
    if args.cmd == "status": return cmd_status(project, args)
    if args.cmd == "build": return cmd_build(project, args, "production")
    if args.cmd == "preview": return cmd_build(project, args, "preview")
    if args.cmd == "serve": return cmd_serve(project, args)
    if args.cmd == "demo": return cmd_demo(project, args)
    if args.cmd == "bundle": return cmd_bundle(project, args)
    if args.cmd == "checksum": return cmd_checksum(project, args)
    if args.cmd == "approve": return cmd_approve(project, args)
    if args.cmd == "new-lesson": return cmd_new_lesson(project, args)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
