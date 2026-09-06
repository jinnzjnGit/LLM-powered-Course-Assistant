import json
from collections import Counter
import streamlit as st
from .materials import parse_uploaded_files
from .retrieval import build_course_chunks, search_course_chunks
from .model_service import (answer_with_course_materials, summarize_course_pages, generate_course_quiz, grade_short_answers, generate_study_plan)
from .storage import (initialize_database, save_quiz_attempt, load_quiz_attempts, save_study_plan, load_latest_study_plan)
from .llm import model_error_message
from .quiz_state import upload_signature, reset_material_state, start_quiz, submit_quiz

def main():
    st.set_page_config(
        page_title="Python 编程基础学习助手",
        page_icon="🐍",
        layout="wide",
    )

    initialize_database()

    st.title("🐍 Python 编程基础学习助手")
    st.caption("本地个人/小组练习版：本实例共用学习记录，AI评分仅供练习参考。")
    st.caption("基于你的课程资料进行答疑、总结、出题和复习")

    with st.sidebar:
        st.header("课程资料")
        uploaded_files = st.file_uploader(
            "上传 PDF 课程资料",
            type=["pdf"],
            accept_multiple_files=True,
        )
        force_ocr = st.checkbox(
            "所有页面强制使用 OCR",
            help="普通模式会自动识别空白页和明显乱码页。若仍有乱码，再开启此选项。",
        )
        if uploaded_files:
            file_signature = upload_signature(uploaded_files, force_ocr)
            if st.session_state.get("file_signature") != file_signature:
                with st.spinner("正在逐页解析；扫描页执行 OCR 时会稍慢……"):
                    reset_material_state(st.session_state)
                    pages, errors = parse_uploaded_files(uploaded_files, force_ocr)
                    st.session_state["course_pages"] = pages
                    st.session_state["course_chunks"] = build_course_chunks(pages)
                    st.session_state["parse_errors"] = errors
                    st.session_state["file_signature"] = file_signature
                    st.session_state.pop("search_results", None)
                    st.session_state.pop("ai_answer", None)
                    st.session_state.pop("course_summary", None)
                    st.session_state.pop("summary_signature", None)
                    st.session_state.pop("quiz_questions", None)
                    st.session_state.pop("quiz_submitted", None)
                    st.session_state.pop("short_answer_grades", None)

            course_pages = st.session_state.get("course_pages", [])
            if course_pages and "course_chunks" not in st.session_state:
                st.session_state["course_chunks"] = build_course_chunks(course_pages)
            parse_errors = st.session_state.get("parse_errors", [])
            readable_pages = sum(bool(page["text"]) for page in course_pages)
            ocr_pages = sum(page["extraction_method"] == "OCR" for page in course_pages)
            total_characters = sum(len(page["text"]) for page in course_pages)
            course_chunks = st.session_state.get("course_chunks", [])

            st.info(f"已选择 {len(uploaded_files)} 个文件；成功读取 {len({p['file_name'] for p in course_pages})} 个")
            col_pages, col_chars = st.columns(2)
            col_pages.metric("可读取页数", f"{readable_pages}/{len(course_pages)}")
            col_chars.metric("文本字符", f"{total_characters:,}")
            st.caption(f"其中 {ocr_pages} 页使用了 OCR")
            st.caption(f"已生成 {len(course_chunks)} 个可检索资料片段")

            for error in parse_errors:
                st.error(error)

            if course_pages and readable_pages == 0:
                st.warning("未提取到可读文字，请检查扫描清晰度或尝试强制OCR。")
        else:
            reset_material_state(st.session_state)
            st.session_state.pop("course_pages", None)
            st.session_state.pop("course_chunks", None)
            st.session_state.pop("parse_errors", None)
            st.session_state.pop("file_signature", None)
            st.session_state.pop("search_results", None)
            st.session_state.pop("ai_answer", None)
            st.session_state.pop("course_summary", None)
            st.session_state.pop("summary_signature", None)
            st.session_state.pop("quiz_questions", None)
            st.session_state.pop("quiz_submitted", None)
            st.session_state.pop("short_answer_grades", None)

    tab_qa, tab_summary, tab_quiz, tab_records, tab_plan = st.tabs(
        ["资料答疑", "章节总结", "练习测验", "学习记录", "复习计划"]
    )

    with tab_qa:
        render_qa(uploaded_files)

    with tab_summary:
        render_summary()

    with tab_quiz:
        render_quiz()

    with tab_records:
        render_records()

    with tab_plan:
        render_plan()


