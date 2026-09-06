"""只检查本地环境，不发起模型请求，不打印密钥。"""
import importlib
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding="utf-8")
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
print(f"Python: {sys.version.split()[0]}")
failed = sys.version_info < (3, 12)
if failed:
    print("FAIL: 本教学版本要求Python 3.12或以上，验证环境为3.12。")
for name in ["streamlit", "dotenv", "pypdf", "openai", "pymupdf", "rapidocr_onnxruntime", "numpy"]:
    try:
        importlib.import_module(name)
        print(f"OK: {name}")
    except Exception as exc:
        print(f"FAIL: {name} ({type(exc).__name__})")
        failed = True
if not failed:
    from learning_assistant.config import get_model_setting
    configured = bool(get_model_setting("OPENAI_API_KEY", "api_key") and get_model_setting("OPENAI_MODEL", "model"))
    print("模型配置：已填写（未验证远程连接）。" if configured else "模型配置：未完整填写；解析、检索和离线测试仍可使用。")
raise SystemExit(1 if failed else 0)
