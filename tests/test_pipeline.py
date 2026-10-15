"""Проверки конвейера по критериям приёмки ТЗ (раздел 14).

Запуск из корня проекта:  python -m unittest discover -s tests -v

Каждый тест работает на временной копии проекта; рабочий content/ не изменяется.
Рецензент «TEST-REVIEWER» — техническая фикстура; в рабочем контенте такая запись блокируется.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("lmb", ROOT / "scripts" / "lmb.py")
lmb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lmb)

REVIEWER = "TEST-REVIEWER (техническая фикстура)"


class Base(unittest.TestCase):
    def setUp(self):
        os.environ["LMB_TEST_FIXTURES"] = "1"
        self.tmp = Path(tempfile.mkdtemp(prefix="lmb-test-"))
        for d in ("content", "site", "templates"):
            shutil.copytree(ROOT / d, self.tmp / d, ignore=shutil.ignore_patterns("history"))
        (self.tmp / "private" / "inbox").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("LMB_TEST_FIXTURES", None)

    def project(self):
        return lmb.Project(self.tmp)

    def run_cli(self, *args):
        return lmb.main(["--root", str(self.tmp), *args])

    def meta_path(self, lid):
        return self.tmp / "content" / "lessons" / lid / "metadata.json"

    def edit_meta(self, lid, fn):
        p = self.meta_path(lid)
        meta = json.loads(p.read_text(encoding="utf-8"))
        fn(meta)
        lmb.write_json(p, meta)

    def build(self, mode="production"):
        report, out = lmb.build(self.project(), mode)
        return report, out

    def dist_text(self, out):
        return "\n".join(p.read_text(encoding="utf-8") for p in Path(out).rglob("*") if p.is_file())

    def approve(self, lid, variant="doctors"):
        self.assertEqual(self.run_cli("approve", lid, variant, "--reviewer", REVIEWER, "--date", "2026-10-14"), 0)


class Catalog(Base):
    def test_a01_ids_and_order(self):
        ids = [m["id"] for m in json.loads((ROOT / "content" / "modules.json").read_text(encoding="utf-8"))]
        self.assertEqual(ids[:14], lmb.CANONICAL_MODULE_IDS)
        self.assertEqual(lmb.check_project(lmb.Project(ROOT)).errors, [])

    def test_a01_missing_module_detected(self):
        p = self.tmp / "content" / "modules.json"
        mods = json.loads(p.read_text(encoding="utf-8"))
        lmb.write_json(p, [m for m in mods if m["id"] != "pellets"])
        self.assertTrue(any("pellets" in e for e in lmb.check_project(self.project()).errors))

    def test_a02_legacy_texts_intact_and_not_approved(self):
        r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "migrate_legacy.py"), "--verify"], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stdout.decode("utf-8", "replace"))
        for lid, meta in lmb.Project(ROOT).lessons.items():
            for v in meta["variants"].values():
                self.assertNotEqual(v.get("editorialStatus"), "approved", lid)

    def test_steroid_saliva_required_and_grouped(self):
        mods = {m["id"]: m for m in lmb.Project(ROOT).modules}
        m = mods["steroid-saliva"]
        self.assertEqual((m["category"], m["displayOrder"], m["icon"]), ("Диагностика", 3, "saliva-tube"))
        meta = lmb.Project(ROOT).lessons["steroid-saliva-intro"]["variants"]
        self.assertEqual((meta["doctors"]["contentKind"], meta["doctors"]["editorialStatus"], meta["doctors"]["approval"]), ("outline", "draft", None))
        self.assertIsNone(meta["admins"]["body"])
        counts = {}
        for x in mods.values():
            counts[x["category"]] = counts.get(x["category"], 0) + 1
        self.assertEqual(counts, {"Диагностика": 6, "Вмешательства": 6, "Основы и клинические направления": 3})
        p = self.tmp / "content" / "modules.json"
        lmb.write_json(p, [x for x in json.loads(p.read_text(encoding="utf-8")) if x["id"] != "steroid-saliva"])
        self.assertTrue(any("steroid-saliva" in e for e in lmb.check_project(self.project()).errors))

    def test_group_and_display_order_validated(self):
        p = self.tmp / "content" / "modules.json"
        mods = json.loads(p.read_text(encoding="utf-8"))
        mods[0]["category"] = "Терапия"
        mods[1]["displayOrder"] = mods[2]["displayOrder"] if mods[1]["category"] == mods[2]["category"] else mods[1]["displayOrder"]
        lmb.write_json(p, mods)
        errors = lmb.check_project(self.project()).errors
        self.assertTrue(any("category" in e for e in errors))

    def test_a11_next_module_needs_no_counters(self):
        p = self.tmp / "content" / "modules.json"
        mods = json.loads(p.read_text(encoding="utf-8"))
        before = len(mods)
        next_n = f"{max(int(m['n']) for m in mods) + 1:02d}"
        next_order = max(m["displayOrder"] for m in mods if m["category"] == "Вмешательства") + 1
        mods.append({"id": "test-module", "n": next_n, "title": "Проверочное направление", "category": "Вмешательства",
                     "displayOrder": next_order, "icon": "doc-unknown", "lead": "Временная запись для проверки.", "keywords": [], "lessons": []})
        lmb.write_json(p, mods)
        self.assertEqual(self.run_cli("new-lesson", "test-module", "test-module-intro", "--title", "Проверочная тема"), 0)
        report, out = self.build("preview")
        self.assertEqual(report.errors, [])
        self.assertTrue(any("иконки" in w for w in report.warnings))
        data = lmb.read_data(out)
        self.assertEqual(len(data["modules"]), before + 1)
        self.assertEqual(len({m["n"] for m in data["modules"]}), before + 1)
        app = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        app = re.sub(r"const iconPaths = \{.*?\};", "", app, flags=re.S)  # координаты SVG не являются счётчиками
        self.assertNotRegex(app, r"\b1[4589]\b")

    def test_editorial_sections_hidden_from_learning_view(self):
        _, out = self.build("preview")
        data = lmb.read_data(out)
        mito = data["lessons"]["mito-intro"]["variants"]["doctors"]
        for part in (mito["html"], mito["text"], json.dumps(mito["toc"], ensure_ascii=False), " ".join(mito["program"])):
            self.assertNotIn("Что дополнить в полном врачебном саммари", part)
        self.assertIn("Типичные ошибки", mito["html"])
        genetics = data["lessons"]["genetics-intro"]["variants"]["doctors"]
        self.assertNotIn("Материалы для наполнения", " ".join(genetics["program"]))
        self.assertNotIn("Задача раздела", genetics["text"])
        md = (ROOT / "content" / "lessons" / "mito-intro" / "doctors.md").read_text(encoding="utf-8")
        self.assertIn("## Что дополнить в полном врачебном саммари", md)

    def test_unknown_editorial_section_detected(self):
        self.edit_meta("mito-intro", lambda m: m["variants"]["doctors"]["editorialSections"].append("Нет такого раздела"))
        self.assertTrue(any("Нет такого раздела" in e for e in lmb.check_project(self.project()).errors))


class Publication(Base):
    DRAFT_MARK = "Отсутствие осадка само по себе не доказывает химическую стабильность"

    def test_a06_drafts_not_in_production(self):
        report, out = self.build("production")
        self.assertEqual(report.errors, [])
        self.assertNotIn(self.DRAFT_MARK, self.dist_text(out))
        _, prev = self.build("preview")
        self.assertIn(self.DRAFT_MARK, self.dist_text(prev))

    def test_a07_private_files_not_published(self):
        canary = "КОНТРОЛЬНАЯ-СТРОКА-PRIVATE-7f3a"
        (self.tmp / "private" / "inbox" / "canary.txt").write_text(canary, encoding="utf-8")
        _, out = self.build("production")
        files = sorted(p.name for p in Path(out).rglob("*") if p.is_file())
        self.assertEqual(files, ["app.js", "data.js", "index.html", "styles.css"])
        self.assertNotIn(canary, self.dist_text(out))

    def test_a08_approved_published_and_tampering_blocks_build(self):
        self.approve("infusion-intro")
        report, out = self.build("production")
        self.assertEqual(report.errors, [])
        v = lmb.read_data(out)["lessons"]["infusion-intro"]["variants"]["doctors"]
        self.assertEqual(v["state"], "approved")
        self.assertIn(self.DRAFT_MARK, v["html"])
        md = self.tmp / "content" / "lessons" / "infusion-intro" / "doctors.md"
        md.write_text(md.read_text(encoding="utf-8").replace("осадка", "осадкa", 1), encoding="utf-8")  # одна буква латиницей
        report, out = self.build("production")
        self.assertIsNone(out)
        self.assertTrue(any("контрольная сумма" in e for e in report.errors))

    def test_a08_metadata_change_also_invalidates(self):
        self.approve("infusion-intro")
        self.edit_meta("infusion-intro", lambda m: m["variants"]["doctors"].update(takeaway="Изменённая ключевая мысль"))
        self.assertTrue(lmb.check_project(self.project()).errors)

    def test_previous_approved_version_stays_until_new_one_ready(self):
        self.approve("infusion-intro")
        approved_version = self.project().lessons["infusion-intro"]["variants"]["doctors"]["version"]
        md = self.tmp / "content" / "lessons" / "infusion-intro" / "doctors.md"
        md.write_text(md.read_text(encoding="utf-8") + "\n## Новый раздел\n\nТекст новой редакции.\n", encoding="utf-8")
        self.edit_meta("infusion-intro", lambda m: m["variants"]["doctors"].update(version="0.2.0", editorialStatus="in_review", approval=None))
        report, out = self.build("production")
        self.assertEqual(report.errors, [])
        v = lmb.read_data(out)["lessons"]["infusion-intro"]["variants"]["doctors"]
        self.assertEqual((v["state"], v["version"]), ("approved", approved_version))
        self.assertIn("ранее утверждённая", v["fallbackNote"])
        self.assertNotIn("Текст новой редакции", self.dist_text(out))

    def test_withdrawn_removes_material(self):
        self.approve("infusion-intro")
        self.edit_meta("infusion-intro", lambda m: m["variants"]["doctors"].update(withdrawn={"date": "2026-10-14", "note": "Снято по решению главного врача"}))
        _, out = self.build("production")
        self.assertEqual(lmb.read_data(out)["lessons"]["infusion-intro"]["variants"]["doctors"]["state"], "withdrawn")
        self.assertNotIn(self.DRAFT_MARK, self.dist_text(out))

    def test_test_reviewer_blocked_in_real_content(self):
        self.approve("infusion-intro")
        os.environ.pop("LMB_TEST_FIXTURES")
        self.assertTrue(any("фикстуры" in e for e in lmb.check_project(self.project()).errors))


class Variants(Base):
    def add_admin(self, lid="infusion-intro"):
        doc = lmb.Project(self.tmp)
        meta = doc.lessons[lid]
        checksum = meta["variants"]["doctors"]["approval"]["checksum"]
        (self.tmp / "content" / "lessons" / lid / "admins.md").write_text("## Что это за услуга\n\nПроверочный административный текст.\n", encoding="utf-8")
        self.edit_meta(lid, lambda m: m["variants"]["admins"].update(
            version="0.1.0", contentKind="summary", body="admins.md", updatedAt="2026-10-14",
            derivedFrom={"lessonId": lid, "variant": "doctors", "version": meta["variants"]["doctors"]["version"], "checksum": checksum}))

    def test_a03_independent_states(self):
        self.approve("infusion-intro")
        _, out = self.build("production")
        v = lmb.read_data(out)["lessons"]["infusion-intro"]["variants"]
        self.assertEqual((v["doctors"]["state"], v["admins"]["state"]), ("approved", "pending"))
        self.assertNotIn("html", v["admins"])

    def test_admin_requires_approved_doctors_base(self):
        (self.tmp / "content" / "lessons" / "mito-intro" / "admins.md").write_text("## Текст\n\nПроверка.\n", encoding="utf-8")
        self.edit_meta("mito-intro", lambda m: m["variants"]["admins"].update(version="0.1.0", contentKind="summary", body="admins.md",
                                                                             derivedFrom={"lessonId": "mito-intro", "version": "0.1.0", "checksum": "sha256:0"}))
        self.assertNotEqual(self.run_cli("approve", "mito-intro", "admins", "--reviewer", REVIEWER), 0)

    def test_a09_admin_flagged_when_doctors_changes(self):
        self.approve("infusion-intro")
        self.add_admin()
        self.approve("infusion-intro", "admins")
        self.assertEqual(lmb.admin_sync_state(self.project(), "infusion-intro"), "ok")
        md = self.tmp / "content" / "lessons" / "infusion-intro" / "doctors.md"
        md.write_text(md.read_text(encoding="utf-8").replace("Главные ошибки", "Типичные ошибки"), encoding="utf-8")
        self.edit_meta("infusion-intro", lambda m: m["variants"]["doctors"].update(version="0.2.0", editorialStatus="in_review", approval=None))
        p = self.project()
        self.assertEqual(lmb.admin_sync_state(p, "infusion-intro"), "needs_sync")
        self.assertTrue(any("требуется сверка" in w for w in lmb.check_project(p).warnings))
        _, out = self.build("production")
        adm = lmb.read_data(out)["lessons"]["infusion-intro"]["variants"]["admins"]
        self.assertEqual(adm["state"], "approved")
        self.assertTrue(adm["needsSync"])


class Validation(Base):
    def test_a10_unknown_source_detected(self):
        self.edit_meta("mito-intro", lambda m: m["variants"]["doctors"]["sources"].append({"id": "no-such-source"}))
        self.assertTrue(any("no-such-source" in e for e in lmb.check_project(self.project()).errors))

    def test_a10_missing_markdown_detected(self):
        (self.tmp / "content" / "lessons" / "mito-intro" / "doctors.md").unlink()
        self.assertTrue(any("не найден" in e for e in lmb.check_project(self.project()).errors))

    def test_a10_broken_internal_link_detected(self):
        md = self.tmp / "content" / "lessons" / "mito-intro" / "doctors.md"
        md.write_text(md.read_text(encoding="utf-8") + "\nСм. [тему](lesson:no-such-lesson).\n", encoding="utf-8")
        self.assertTrue(any("no-such-lesson" in e for e in lmb.check_project(self.project()).errors))

    def test_public_sources_cannot_hold_internal_fields(self):
        p = self.tmp / "content" / "sources" / "public.json"
        src = json.loads(p.read_text(encoding="utf-8"))
        src[0]["path"] = "private/originals/file.docx"
        lmb.write_json(p, src)
        self.assertTrue(any("недопустимые поля" in e for e in lmb.check_project(self.project()).errors))

    def test_a05_add_and_remove_lesson_via_files(self):
        self.assertEqual(self.run_cli("new-lesson", "infusion", "infusion-test-topic", "--title", "Проверочная тема"), 0)
        self.edit_meta("infusion-test-topic", lambda m: m["variants"]["doctors"].update(sources=[{"id": "lmb-sop-12", "locator": "раздел 1", "supports": "проверка"}]))
        report, out = self.build("preview")
        self.assertEqual(report.errors, [])
        data = lmb.read_data(out)
        self.assertIn("infusion-test-topic", data["modules"][1]["lessons"])
        self.assertEqual(data["lessons"]["infusion-test-topic"]["variants"]["doctors"]["state"], "draft")
        shutil.rmtree(self.tmp / "content" / "lessons" / "infusion-test-topic")
        p = self.tmp / "content" / "modules.json"
        mods = json.loads(p.read_text(encoding="utf-8"))
        mods[1]["lessons"].remove("infusion-test-topic")
        lmb.write_json(p, mods)
        self.assertEqual(lmb.check_project(self.project()).errors, [])

    def test_markdown_escapes_html(self):
        html, toc = lmb.render_markdown("## Раздел\n\n<script>alert(1)</script> **важно**\n\n| A | B |\n|---|---|\n| 1 | 2 |\n", lambda u: u)
        self.assertNotIn("<script>", html)
        self.assertIn("<strong>важно</strong>", html)
        self.assertIn("<table>", html)
        self.assertEqual(toc, [{"id": "section-1", "title": "Раздел"}])


if __name__ == "__main__":
    unittest.main()