def render_qa(uploaded_files):
    st.subheader("向课程资料提问")
    if st.button("清空对话上下文"):
        st.session_state.pop("qa_history", None)
        st.session_state.pop("ai_answer", None)
    st.caption("保留最近3轮对话；追问检索时请保留知识点关键词。")
    question = st.text_area(
        "你的问题",
        placeholder="例如：Python 中列表和元组有什么区别？",
    )
    if st.button("检索相关资料", type="primary"):
        if not question.strip():
            st.warning("请先输入问题。")
        elif not uploaded_files:
            st.warning("请先在左侧上传课程资料。")
        else:
            st.session_state["search_results"] = search_course_chunks(
                question,
                st.session_state.get("course_chunks", []),
            )
            st.session_state["search_question"] = question
            st.session_state.pop("ai_answer", None)

    search_results = st.session_state.get("search_results", [])
    if search_results:
        st.subheader("最相关的课程资料")
        for rank, result in enumerate(search_results, start=1):
            with st.expander(
                f'{rank}. {result["file_name"]} · 第 {result["page_number"]} 页 '
                f'· 相关度 {result["score"]:.2f}',
                expanded=rank <= 2,
            ):
                st.write(result["text"])
                st.caption(
                    f'片段 {result["part_number"]} · {result["extraction_method"]}'
                )

        if st.button("让 DeepSeek 根据这些资料回答", type="primary"):
            with st.spinner("DeepSeek 正在阅读相关资料并组织答案……"):
                try:
                    st.session_state["ai_answer"] = answer_with_course_materials(
                        st.session_state.get("search_question", question),
                        search_results,
                        st.session_state.get("qa_history", []),
                    )
                    st.session_state["qa_history"] = (
                        st.session_state.get("qa_history", []) + [
                            {"role": "user", "content": st.session_state.get("search_question", question)},
                            {"role": "assistant", "content": st.session_state["ai_answer"]},
                        ]
                    )[-6:]
                except Exception as exc:
                    st.error(model_error_message(exc))

        if st.session_state.get("ai_answer"):
            st.subheader("课程助手回答")
            st.markdown(st.session_state["ai_answer"])
    elif "search_results" in st.session_state and question.strip():
        st.warning("没有找到相关片段，请换一种提问方式或检查 PDF 解析结果。")

    course_pages = st.session_state.get("course_pages", [])
    readable_pages = [page for page in course_pages if page["text"]]
    if readable_pages:
        with st.expander("检查解析结果（建议首次上传时查看）"):
            selected_page = st.selectbox(
                "选择页面",
                options=range(len(readable_pages)),
                format_func=lambda index: (
                    f'{readable_pages[index]["file_name"]} · '
                    f'第 {readable_pages[index]["page_number"]} 页 · '
                    f'{readable_pages[index]["extraction_method"]}'
                ),
            )
            preview = readable_pages[selected_page]
            st.text_area(
                "提取出的文字",
                value=preview["text"],
                height=260,
                disabled=True,
            )


def render_summary():
    st.subheader("章节总结助手")
    course_pages = st.session_state.get("course_pages", [])
    if not course_pages:
        st.info("请先在左侧上传课程 PDF。")
    else:
        available_files = list(dict.fromkeys(page["file_name"] for page in course_pages))
        summary_file = st.selectbox("选择资料", available_files, key="summary_file")
        file_pages = [
            page
            for page in course_pages
            if page["file_name"] == summary_file and page["text"]
        ]

        if not file_pages:
            st.warning("这份资料没有可读取的页面。")
        else:
            minimum_page = min(page["page_number"] for page in file_pages)
            maximum_page = max(page["page_number"] for page in file_pages)
            if minimum_page == maximum_page:
                page_range = (minimum_page, maximum_page)
                st.caption(f"当前资料只有第 {minimum_page} 页可读取")
            else:
                page_range = st.slider(
                    "选择页码范围",
                    minimum_page,
                    maximum_page,
                    (minimum_page, min(minimum_page + 9, maximum_page)),
                )

            summary_style = st.selectbox(
                "总结风格",
                ["详细学习版", "考前速记版", "教师授课提纲版"],
            )
            selected_pages = [
                page
                for page in file_pages
                if page_range[0] <= page["page_number"] <= page_range[1]
            ]
            selected_characters = sum(len(page["text"]) for page in selected_pages)
            st.caption(
                f"将总结 {len(selected_pages)} 页，共约 {selected_characters:,} 个字符"
            )

            if len(selected_pages) > 30:
                st.warning("一次总结超过 30 页可能较慢，建议按章节分批生成。")

            if st.button("生成章节总结", type="primary"):
                with st.spinner("总结助手 正在阅读所选课程内容……"):
                    try:
                        st.session_state["course_summary"] = summarize_course_pages(
                            summary_file, selected_pages, summary_style
                        )
                        st.session_state["summary_signature"] = (
                            summary_file,
                            page_range,
                            summary_style,
                        )
                    except Exception as exc:
                        st.error(model_error_message(exc))

            current_signature = (summary_file, page_range, summary_style)
            if (
                st.session_state.get("course_summary")
                and st.session_state.get("summary_signature") == current_signature
            ):
                st.divider()
                st.markdown(st.session_state["course_summary"])


