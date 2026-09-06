"""路径固定在项目根目录；不依赖启动终端的工作目录。"""
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = Path(os.getenv("LEARNING_DATABASE_PATH", str(APP_DIR / "data" / "learning.db")))
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_CONTEXT_CHARACTERS = 30000


def get_model_setting(primary_name: str, short_name: str, default: str = "") -> str:
    # 延迟加载，使离线业务测试无需模型SDK或dotenv。
    from dotenv import load_dotenv
    load_dotenv(APP_DIR / ".env", override=False)
    return os.getenv(primary_name) or os.getenv(short_name) or default
