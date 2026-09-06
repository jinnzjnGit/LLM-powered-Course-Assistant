import json
from .llm import configured_model, check_context, load_prompt
from .validation import validate_questions, validate_grades, validate_citations


def answer_with_course_materials(question: str, results: list[dict], history: list[dict] | None = None) -> str:
    """只根据检索片段生成答案，并要求模型使用可核验的资料编号。"""
    client, model = configured_model()

    if not results:
        raise ValueError("没有可用检索资料，请先检索。")
    context_parts = []
    for index, result in enumerate(results, start=1):
        context_parts.append(
            f'[资料{index}] 文件：{result["file_name"]}；'
            f'页码：第 {result["page_number"]} 页\n{result["text"]}'
        )
    context = "\n\n".join(context_parts)
    check_context(context + json.dumps((history or [])[-6:], ensure_ascii=False) + question)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    load_prompt("answer_with_course_materials.txt")
                ),
            },
            *(history or [])[-6:],
            {
                "role": "user",
                "content": f"课程资料片段：\n{context}\n\n学生问题：{question}",
            },
        ],
        temperature=0.2,
    )
    answer = response.choices[0].message.content or ""
    validate_citations(answer, len(results))
    return answer

def summarize_course_pages(
    file_name: str, pages: list[dict], summary_style: str
) -> str:
    """根据用户选择的课程页生成带页码依据的结构化总结。"""
    client, model = configured_model()

    source = "\n\n".join(
        f'【第{page["page_number"]}页】\n{page["text"]}'
        for page in pages
        if page["text"]
    )
    if not source:
        raise ValueError("所选页码没有可读取文字。")
    check_context(source)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    load_prompt("summarize_course_pages.txt")
                ),
            },
            {
                "role": "user",
                "content": (
                    f"资料文件：{file_name}\n"
                    f"总结风格：{summary_style}\n\n"
                    "请按以下结构总结：\n"
                    "1. 本节学习目标\n"
                    "2. 核心概念与知识结构\n"
                    "3. 关键语法和 Python 示例\n"
                    "4. 初学者易错点\n"
                    "5. 五条考前速记\n\n"
                    f"课程资料：\n{source}"
                ),
            },
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content or "模型没有返回总结。"

def generate_course_quiz(
    file_name: str,
    pages: list[dict],
    question_count: int,
    question_types: list[str],
    difficulty: str,
) -> list[dict]:
    """根据指定资料生成结构化练习题。"""
    client, model = configured_model()

    source = "\n\n".join(
        f'【第{page["page_number"]}页】\n{page["text"]}'
        for page in pages
        if page["text"]
    )
    if not source:
        raise ValueError("所选页码没有可读取文字。")
    check_context(source)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    load_prompt("generate_course_quiz.txt")
                ),
            },
            {
                "role": "user",
                "content": (
                    f"资料文件：{file_name}\n题目数量：{question_count}\n"
                    f"题型：{', '.join(question_types)}\n难度：{difficulty}\n\n"
                    "返回格式：\n"
                    '{"questions":[{'
                    '"id":1,"type":"单选题/判断题/简答题",'
                    '"question":"题目文字","options":["A. ...","B. ..."],'
                    '"answer":"单选题填字母，判断题填正确或错误，简答题填参考答案",'
                    '"explanation":"解析","source_pages":[1,2]'
                    "}]}\n"
                    "单选题必须有四个选项；判断题 options 必须是[\"正确\",\"错误\"]；"
                    "简答题 options 必须是空数组。source_pages 只能填写资料中真实存在的页码。\n\n"
                    f"课程资料：\n{source}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    raw_content = response.choices[0].message.content or "{}"
    return validate_questions(json.loads(raw_content), question_count,
                              question_types, {page["page_number"] for page in pages})


def grade_short_answers(answer_items: list[dict]) -> list[dict]:
    """使用课程参考答案批改简答题，并返回结构化诊断。"""
    client, model = configured_model()

    check_context(json.dumps(answer_items, ensure_ascii=False))
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    load_prompt("grade_short_answers.txt")
                ),
            },
            {
                "role": "user",
                "content": (
                    "请批改以下答案。返回格式："
                    '{"grades":[{"id":1,"score":0,"error_type":"概念不清",'
                    '"feedback":"具体反馈","suggestion":"复习建议"}]}\n\n'
                    + json.dumps(answer_items, ensure_ascii=False)
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    raw_content = response.choices[0].message.content or "{}"
    return validate_grades(json.loads(raw_content), {item["id"] for item in answer_items})


def generate_study_plan(
    attempts: list[dict], plan_days: int, daily_minutes: int
) -> str:
    """根据历史错题和错误类型生成个性化复习计划。"""
    client, model = configured_model()

    learning_history = []
    for attempt in attempts[:20]:
        details = json.loads(attempt["details_json"])
        wrong_items = []
        for detail in details:
            if detail.get("is_correct", False):
                continue
            wrong_items.append(
                {
                    "type": detail["type"],
                    "question": detail["question"],
                    "error_type": detail.get("error_type", "未知"),
                    "suggestion": detail.get("suggestion", ""),
                    "source_pages": detail.get("source_pages", []),
                }
            )
        learning_history.append(
            {
                "time": attempt["created_at"],
                "file_name": attempt["file_name"],
                "objective_score": (
                    f'{attempt["objective_correct"]}/{attempt["objective_total"]}'
                ),
                "short_score": f'{attempt["short_score"]}/{attempt["short_total"]}',
                "wrong_items": wrong_items,
            }
        )

    check_context(json.dumps(learning_history, ensure_ascii=False))
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    load_prompt("generate_study_plan.txt")
                ),
            },
            {
                "role": "user",
                "content": (
                    f"计划天数：{plan_days}天\n每天时间：{daily_minutes}分钟\n\n"
                    "请输出 Markdown，包含：\n"
                    "1. 学情诊断（优势、薄弱点、错误类型统计）\n"
                    "2. 每日复习安排（每天分钟数合计不得超过可用时间）\n"
                    "3. 每天的练习任务与检验标准\n"
                    "4. 第1、3、7天等间隔复习节点（按计划天数调整）\n"
                    "5. 计划结束时的自测建议\n\n"
                    "历史学习记录：\n"
                    + json.dumps(learning_history, ensure_ascii=False)
                ),
            },
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content or "模型没有返回学习计划。"
