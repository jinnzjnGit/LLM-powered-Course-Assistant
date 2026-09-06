"""模型连接与调用边界；不在日志里输出密钥或完整资料。"""
from functools import lru_cache
import logging
from .config import MAX_CONTEXT_CHARACTERS, APP_DIR, get_model_setting


logger = logging.getLogger(__name__)


def configured_model():
    key = get_model_setting("OPENAI_API_KEY", "api_key")
    url = get_model_setting("OPENAI_BASE_URL", "base_url", "https://api.deepseek.com")
    model = get_model_setting("OPENAI_MODEL", "model")
    if not key or not model:
        raise ValueError("请在本地.env或Streamlit Secrets中填写API密钥和模型名称。")
    return get_ai_client(key, url), model


def load_prompt(name: str) -> str:
    return (APP_DIR / "prompts" / name).read_text(encoding="utf-8")


@lru_cache(maxsize=4)
def get_ai_client(api_key: str, base_url: str):
    from openai import OpenAI
    return OpenAI(api_key=api_key, base_url=base_url, timeout=45.0, max_retries=1)


def check_context(text: str) -> None:
    if len(text) > MAX_CONTEXT_CHARACTERS:
        raise ValueError("内容超过30000字符，请缩小页码范围、减少题目或缩短答案。")


def model_error_message(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return f"生成结果未通过检查：{exc}"
    status = getattr(exc, "status_code", None)
    error_type = type(exc).__name__
    error_code = getattr(exc, "code", None)
    logger.error(
        "Model request failed: type=%s status=%s code=%s",
        error_type,
        status,
        error_code,
    )
    if status in (401, 403):
        return "模型认证失败，请检查Streamlit Secrets中的密钥及访问权限（HTTP 401/403）。"
    if status in (402, 429):
        return "模型额度不足或请求过于频繁，请检查额度或稍后重试（HTTP 402/429）。"
    if status in (400, 404, 422):
        return f"模型请求被拒绝，请核对OPENAI_MODEL和OPENAI_BASE_URL（HTTP {status}）。"
    if status is not None and int(status) >= 500:
        return f"DeepSeek服务端暂时异常，请稍后重试（HTTP {status}）。"
    if error_type == "APITimeoutError":
        return "连接DeepSeek超时；云端网络或服务响应较慢，请稍后重试（诊断：APITimeoutError）。"
    if error_type == "APIConnectionError":
        return "Streamlit云端无法连接DeepSeek，请检查服务地址或稍后重试（诊断：APIConnectionError）。"
    return f"模型服务调用失败，请查看Manage app日志（诊断：{error_type}）。"
