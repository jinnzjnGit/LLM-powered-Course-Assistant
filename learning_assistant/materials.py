from io import BytesIO
from functools import lru_cache
import hashlib
import unicodedata
import numpy as np
import pymupdf
from pypdf import PdfReader
from .config import MAX_PDF_BYTES, MAX_PDF_PAGES


@lru_cache(maxsize=1)
def get_ocr_engine():
    """OCR 模型较大，在整个应用生命周期中只加载一次。"""
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()

def text_needs_ocr(text: str) -> bool:
    """判断普通提取结果是否太少或包含明显乱码。"""
    compact = "".join(text.split())
    if len(compact) < 20:
        return True

    bad_characters = 0
    for character in compact:
        category = unicodedata.category(character)
        if character == "\ufffd" or category in {"Cc", "Cs", "Co"}:
            bad_characters += 1
    return bad_characters / len(compact) > 0.02

def ocr_pdf_page(pdf_page: pymupdf.Page) -> str:
    """将单页渲染为约 216 DPI 图片并执行中英文 OCR。"""
    pixmap = pdf_page.get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=False)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )
    result, _ = get_ocr_engine()(image)
    if not result:
        return ""
    return "\n".join(line[1].strip() for line in result if line[1].strip())

def extract_pdf_pages(
    file_name: str, file_bytes: bytes, force_ocr: bool = False
) -> list[dict]:
    """逐页提取 PDF 文本，对异常页自动 OCR，并保留出处。"""
    if len(file_bytes) > MAX_PDF_BYTES:
        raise ValueError("单个PDF不得超过20MB。")
    document_id = hashlib.sha256(file_bytes).hexdigest()
    reader = PdfReader(BytesIO(file_bytes))
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError("单个PDF不得超过100页，请按章节拆分。")
    rendered_document = pymupdf.open(stream=file_bytes, filetype="pdf")
    try:
        pages = []
        for page_index, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            extraction_method = "普通提取"
            if force_ocr or text_needs_ocr(text):
                ocr_text = ocr_pdf_page(rendered_document[page_index]).strip()
                if ocr_text:
                    text = ocr_text
                    extraction_method = "OCR"
            pages.append(
                {
                    "document_id": document_id,
                    "file_name": file_name,
                    "page_number": page_index + 1,
                    "text": text,
                    "extraction_method": extraction_method,
                }
            )
    finally:
        rendered_document.close()
    return pages

def parse_uploaded_files(uploaded_files, force_ocr: bool) -> tuple[list[dict], list[str]]:
    """解析所有上传文件，返回页面数据和错误信息。"""
    if len(uploaded_files) > 5:
        return [], ["一次最多上传5个PDF，请分批学习。"]
    if len({f.name for f in uploaded_files}) != len(uploaded_files):
        return [], ["存在同名PDF，请重命名后重新上传。"]
    all_pages = []
    errors = []
    for uploaded_file in uploaded_files:
        try:
            all_pages.extend(
                extract_pdf_pages(
                    uploaded_file.name, uploaded_file.getvalue(), force_ocr=force_ocr
                )
            )
        except Exception as exc:
            errors.append(f"{uploaded_file.name}：{exc}")
    return all_pages, errors