def render_quiz():
    st.subheader("练习出题助手")
    course_pages = st.session_state.get("course_pages", [])
    if not course_pages:
        st.info("请先在左侧上传课程 PDF。")
    else:
        available_files = list(dict.fromkeys(page["file_name"] for page in course_pages))
        quiz_file = st.selectbox("选择出题资料", available_files, key="quiz_file")
        file_pages = [
            page
            for page in course_pages
            if page["file_name"] == quiz_file and page["text"]
        ]

        if not file_pages:
            st.warning("这份资料没有可读取的页面。")
        else:
            minimum_page = min(page["page_number"] for page in file_pages)
            maximum_page = max(page["page_number"] for page in file_pages)
            if minimum_page == maximum_page:
                quiz_page_range = (minimum_page, maximum_page)
                st.caption(f"当前资料只有第 {minimum_page} 页可读取")
            else:
                quiz_page_range = st.slider(
                    "出题页码范围",
                    minimum_page,
                    maximum_page,
                    (minimum_page, min(minimum_page + 9, maximum_page)),
                    key="quiz_page_range",
                )

            col_count, col_difficulty = st.columns(2)
            question_count = col_count.number_input(
                "题目数量", min_value=3, max_value=15, value=5, step=1
            )
            difficulty = col_difficulty.selectbox(
                "难度", ["基础", "中等", "综合应用"]
            )
            question_types = st.multiselect(
                "题型",
                ["单选题", "判断题", "简答题"],
                default=["单选题", "判断题", "简答题"],
            )
            selected_quiz_pages = [
                page
                for page in file_pages
                if quiz_page_range[0] <= page["page_number"] <= quiz_page_range[1]
            ]

            if st.button("根据资料生成练习题", type="primary"):
                if not question_types:
                    st.warning("请至少选择一种题型。")
                else:
                    with st.spinner("出题助手 正在分析知识点并生成练习……"):
                        try:
                            st.session_state["quiz_questions"] = generate_course_quiz(
                                quiz_file,
                                selected_quiz_pages,
                                int(question_count),
                                question_types,
                                difficulty,
                            )
                            start_quiz(st.session_state, quiz_file, selected_quiz_pages)
                            st.session_state["quiz_submitted"] = False
                            st.session_state.pop("short_answer_grades", None)
                            st.session_state.pop("saved_quiz_version", None)
                            st.session_state["quiz_version"] = (
                                st.session_state.get("quiz_version", 0) + 1
                            )
                        except Exception as exc:
                            st.error(model_error_message(exc))

            quiz_questions = st.session_state.get("quiz_questions", [])
            if quiz_questions:
                st.caption(f"当前试卷来源：{st.session_state['quiz_source']['file_name']}；切换选项后须点击生成才会更换试卷。")
                st.divider()
                quiz_version = st.session_state.get("quiz_version", 1)
                with st.form(f"quiz_form_{quiz_version}"):
                    for question in quiz_questions:
                        st.markdown(
                            f'**第 {question["id"]} 题 · {question["type"]}**  '
                            f'{question["question"]}'
                        )
                        answer_key = f'quiz_{quiz_version}_{question["id"]}'
                        if question["type"] in {"单选题", "判断题"}:
                            st.radio(
                                "请选择答案",
                                question["options"],
                                index=None,
                                key=answer_key,
                                label_visibility="collapsed",
                            )
                        else:
                            st.text_area(
                                "请输入你的答案",
                                key=answer_key,
                                placeholder="写出你的思路或答案……",
                            )
                        st.caption(
                            "资料页码："
                            + ", ".join(
                                f'第 {page} 页' for page in question["source_pages"]
                            )
                        )
                    submitted = st.form_submit_button("提交答案", type="primary")
                    if submitted:
                        submit_quiz(st.session_state, quiz_questions, quiz_version)

                if st.session_state.get("quiz_submitted"):
                    st.caption("评分与保存针对最后一次提交的答案；修改后请重新提交。")
                    objective_total = 0
                    objective_correct = 0
                    for question in quiz_questions:
                        answer_key = f'quiz_{quiz_version}_{question["id"]}'
                        student_answer = st.session_state.get("submitted_answers", {}).get(question["id"], "")
                        if question["type"] in {"单选题", "判断题"}:
                            objective_total += 1
                            expected = question["answer"].strip().upper()
                            actual = str(student_answer).strip().upper()
                            if question["type"] == "单选题":
                                expected = expected[:1]
                                actual = actual[:1]
                            is_correct = actual == expected
                            objective_correct += int(is_correct)
                            status = "✅ 回答正确" if is_correct else "❌ 回答错误"
                        else:
                            status = "📝 请对照参考答案自查"

                        with st.expander(
                            f'第 {question["id"]} 题：{status}',
                            expanded=True,
                        ):
                            st.write(f'你的答案：{student_answer or "未作答"}')
                            st.write(f'参考答案：{question["answer"]}')
                            st.write(f'解析：{question["explanation"]}')

                    if objective_total:
                        st.metric(
                            "客观题得分",
                            f"{objective_correct}/{objective_total}",
                        )

                    short_answer_items = []
                    for question in quiz_questions:
                        if question["type"] != "简答题":
                            continue
                        answer_key = f'quiz_{quiz_version}_{question["id"]}'
                        short_answer_items.append(
                            {
                                "id": question["id"],
                                "question": question["question"],
                                "student_answer": (
                                    st.session_state.get("submitted_answers", {}).get(question["id"], "")
                                ),
                                "reference_answer": question["answer"],
                                "source_pages": question["source_pages"],
                            }
                        )

                    if short_answer_items:
                        if st.button("使用 AI 批改简答题", type="primary"):
                            with st.spinner("批改助手 正在分析答案……"):
                                try:
                                    st.session_state["short_answer_grades"] = (
                                        grade_short_answers(short_answer_items)
                                    )
                                except Exception as exc:
                                    st.error(model_error_message(exc))

                        grades = st.session_state.get("short_answer_grades", [])
                        if grades:
                            st.subheader("AI 简答题批改")
                            total_score = sum(grade["score"] for grade in grades)
                            st.metric(
                                "简答题得分",
                                f"{total_score}/{len(grades) * 5}",
                            )
                            for grade in grades:
                                with st.expander(
                                    f'第 {grade["id"]} 题 · {grade["score"]}/5 分 '
                                    f'· {grade["error_type"]}',
                                    expanded=True,
                                ):
                                    st.write(f'批改反馈：{grade["feedback"]}')
                                    st.write(f'复习建议：{grade["suggestion"]}')

                    grades = st.session_state.get("short_answer_grades", [])
                    grading_ready = not short_answer_items or bool(grades)
                    if not grading_ready:
                        st.info("请先完成 AI 简答题批改，再保存完整学习记录。")
                    elif st.session_state.get("saved_quiz_version") == quiz_version:
                        st.success("本次练习已经保存到学习记录。")
                    elif st.button("保存本次练习记录"):
                        grade_by_id = {grade["id"]: grade for grade in grades}
                        details = []
                        for question in quiz_questions:
                            answer_key = f'quiz_{quiz_version}_{question["id"]}'
                            student_answer = st.session_state.get("submitted_answers", {}).get(question["id"], "")
                            detail = {
                                "id": question["id"],
                                "type": question["type"],
                                "question": question["question"],
                                "student_answer": student_answer,
                                "reference_answer": question["answer"],
                                "source_pages": question["source_pages"],
                                "explanation": question["explanation"],
                                "document_id": st.session_state["quiz_source"]["document_id"],
                            }
                            if question["type"] in {"单选题", "判断题"}:
                                expected = question["answer"].strip().upper()
                                actual = str(student_answer).strip().upper()
                                if question["type"] == "单选题":
                                    expected, actual = expected[:1], actual[:1]
                                detail["is_correct"] = actual == expected
                                detail["score"] = 1 if actual == expected else 0
                                detail["error_type"] = (
                                    "完全正确" if actual == expected else "客观题答错"
                                )
                                detail["suggestion"] = (
                                    "" if actual == expected else "结合资料页码重新复习该知识点。"
                                )
                            else:
                                grade = grade_by_id.get(question["id"], {})
                                detail["is_correct"] = grade.get("score", 0) >= 4
                                detail["score"] = grade.get("score", 0)
                                detail["error_type"] = grade.get("error_type", "未批改")
                                detail["suggestion"] = grade.get("suggestion", "")
                            details.append(detail)

                        short_score = sum(grade["score"] for grade in grades)
                        attempt_id = save_quiz_attempt(
                            st.session_state["quiz_source"]["file_name"],
                            objective_correct,
                            objective_total,
                            short_score,
                            len(short_answer_items) * 5,
                            details,
                            attempt_key=st.session_state["attempt_key"],
                        )
                        st.session_state["saved_quiz_version"] = quiz_version
                        st.success(f"学习记录已保存，记录编号：{attempt_id}")


