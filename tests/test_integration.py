"""需要已安装应用依赖；模型与OCR使用替身，所有数据库写入临时目录。"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

try:
    import pymupdf
    from streamlit.testing.v1 import AppTest
    from learning_assistant import materials, ui, storage
    HAS_DEPENDENCIES = True
except ImportError:
    HAS_DEPENDENCIES = False


@unittest.skipUnless(HAS_DEPENDENCIES, "请先安装requirements.txt，再执行PDF与页面集成测试")
class IntegrationTests(unittest.TestCase):
    def make_pdf(self):
        with pymupdf.open() as doc:
            page = doc.new_page()
            page.insert_text((50, 50), "Python list append adds one element to the list.")
            return doc.tobytes()

    def test_pdf_text_and_document_identity(self):
        data = self.make_pdf()
        pages = materials.extract_pdf_pages("a.pdf", data)
        self.assertEqual(pages[0]["page_number"], 1)
        self.assertEqual(pages[0]["extraction_method"], "普通提取")
        self.assertIn("append", pages[0]["text"])
        self.assertEqual(len(pages[0]["document_id"]), 64)

    def test_forced_ocr_branch(self):
        with patch.object(materials, "ocr_pdf_page", return_value="扫描页识别结果"):
            pages = materials.extract_pdf_pages("a.pdf", self.make_pdf(), force_ocr=True)
        self.assertEqual(pages[0]["extraction_method"], "OCR")

    def test_ocr_error_closes_document(self):
        document = pymupdf.open(stream=self.make_pdf(), filetype="pdf")
        with patch.object(materials.pymupdf, "open", return_value=document), patch.object(materials, "ocr_pdf_page", side_effect=RuntimeError("OCR failed")):
            with self.assertRaises(RuntimeError):
                materials.extract_pdf_pages("a.pdf", self.make_pdf_bytes, True)
        self.assertTrue(document.is_closed)

    @property
    def make_pdf_bytes(self):
        # 使用pypdf生成空白页，不受上面对pymupdf.open的替换影响。
        from io import BytesIO
        from pypdf import PdfWriter
        buffer = BytesIO(); writer = PdfWriter(); writer.add_blank_page(width=100, height=100); writer.write(buffer)
        return buffer.getvalue()

    def test_duplicate_file_names_rejected(self):
        f = SimpleNamespace(name="a.pdf", getvalue=self.make_pdf)
        pages, errors = materials.parse_uploaded_files([f, f], False)
        self.assertEqual(pages, []); self.assertTrue(errors)

    def test_pdf_limits(self):
        with patch.object(materials, "MAX_PDF_BYTES", 1):
            with self.assertRaises(ValueError):
                materials.extract_pdf_pages("a.pdf", b"long")

    def test_ui_quiz_change_answer_and_file(self):
        with tempfile.TemporaryDirectory() as folder:
            files = [SimpleNamespace(name=name, getvalue=lambda: b"PDF") for name in ["A.pdf", "B.pdf"]]
            pages = [dict(file_name=name, document_id=name, page_number=1, text="Python list", extraction_method="普通提取") for name in ["A.pdf", "B.pdf"]]
            questions = [dict(id=1, type="简答题", question="解释列表", answer="列表可变", options=[], explanation="可以修改", source_pages=[1])]
            grades = [dict(id=1, score=5, error_type="完全正确", feedback="正确", suggestion="继续练习")]
            with patch.object(storage, "DATABASE_PATH", Path(folder) / "test.db"), \
                 patch.object(ui.st, "file_uploader", return_value=files), \
                 patch.object(ui, "parse_uploaded_files", return_value=(pages, [])), \
                 patch.object(ui, "generate_course_quiz", return_value=questions), \
                 patch.object(ui, "grade_short_answers", return_value=grades):
                app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
                app.run()
                def click(label):
                    next(b for b in app.button if b.label == label).click().run()
                    self.assertEqual(len(app.exception), 0)
                self.assertEqual(len(app.exception), 0)
                click("根据资料生成练习题")
                app.text_area(key="quiz_1_1").set_value("旧答案")
                click("提交答案")
                click("使用 AI 批改简答题")
                app.selectbox(key="quiz_file").select("B.pdf").run()
                click("保存本次练习记录")
                self.assertEqual(storage.load_quiz_attempts()[0]["file_name"], "A.pdf")
                app.text_area(key="quiz_1_1").set_value("新答案")
                click("提交答案")
                self.assertNotIn("short_answer_grades", app.session_state)
                self.assertFalse(any(b.label == "保存本次练习记录" for b in app.button))
                click("使用 AI 批改简答题")
                click("保存本次练习记录")
                self.assertEqual(len(storage.load_quiz_attempts()), 2)


if __name__ == "__main__":
    unittest.main()
