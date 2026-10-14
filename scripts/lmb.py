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

VARIANTS = [("doctors", "Для врачей"), ("admins", "Для администраторов")]
VARIANT_IDS = [v for v, _ in VARIANTS]
EDITORIAL_STATUSES = {"draft", "needs_clarification", "in_review", "approved", "archived"}
CONTENT_KINDS = {"outline", "summary"}
COVERAGE = {"concept", "safety", "clinical", "interpretation"}
# Порядок и ID 14 направлений из ТЗ (раздел 3). Новые направления добавляются после них.
CANONICAL_MODULE_IDS = ["mito", "infusion", "peptide", "hormone", "ozone", "lymph", "aging", "men", "women",
                        "pellets", "genetics", "estrogen-metabolites", "hms-osipov", "organic-acids"]
PUBLIC_SOURCE_FIELDS = {"id", "title", "author", "year", "type", "url", "note"}
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


# ---------------------------------------------------------------- контрольная сумма

CHECKSUM_FIELDS = ["version", "contentKind", "coverage", "goal", "takeaway", "scope", "sources", "claims", "derivedFrom"]


def compute_checksum(lesson_meta, variant, body_text):
    """SHA-256 текста Markdown и клинически значимых метаданных варианта."""
    v = lesson_meta["variants"][variant]
    payload = {
        "lessonId": lesson_meta["lessonId"], "title": lesson_meta["title"], "variant": variant,
        "meta": {k: v.get(k) for k in CHECKSUM_FIELDS},
        "body": (body_text or "").replace("\r\n", "\n"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def approval_problem(lesson_meta, variant, body_text):
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
    if a.get("checksum") != compute_checksum(lesson_meta, variant, body_text):
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
        valid = approval_problem(lesson_like, variant, body) is None
        found.append({"version": snap["variant"]["version"], "meta": snap, "body": body, "valid": valid,
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


def render_markdown(md, link_check):
    """Небольшое подмножество Markdown: ##/### заголовки, абзацы, списки, таблицы, цитаты,
    **жирный**, *курсив*, `код`, [ссылки](url). HTML внутри текста экранируется."""
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
                out.append(f'</section><section class="text-section" id="{sid}"><h2><span>{section_no:02d}</span>{render_inline(title, link_check)}</h2>')
            else:
                out.append(f"<h{level}>{render_inline(title, link_check)}</h{level}>")
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
                and not (lines[i].lstrip().startswith("|") and i + 1 < n and is_table_sep(lines[i + 1])):
            buf.append(lines[i].strip()); i += 1
        out.append(f"<p>{render_inline(' '.join(buf), link_check)}</p>")
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
    for cid in CANONICAL_MODULE_IDS:
        if cid not in ids:
            r.error("modules.json", f"отсутствует постоянное направление «{cid}»")
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
                    render_markdown(body, make_link_check(project, w, r))
                except MarkdownError as e:
                    r.error(w, str(e))
        elif v.get("contentKind") == "summary":
            r.error(w, "у саммари нет файла текста (body)")
        if v.get("editorialStatus") == "approved":
            prob = approval_problem(meta, vname, body)
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
    current = compute_checksum(meta, "doctors", project.body(lid, "doctors"))
    if d.get("lessonId", lid) != lid or d["version"] != doc.get("version") or d["checksum"] != current:
        return "needs_sync"
    return "ok"


def doctors_version_was_approved(project, lid, derived):
    meta = project.lessons[lid]
    if approval_problem(meta, "doctors", project.body(lid, "doctors")) is None:
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
    base = {"state": "pending", "program": (v or {}).get("program") or [], "programNote": (v or {}).get("programNote")}
    if not v:
        return base
    if v.get("withdrawn"):
        return {"state": "withdrawn", "program": [], "withdrawnNote": v["withdrawn"].get("note") if isinstance(v["withdrawn"], dict) else None}
    if v.get("editorialStatus") == "archived":
        return {"state": "withdrawn", "program": []}
    body = project.body(lid, vname)
    approved_ok = body is not None and approval_problem(meta, vname, body) is None
    chosen, fallback_version = None, None
    if v.get("contentKind") == "outline" and body is not None:
        chosen = ("outline", v, body)
    elif v.get("contentKind") == "summary" and body is not None:
        if approved_ok:
            chosen = ("approved", v, body)
        elif mode == "preview":
            chosen = ("draft", v, body)
        else:
            for snap in history_snapshots(project, lid, vname):
                if snap["valid"]:
                    chosen = ("approved", snap["meta"]["variant"], snap["body"])
                    fallback_version = snap["version"]
                    break
    if not chosen:
        return base
    state, vv, body = chosen
    where = f"lessons/{lid}/{vname}"
    body_html, toc = render_markdown(body, make_link_check(project, where, r))
    out = {
        "state": state, "version": vv["version"], "updatedAt": vv.get("updatedAt"), "nextReviewAt": vv.get("nextReviewAt"),
        "goal": vv.get("goal"), "takeaway": vv.get("takeaway"), "scope": vv.get("scope"), "coverage": vv.get("coverage", []),
        "html": body_html, "toc": toc, "program": vv.get("program") or [t["title"] for t in toc],
        "sources": [{"id": s["id"], "locator": s.get("locator"), "supports": s.get("supports")} for s in vv.get("sources", [])],
        "text": html_to_text(body_html),
    }
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


def build_data(project, mode, r):
    lessons = {}
    for m in project.modules:
        for lid in m["lessons"]:
            meta = project.lessons.get(lid)
            if not meta:
                continue
            lessons[lid] = {
                "id": lid, "moduleId": m["id"], "title": meta["title"], "order": meta.get("order", 1),
                "keywords": meta.get("keywords", []), "related": meta.get("relatedLessonIds", []),
                "alsoIn": meta.get("alsoInModules", []),
                "variants": {vn: resolve_variant(project, lid, vn, mode, r) for vn in VARIANT_IDS},
            }
    used = {s["id"] for l in lessons.values() for v in l["variants"].values() for s in v.get("sources", [])}
    sources = {sid: {k: s.get(k) for k in ("title", "author", "year", "type", "url")} for sid, s in project.sources.items() if sid in used}
    return {
        "build": {"mode": mode, "builtAt": dt.date.today().isoformat()},
        "variants": [{"id": v, "label": label} for v, label in VARIANTS],
        "modules": [{k: m.get(k) for k in ("id", "n", "title", "category", "icon", "lead", "keywords", "lessons")} for m in project.modules],
        "lessons": lessons, "sources": sources, "synonyms": project.synonyms,
    }


def build(project, mode, out_dir=None):
    """mode: production -> dist/, preview -> preview/. Возвращает (Report, путь)."""
    r = check_project(project)
    if r.errors and mode == "production":
        return r, None
    out = Path(out_dir) if out_dir else project.root / ("dist" if mode == "production" else "preview")
    if out.resolve() == project.root.resolve() or project.root.resolve() not in out.resolve().parents:
        raise SystemExit("Каталог сборки должен находиться внутри проекта")
    data = build_data(project, mode, r)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for f in SITE_FILES:
        shutil.copyfile(project.root / "site" / f, out / f)
    js = "window.LMB_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    write_text(out / "data.js", js)
    expected = set(SITE_FILES) | {"data.js"}
    actual = {str(p.relative_to(out)).replace("\\", "/") for p in out.rglob("*") if p.is_file()}
    if actual != expected:
        r.error("сборка", f"непредусмотренный состав файлов: {sorted(actual ^ expected)}")
    return r, out


# ---------------------------------------------------------------- команды

def cmd_check(project, args):
    r = check_project(project)
    r.print(verbose=args.verbose)
    return 1 if r.errors else 0


def cmd_status(project, args):
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
                ok = approval_problem(meta, vn, project.body(lid, vn)) is None
                s = f"{v.get('contentKind')} {v.get('version')} {v.get('editorialStatus')}{' ✓' if ok else ''}"
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
    data = (src / "data.js").read_text(encoding="utf-8").replace("</", "<\\/")
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
    target = project.root / args.target
    if not (target / "index.html").exists():
        print(f"Нет сборки в {target}. Сначала выполните: python scripts/lmb.py {'build' if args.target == 'dist' else 'preview'}")
        return 1
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(target))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as srv:
        print(f"Открыть: http://127.0.0.1:{args.port}/  (Ctrl+C — остановить)")
        srv.serve_forever()


def cmd_checksum(project, args):
    meta = project.lessons[args.lesson]
    print(compute_checksum(meta, args.variant, project.body(args.lesson, args.variant)))
    return 0


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
    date = args.date or dt.date.today().isoformat()
    v["editorialStatus"] = "approved"
    v["approval"] = {"version": v["version"], "checksum": compute_checksum(meta, vn, body), "reviewer": args.reviewer.strip(),
                     "date": date, "note": args.note}
    d = project.lesson_dir(lid)
    write_json(d / "metadata.json", meta)
    hist = d / "history"
    write_text(hist / f"{vn}-{v['version']}.md", body)
    write_json(hist / f"{vn}-{v['version']}.json", {"title": meta["title"], "variant": v})
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
             "updatedAt": None, "nextReviewAt": None, "goal": None, "takeaway": None, "scope": None, "program": [],
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
    p = sub.add_parser("serve"); p.add_argument("target", choices=["preview", "dist"]); p.add_argument("--port", type=int, default=8000)
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
