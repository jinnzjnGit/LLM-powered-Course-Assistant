"""模型输出按整批校验：有错误则拒绝，避免静默漏题或错误计分。"""
import re

QUESTION_TYPES = {"单选题", "判断题", "简答题"}
ERROR_TYPES = {"完全正确", "概念不清", "记忆混淆", "代码或语法错误", "表达不完整", "未作答"}


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}必须为非空文本。")
    return value.strip()


def validate_questions(data, count: int, requested_types: list[str], allowed_pages: set[int]) -> list[dict]:
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        raise ValueError("模型必须返回questions数组。")
    questions = data["questions"]
    if len(questions) != count:
        raise ValueError(f"需要{count}道题，实际返回{len(questions)}道，请重新生成。")
    normalized = []
    seen = set()
    for index, item in enumerate(questions, 1):
        if not isinstance(item, dict):
            raise ValueError("每道题必须为对象。")
        kind = item.get("type")
        if not isinstance(kind, str) or kind not in QUESTION_TYPES or kind not in requested_types:
            raise ValueError("返回了未选择或不支持的题型。")
        question = _text(item.get("question"), "题干")
        if question in seen:
            raise ValueError("出现重复题干，请重新生成。")
        seen.add(question)
        answer = _text(item.get("answer"), "参考答案")
        explanation = _text(item.get("explanation"), "解析")
        pages = item.get("source_pages")
        if not isinstance(pages, list) or not pages or any(type(p) is not int or p not in allowed_pages for p in pages):
            raise ValueError("题目必须引用本次资料中的真实页码。")
        options = item.get("options")
        if not isinstance(options, list):
            raise ValueError("options必须为数组。")
        if kind == "单选题":
            if len(options) != 4 or any(not isinstance(o, str) or not o.strip() for o in options):
                raise ValueError("单选题必须有四个非空选项。")
            bodies = []
            for letter, option in zip("ABCD", options):
                match = re.fullmatch(r"([A-Da-d])[.、．:：)）]\s*(.+)", option.strip(), re.DOTALL)
                if not match or match[1].upper() != letter:
                    raise ValueError("单选题选项必须依次以A.、B.、C.、D.开头。")
                bodies.append(match[2].strip())
            if len(set(bodies)) != 4:
                raise ValueError("单选题选项不能重复。")
            answer = answer.upper()
            if answer not in {"A", "B", "C", "D"}:
                raise ValueError("单选题答案必须是A、B、C或D。")
            options = [f"{letter}. {body}" for letter, body in zip("ABCD", bodies)]
        elif kind == "判断题":
            if options != ["正确", "错误"] or answer not in options:
                raise ValueError("判断题选项和答案必须使用正确/错误。")
        elif options:
            raise ValueError("简答题options必须为空数组。")
        normalized.append(dict(id=index, type=kind, question=question, answer=answer,
                               options=options, explanation=explanation, source_pages=sorted(set(pages))))
    return normalized


def validate_grades(data, expected_ids: set[int]) -> list[dict]:
    if not isinstance(data, dict) or not isinstance(data.get("grades"), list):
        raise ValueError("模型必须返回grades数组。")
    result = {}
    for grade in data["grades"]:
        if not isinstance(grade, dict):
            raise ValueError("每项评分必须为对象。")
        qid = grade.get("id")
        if type(qid) is not int or qid not in expected_ids or qid in result:
            raise ValueError("批改结果包含重复或未知题号。")
        score = grade.get("score")
        if type(score) is not int or not 0 <= score <= 5:
            raise ValueError("分数必须为0到5的整数。")
        error = grade.get("error_type")
        if not isinstance(error, str) or error not in ERROR_TYPES:
            raise ValueError("错误类型不合法。")
        result[qid] = dict(id=qid, score=score, error_type=error,
                           feedback=_text(grade.get("feedback"), "批改反馈"),
                           suggestion=_text(grade.get("suggestion"), "复习建议"))
    if set(result) != expected_ids or not result:
        raise ValueError("批改未覆盖全部简答题，请重新批改。")
    return [result[qid] for qid in sorted(result)]


def validate_citations(answer: str, source_count: int) -> None:
    if not answer.strip():
        raise ValueError("模型没有返回答案。")
    citations = [int(x) for x in re.findall(r"\[资料(\d+)\]", answer)]
    if any(x < 1 or x > source_count for x in citations):
        raise ValueError("回答引用了不存在的资料编号，请重新生成。")
    if not citations and "现有课程资料不足以回答" not in answer:
        raise ValueError("回答缺少资料引用，请重新生成。")
