import os
from pathlib import Path
from dotenv import load_dotenv

# Resolve env file relative to this file so it works regardless of the
# working directory uvicorn is launched from.  Try both names because
# Windows sometimes silently appends ".txt" when saving a dotenv file.
_here = Path(__file__).parent
load_dotenv(_here / ".env")
load_dotenv(_here / ".env.txt")   # Windows fallback — no-op if file absent

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
CHANNEL_STUB_URL: str = os.getenv("CHANNEL_STUB_URL", "http://localhost:8001")
CRM_RECEIPT_URL: str = os.getenv("CRM_RECEIPT_URL", "http://localhost:8000/api/receipts")
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./bare.db")

# Base URL for the OpenAI-compatible API.
# Explicit env var wins; otherwise auto-detect OpenRouter keys (sk-or-*).
_explicit_base: str = os.getenv("OPENAI_BASE_URL", "")
if _explicit_base:
    OPENAI_BASE_URL: str = _explicit_base
elif OPENAI_API_KEY.startswith("sk-or-"):
    OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
else:
    OPENAI_BASE_URL = ""   # empty → openai SDK uses its own default
