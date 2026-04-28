"""pytest 共用設定：注入假環境變數，避免 import config 時噴 warning。"""
import os
import sys
import pathlib

# 將專案根目錄加入 sys.path，使 `import db / features / prompts` 在 pytest 內可解析
_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
os.environ.setdefault("LINE_CHANNEL_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("DISABLE_SCHEDULER", "1")
