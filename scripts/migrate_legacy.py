"""Одноразовый перенос текстов прототипа (legacy/prototype-1bdedd4/content.js) в content/.

Запуск из корня проекта:
    python scripts/migrate_legacy.py            # перенос (не перезаписывает существующие темы)
    python scripts/migrate_legacy.py --verify   # только сверка перенесённых текстов с исходником

Скрипт сохраняется для прослеживаемости переноса. Медицинский текст переносится дословно:
каждый блок прототипа становится разделом `## Заголовок` в doctors.md. Все перенесённые
варианты получают editorialStatus = draft и не имеют записи об утверждении.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "legacy" / "prototype-1bdedd4" / "content.js"
MIGRATION_DATE = "2026-10-14"  # дата редакции, указанная в прототипе («Редакция 14.10.2026»)

# Постоянные ID публичного реестра источников. Ключ — точное название из прототипа.
SOURCE_IDS = {
    "МИТОпаспорт_и_12_признаков_старения.pptx": ("lmb-mito-presentation", "Учебная презентация (внутренний материал)"),
    "МК митохондрии 05.07.26docx.docx": ("lmb-mk-mito-program", "Программа мастер-класса (внутренний материал)"),
    "СОП-12_Назначение_и_сопровождение_инфузионной_терапии_Love_my_body.docx": ("lmb-sop-12", "СОП клиники"),
    "СОП-08_Подкожное_введение_пептидных_препаратов_Love_my_body.docx": ("lmb-sop-08", "СОП клиники"),
    "СОП-10_Озонотерапия_и_БАГОТ_Love_my_body.docx": ("lmb-sop-10", "СОП клиники"),
    "СОП-09_Проведение_лимфотропной_терапии_Love_my_body.docx": ("lmb-sop-09", "СОП клиники"),
    "Взлом_системы_старения_лекция_40_минут.docx": ("lmb-aging-lecture", "Учебная лекция (внутренний материал)"),
    "López-Otín C. et al. Hallmarks of aging: An expanding universe. Cell. 2023;186:243–278.": ("lopez-otin-2023", "Научная публикация"),
}
LINK_IDS = {
    "https://www.who.int/initiatives/medication-without-harm/medication-safety-in-high-risk-situations": ("who-medication-safety", "Материал ВОЗ"),
    "https://doi.org/10.1016/j.cell.2022.11.001": ("lopez-otin-2023", "Научная публикация"),
    "https://www.who.int/news-room/fact-sheets/detail/ageing-and-health": ("who-ageing-health", "Материал ВОЗ"),
}
# Покрытие по описанию исходного состояния в ТЗ (раздел 2); требует подтверждения редактором.
COVERAGE = {"mito": ["concept"], "infusion": ["safety"], "peptide": ["safety"], "ozone": ["safety"], "lymph": ["safety"], "aging": ["concept"]}

# Дополнительные темы озонотерапии (ТЗ, раздел 3). Программы взяты из формулировок черновика ozone-intro v0.1.0.
OZONE_TOPICS = [
    ("ozone-iv-solution", "Внутривенный озонированный раствор", [], "Сейчас метод описан во вводной теме по СОП-10."),
    ("ozone-bagot", "Большая аутогемотерапия с озоном (БАГОТ)", [], "Сейчас метод описан во вводной теме по СОП-10."),
    ("ozone-rectal", "Ректальные инсуффляции",
     ["Клинические задачи", "Отбор пациента", "Противопоказания", "Оборудование и одноразовые принадлежности", "Параметры", "Наблюдение"],
     "Нужны отдельные учебные материалы; СОП-10 не распространяется на этот способ."),
    ("ozone-vaginal", "Вагинальные инсуффляции",
     ["Гинекологическая оценка", "Показания и ограничения", "Методика", "Переносимость", "Контроль результата"],
     "Нужны профильные материалы клиники; параметры других методов не переносятся."),
]


def js_literal_to_json(src: str) -> str:
    """Преобразует JS-литерал прототипа (одинарные кавычки, ключи без кавычек) в JSON."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == "'":
            j = i + 1
            buf = []
            while src[j] != "'":
                if src[j] == "\\":
                    buf.append(src[j + 1]); j += 2; continue
                buf.append(src[j]); j += 1
            out.append(json.dumps("".join(buf), ensure_ascii=False))
            i = j + 1
        elif c.isalpha() or c == "_":
            m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", src[i:])
            word = m.group(0)
            rest = src[i + len(word):].lstrip()
            out.append(json.dumps(word) if rest.startswith(":") else word)
            i += len(word)
        else:
            out.append(c); i += 1
    return "".join(out)


def load_legacy():
    text = LEGACY.read_text(encoding="utf-8")
    body = text[text.index("["): text.rindex("]") + 1]
    return json.loads(js_literal_to_json(body))


def sections_to_md(sections):
    return "".join(f"## {title}\n\n{body}\n\n" for title, body in sections).rstrip("\n") + "\n"


def md_to_sections(md):
    parts = re.split(r"^## (.+)$", md.replace("\r\n", "\n"), flags=re.M)
    return [[parts[k].strip(), parts[k + 1].strip()] for k in range(1, len(parts), 2)]


