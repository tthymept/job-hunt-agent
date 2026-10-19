import os
import sys
from pathlib import Path

# The agents live in the repo root and read API keys when imported. Dummy values
# let the tests import them without a .env (e.g. in CI); no test calls a real service.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

for name, value in {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_KEY": "test-key",
    "DATABASE_URL": "postgresql://test",
    "RAPIDAPI_KEY": "test-key",
    "GEMINI_API_KEY": "test-key",
}.items():
    os.environ.setdefault(name, value)
