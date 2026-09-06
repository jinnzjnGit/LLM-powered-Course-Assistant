import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from learning_assistant.retrieval import split_text, build_course_chunks, search_course_chunks
from learning_assistant.validation import validate_questions, validate_grades, validate_citations
from learning_assistant.quiz_state import upload_signature, start_quiz, submit_quiz, reset_material_state
from learning_assistant import storage, model_service
from learning_assistant.llm import check_context, model_error_message


def question():
    return dict(type="单选题", question="哪个是列表？", options=["A. []", "B. ()", "C. {}", "D. 1"],
                answer="A", explanation="方括号表示列表。", source_pages=[1])


def grade(qid=1):
    return dict(id=qid, score=5, error_type="完全正确", feedback="答案正确", suggestion="继续练习")


class RetrievalTests(unittest.TestCase):
    def test_python_indentation_preserved(self):
        code = 'if True:\n    print(1)\n    if True:\n        print(2)'
        self.assertEqual(split_text(code), [code])
        compile(split_text(code)[0], "retrieved", "exec")

    def test_tabs_and_leading_spaces_preserved(self):
        self.assertEqual(split_text('    x\n\ty'), ['    x\n\ty'])

    def test_invalid_window(self):
        for size, overlap in [(0, 0), (5, 5), (5, -1)]:
            with self.assertRaises(ValueError):
                split_text("abc", size, overlap)

    def test_search_source_and_no_match(self):
        chunks = build_course_chunks([dict(file_name="a.pdf", document_id="hash", page_number=2,
                                          text="Python list append adds an element", extraction_method="普通提取")])
        result = search_course_chunks("append", chunks)
        self.assertEqual(result[0]["page_number"], 2)
        self.assertEqual(result[0]["document_id"], "hash")
        self.assertEqual(search_course_chunks("zzzzzz", chunks), [])

    def test_empty_inputs(self):
        self.assertEqual(split_text(""), [])
        self.assertEqual(search_course_chunks("", []), [])


class ValidationTests(unittest.TestCase):
    def test_valid_question(self):
        self.assertEqual(validate_questions({"questions": [question()]}, 1, ["单选题"], {1})[0]["id"], 1)

    def test_reject_bad_question_fields(self):
        for field, value in [("options", []), ("answer", "Z"), ("source_pages", [999]),
                             ("source_pages", []), ("type", "编程题"), ("question", None),
                             ("options", ["A. 同", "B. 同", "C. 不同", "D. 其他"])]:
            with self.subTest(field=field, value=value):
                q = question(); q[field] = value
                with self.assertRaises(ValueError):
                    validate_questions({"questions": [q]}, 1, ["单选题"], {1})

    def test_reject_partial_and_duplicate_quiz(self):
        for questions, count in [([question()], 3), ([question(), question()], 2)]:
            with self.assertRaises(ValueError):
                validate_questions({"questions": questions}, count, ["单选题"], {1})

    def test_other_question_types(self):
        q = question(); q.update(type="判断题", options=["正确", "错误"], answer="正确")
        validate_questions({"questions": [q]}, 1, ["判断题"], {1})
        q.update(type="简答题", options=[], answer="参考解答")
        validate_questions({"questions": [q]}, 1, ["简答题"], {1})

    def test_reject_bad_grade_batch(self):
        for batch in [[grade(), grade()], [grade()], [grade(), grade(3)], []]:
            with self.assertRaises(ValueError):
                validate_grades({"grades": batch}, {1, 2})

    def test_reject_score_coercion(self):
        for score in [6, -1, "5", 2.5, True]:
            g = grade(); g["score"] = score
            with self.assertRaises(ValueError):
                validate_grades({"grades": [g]}, {1})

    def test_grades_ordered(self):
        self.assertEqual([g["id"] for g in validate_grades({"grades": [grade(2), grade()]}, {1, 2})], [1, 2])

    def test_citations(self):
        validate_citations("列表可以修改[资料1]", 2)
        validate_citations("现有课程资料不足以回答这个问题", 2)
        for text in ["", "没有引用", "依据[资料3]", "依据[资料0]"]:
            with self.assertRaises(ValueError):
                validate_citations(text, 2)

    def test_context_budget(self):
        with self.assertRaises(ValueError):
            check_context("x" * 30001)

    def test_remote_error_not_leaked(self):
        self.assertNotIn("secret", model_error_message(RuntimeError("secret")))