def empty_admin():
    return {"version": "0.0.0", "editorialStatus": "draft", "contentKind": "outline", "coverage": [], "body": None,
            "updatedAt": None, "nextReviewAt": None, "goal": None, "takeaway": None, "scope": None,
            "program": [], "sources": [], "claims": [], "derivedFrom": None, "approval": None}


def migrate():
    legacy = load_legacy()
    modules, sources = [], {}
    for m in legacy:
        lesson_id = f"{m['id']}-intro"
        lessons = [lesson_id] + ([t[0] for t in OZONE_TOPICS] if m["id"] == "ozone" else [])
        modules.append({"id": m["id"], "n": m["n"], "title": m["title"], "category": m["category"], "icon": m["icon"],
                        "lead": m["lead"], "keywords": m["keywords"].split(), "lessons": lessons})
        var_sources = []
        for name, desc in m["sources"]:
            sid, kind = SOURCE_IDS[name]
            sources.setdefault(sid, {"id": sid, "title": name, "author": None, "year": None, "type": kind, "url": None})
            var_sources.append({"id": sid, "locator": None, "supports": desc})
        for label, url in m["links"]:
            sid, kind = LINK_IDS[url]
            entry = sources.setdefault(sid, {"id": sid, "title": label, "author": None, "year": None, "type": kind, "url": None})
            entry["url"] = url
            if not any(s["id"] == sid for s in var_sources):
                var_sources.append({"id": sid, "locator": None, "supports": None})
        if "lopez-otin-2023" in sources:
            sources["lopez-otin-2023"].update(author="López-Otín C. et al.", year=2023)
        is_summary = m["type"] == "summary"
        meta = {
            "schemaVersion": 1, "lessonId": lesson_id, "moduleId": m["id"], "title": m["title"], "order": 1,
            "keywords": [], "relatedLessonIds": [], "alsoInModules": [],
            "migratedFrom": {"prototypeCommit": "1bdedd4630433560cec01c17d287649d455775e2", "route": f"#module/{m['id']}"},
            "variants": {
                "doctors": {
                    "version": "0.1.0", "editorialStatus": "draft", "contentKind": "summary" if is_summary else "outline",
                    "coverage": COVERAGE.get(m["id"], []), "body": "doctors.md", "updatedAt": MIGRATION_DATE, "nextReviewAt": None,
                    "goal": m["lead"], "takeaway": m["takeaway"], "scope": m["scope"],
                    "program": [t for t, _ in m["sections"]], "sources": var_sources, "claims": [], "approval": None,
                },
                "admins": empty_admin(),
            },
        }
        write_lesson(lesson_id, meta, sections_to_md(m["sections"]))
    for order, (lid, title, program, note) in enumerate(OZONE_TOPICS, start=2):
        meta = {"schemaVersion": 1, "lessonId": lid, "moduleId": "ozone", "title": title, "order": order,
                "keywords": [], "relatedLessonIds": ["ozone-intro"], "alsoInModules": [],
                "variants": {"doctors": {**empty_admin(), "program": program, "programNote": note}, "admins": empty_admin()}}
        meta["variants"]["doctors"].pop("derivedFrom")
        write_lesson(lid, meta, None)
    write_json(ROOT / "content" / "modules.json", modules)
    write_json(ROOT / "content" / "sources" / "public.json", sorted(sources.values(), key=lambda s: s["id"]))
    print(f"Перенесено направлений: {len(modules)}; источников: {len(sources)}")


def write_lesson(lesson_id, meta, md):
    d = ROOT / "content" / "lessons" / lesson_id
    if (d / "metadata.json").exists():
        print(f"Пропуск {lesson_id}: тема уже существует"); return
    d.mkdir(parents=True, exist_ok=True)
    write_json(d / "metadata.json", meta)
    if md is not None:
        write_text(d / "doctors.md", md)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def verify():
    """A02: каждый блок каждого из 14 разделов прототипа присутствует дословно и не отмечен утверждённым."""
    problems = 0
    for m in load_legacy():
        d = ROOT / "content" / "lessons" / f"{m['id']}-intro"
        meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
        doc = meta["variants"]["doctors"]
        got = md_to_sections((d / "doctors.md").read_text(encoding="utf-8"))
        checks = [
            (got == m["sections"], "текст разделов"),
            (doc["takeaway"] == m["takeaway"], "ключевая мысль"),
            (doc["goal"] == m["lead"], "краткая цель"),
            (doc["editorialStatus"] != "approved" and doc["approval"] is None, "нет утверждения"),
            (doc["contentKind"] == ("summary" if m["type"] == "summary" else "outline"), "вид материала"),
        ]
        for ok, what in checks:
            if not ok:
                problems += 1; print(f"РАСХОЖДЕНИЕ {m['id']}: {what}")
    print("Сверка с прототипом: " + ("всё совпадает" if not problems else f"расхождений {problems}"))
    return problems == 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    if not args.verify:
        migrate()
    sys.exit(0 if verify() else 1)
