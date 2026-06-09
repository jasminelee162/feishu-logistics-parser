"""
配置读取模块。

使用 dotenv 从项目根目录的 `.env` 中读取飞书/多维表相关配置。
"""
from pathlib import Path
import os
from dotenv import load_dotenv


# 尝试从项目根目录加载 .env
ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=str(ENV_PATH))
else:
    load_dotenv()


SETTINGS = {
    "APP_ID": os.getenv("APP_ID", ""),
    "APP_SECRET": os.getenv("APP_SECRET", ""),
    "APP_TOKEN": os.getenv("APP_TOKEN", ""),
    "ORDER_TABLE_ID": os.getenv("ORDER_TABLE_ID", ""),
        "ADDRESS_TABLE_ID": os.getenv("ADDRESS_TABLE_ID", ""),
        "SUMMARY_TABLE_ID": os.getenv("SUMMARY_TABLE_ID", ""),
        "UNKNOWN_TABLE_ID": os.getenv("UNKNOWN_TABLE_ID", ""),
    "SUMMARY_ALLOWED_FIELDS": os.getenv("SUMMARY_ALLOWED_FIELDS", ""),
}


__all__ = ["SETTINGS"]
"""配置模块：从 .env 加载运行时配置。

使用 `python-dotenv` 读取项目根目录下的 `.env` 文件。
提供应用需要的基础配置项并返回字典。
"""
from dotenv import load_dotenv
import os
from pathlib import Path


def load_settings() -> dict:
    """加载并返回配置字典。

    从项目根目录加载 `.env`，并读取下列变量：
    - APP_ID
    - APP_SECRET
    - APP_TOKEN
    - ORDER_TABLE_ID
    - ADDRESS_TABLE_ID
    - SUMMARY_TABLE_ID

    返回一个简单的字典供程序使用。
    """
    # 默认从项目根目录查找 .env
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        # 仍然调用 load_dotenv() 以便使用系统环境变量
        load_dotenv()

    return {
        "APP_ID": os.getenv("APP_ID", ""),
        "APP_SECRET": os.getenv("APP_SECRET", ""),
        "APP_TOKEN": os.getenv("APP_TOKEN", ""),
        "ORDER_TABLE_ID": os.getenv("ORDER_TABLE_ID", ""),
        "ADDRESS_TABLE_ID": os.getenv("ADDRESS_TABLE_ID", ""),
        "SUMMARY_TABLE_ID": os.getenv("SUMMARY_TABLE_ID", ""),
        "UNKNOWN_TABLE_ID": os.getenv("UNKNOWN_TABLE_ID", ""),
        "SUMMARY_ALLOWED_FIELDS": os.getenv("SUMMARY_ALLOWED_FIELDS", ""),
    }