class StateTests(unittest.TestCase):
    def test_same_name_same_length_changed_content(self):
        a = SimpleNamespace(name="a.pdf", getvalue=lambda: b"abc")
        b = SimpleNamespace(name="a.pdf", getvalue=lambda: b"xyz")
        self.assertNotEqual(upload_signature([a], False), upload_signature([b], False))

    def test_snapshot_regrade_and_idempotency(self):
        state = {"quiz_1_1": "旧答案"}
        submit_quiz(state, [{"id": 1}], 1)
        key = state["attempt_key"]
        state["short_answer_grades"] = [grade()]
        submit_quiz(state, [{"id": 1}], 1)
        self.assertEqual(key, state["attempt_key"])
        state["quiz_1_1"] = "新答案"
        self.assertEqual(state["submitted_answers"][1], "旧答案")
        submit_quiz(state, [{"id": 1}], 1)
        self.assertNotEqual(key, state["attempt_key"])
        self.assertNotIn("short_answer_grades", state)

    def test_source_bound_to_quiz(self):
        state = {}
        start_quiz(state, "A.pdf", [{"document_id": "abc", "page_number": 1}])
        state["quiz_file"] = "B.pdf"
        self.assertEqual(state["quiz_source"]["file_name"], "A.pdf")

    def test_material_reset_clears_answers_and_chat(self):
        state = dict(quiz_1_1="old", quiz_version=1, qa_history=[1], attempt_key="old", other="keep")
        reset_material_state(state)
        self.assertEqual(state, {"other": "keep"})


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "learning.db"
        self.patcher = patch.object(storage, "DATABASE_PATH", self.path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop(); self.temp.cleanup()

    def test_migrate_old_records_without_loss(self):
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE quiz_attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, file_name TEXT NOT NULL, objective_correct INTEGER NOT NULL, objective_total INTEGER NOT NULL, short_score INTEGER NOT NULL, short_total INTEGER NOT NULL, details_json TEXT NOT NULL)")
            db.execute("INSERT INTO quiz_attempts VALUES (1,'old','old.pdf',1,1,0,0,'[]')")
        db.close()
        storage.initialize_database(); storage.initialize_database()
        self.assertEqual(storage.load_quiz_attempts()[0]["file_name"], "old.pdf")
        self.assertEqual(len(list(self.path.parent.glob("backups/*.db"))), 1)

    def test_duplicate_save_and_new_attempt(self):
        storage.initialize_database()
        first = storage.save_quiz_attempt("A.pdf", 1, 1, 0, 0, [], attempt_key="one")
        self.assertEqual(first, storage.save_quiz_attempt("A.pdf", 1, 1, 0, 0, [], attempt_key="one"))
        storage.save_quiz_attempt("A.pdf", 1, 1, 0, 0, [], attempt_key="two")
        self.assertEqual(len(storage.load_quiz_attempts()), 2)

    def test_plan_round_trip(self):
        storage.initialize_database()
        self.assertIsNone(storage.load_latest_study_plan())
        storage.save_study_plan(7, 30, "计划")
        self.assertEqual(storage.load_latest_study_plan()["content"], "计划")


class ModelContractTests(unittest.TestCase):
    def client(self, payload):
        self.calls = []
        def create(**kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload))])
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    def test_history_bounded_and_current_sources(self):
        with patch.object(model_service, "configured_model", return_value=(self.client("答案[资料1]"), "fake")):
            result = model_service.answer_with_course_materials("问题", [dict(file_name="a.pdf", page_number=1, text="资料")],
                [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i)} for i in range(10)])
        self.assertEqual(result, "答案[资料1]")
        self.assertEqual(len(self.calls[0]["messages"]), 8)
        self.assertIn("资料片段", self.calls[0]["messages"][-1]["content"])

    def test_partial_grading_rejected_at_model_boundary(self):
        with patch.object(model_service, "configured_model", return_value=(self.client(json.dumps({"grades": [grade()]})), "fake")):
            with self.assertRaises(ValueError):
                model_service.grade_short_answers([{"id": 1}, {"id": 2}])

    def test_bad_json_rejected(self):
        with patch.object(model_service, "configured_model", return_value=(self.client("not JSON"), "fake")):
            with self.assertRaises(ValueError):
                model_service.generate_course_quiz("a.pdf", [{"page_number": 1, "text": "abc"}], 1, ["单选题"], "基础")


if __name__ == "__main__":
    unittest.main()
