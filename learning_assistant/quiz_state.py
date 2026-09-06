"""试卷、提交快照、批改结果按生命周期绑定。"""
import hashlib
from uuid import uuid4


def upload_signature(files, force_ocr: bool):
    return tuple((f.name, hashlib.sha256(f.getvalue()).hexdigest()) for f in files) + (("force_ocr", force_ocr),)


def reset_material_state(state):
    for key in list(state):
        if key.startswith("quiz_") or key in {
            "course_pages", "course_chunks", "parse_errors", "file_signature",
            "search_results", "search_question", "ai_answer", "qa_history",
            "course_summary", "summary_signature", "submitted_answers",
            "short_answer_grades", "saved_quiz_version", "attempt_key",
        }:
            del state[key]


def start_quiz(state, file_name, pages):
    state["quiz_source"] = {
        "file_name": file_name,
        "document_id": pages[0].get("document_id", file_name),
        "source_pages": [page["page_number"] for page in pages],
    }
    state.pop("submitted_answers", None)
    state.pop("attempt_key", None)


def submit_quiz(state, questions, version):
    answers = {q["id"]: state.get(f'quiz_{version}_{q["id"]}', "") or "" for q in questions}
    # 重复点击同一提交不改变身份；修改答案必须重新批改、作为新尝试保存。
    if answers != state.get("submitted_answers"):
        state["submitted_answers"] = answers
        state.pop("short_answer_grades", None)
        state.pop("saved_quiz_version", None)
        state["attempt_key"] = uuid4().hex
    state["quiz_submitted"] = True