def render_records():
    st.subheader("学习记录与错题本")
    attempts = load_quiz_attempts()
    if not attempts:
        st.info("还没有学习记录。完成一次练习并保存后，会显示在这里。")
    else:
        st.markdown("#### 历史练习")
        record_rows = []
        wrong_questions = []
        for attempt in attempts:
            details = json.loads(attempt["details_json"])
            wrong_count = sum(not detail.get("is_correct", False) for detail in details)
            record_rows.append(
                {
                    "时间": attempt["created_at"],
                    "资料": attempt["file_name"],
                    "客观题": (
                        f'{attempt["objective_correct"]}/{attempt["objective_total"]}'
                    ),
                    "简答题": f'{attempt["short_score"]}/{attempt["short_total"]}',
                    "错题数": wrong_count,
                }
            )
            for detail in details:
                if not detail.get("is_correct", False):
                    wrong_questions.append(
                        {**detail, "created_at": attempt["created_at"], "file_name": attempt["file_name"]}
                    )

        st.dataframe(record_rows, width="stretch", hide_index=True)
        st.markdown(f"#### 错题本（{len(wrong_questions)} 题）")
        if not wrong_questions:
            st.success("目前没有错题，继续保持！")
        else:
            for index, detail in enumerate(wrong_questions, start=1):
                with st.expander(
                    f'{index}. {detail["type"]} · {detail["error_type"]} '
                    f'· {detail["created_at"]}'
                ):
                    st.write(f'题目：{detail["question"]}')
                    st.write(f'你的答案：{detail["student_answer"] or "未作答"}')
                    st.write(f'参考答案：{detail["reference_answer"]}')
                    st.write(f'复习建议：{detail.get("suggestion") or "复习对应知识点。"}')
                    st.caption(
                        f'资料：{detail["file_name"]}；页码：'
                        + ", ".join(
                            f'第 {page} 页' for page in detail["source_pages"]
                        )
                    )


