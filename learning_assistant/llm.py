"""模型连接与调用边界；不在日志里输出密钥或完整资料。"""
from functools import lru_cache
from .config import MAX_CONTEXT_CHARACTERS, APP_DIR, get_model_setting


def configured_model():
    key = get_model_setting("OPENAI_API_KEY", "api_key")
    url = get_model_setting("OPENAI_BASE_URL", "base_url", "https://api.deepseek.com")
    model = get_model_setting("OPENAI_MODEL", "model")
    if not key or not model:
        raise ValueError("请在.env中填写API密钥和当前服务支持的模型名称。")
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
    if status in (401, 403):
        return "模型认证失败，请检查.env密钥及访问权限。"
    if status in (402, 429):
        return "模型额度不足或请求过于频繁，请检查额度或稍后重试。"
    return "模型服务暂时不可用，请检查网络、模型名称及服务地址后重试。"