def render_plan():
    st.subheader("个性化复习规划助手")
    attempts = load_quiz_attempts()
    if not attempts:
        st.info("请先完成并保存至少一次练习，规划助手 才能分析学习情况。")
    else:
        total_questions = 0
        total_wrong = 0
        error_counts = Counter()
        for attempt in attempts:
            details = json.loads(attempt["details_json"])
            total_questions += len(details)
            for detail in details:
                if not detail.get("is_correct", False):
                    total_wrong += 1
                    error_counts[detail.get("error_type", "未知")] += 1

        col_attempts, col_wrong = st.columns(2)
        col_attempts.metric("已保存练习", len(attempts))
        col_wrong.metric("累计错题", f"{total_wrong}/{total_questions}")
        if error_counts:
            st.caption(
                "主要错误类型："
                + "；".join(
                    f"{error_type} {count} 次"
                    for error_type, count in error_counts.most_common(3)
                )
            )

        col_days, col_minutes = st.columns(2)
        plan_days = col_days.selectbox("计划周期", [3, 7, 14, 30], index=1)
        daily_minutes = col_minutes.selectbox(
            "每天可学习时间", [15, 20, 30, 45, 60], index=2
        )

        if st.button("生成个性化复习计划", type="primary"):
            with st.spinner("规划助手 正在分析历史练习与错题……"):
                try:
                    plan_content = generate_study_plan(
                        attempts, int(plan_days), int(daily_minutes)
                    )
                    plan_id = save_study_plan(
                        int(plan_days), int(daily_minutes), plan_content
                    )
                    st.success(f"复习计划已生成并保存，计划编号：{plan_id}")
                except Exception as exc:
                    st.error(model_error_message(exc))

        latest_plan = load_latest_study_plan()
        if latest_plan:
            st.divider()
            st.caption(
                f'最近计划生成于 {latest_plan["created_at"]} · '
                f'{latest_plan["plan_days"]} 天 · '
                f'每天 {latest_plan["daily_minutes"]} 分钟'
            )
            st.markdown(latest_plan["content"])
