import os
import sys
from dotenv import load_dotenv

load_dotenv(override=True)

def _get_secret(key: str, default: str = None) -> str:
    val = os.getenv(key)
    if not val:
        try:
            import streamlit as st
            if hasattr(st, "secrets") and key in st.secrets:
                val = str(st.secrets[key])
        except Exception:
            pass
    return val or default

GROQ_API_KEY = _get_secret("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise EnvironmentError("GROQ_API_KEY is not set in .env or Streamlit Secrets")

FAST_MODEL = "llama-3.1-8b-instant"
SMART_MODEL = "llama-3.3-70b-versatile"
MODEL = FAST_MODEL

CHROMA_PATH = "./chroma_db"

# ─── Feature Flags ────────────────────────────────────────────────
# Set to False to skip the second self-reflection LLM call per response.
# Disabling halves API costs and latency significantly.
ENABLE_SELF_REFLECTION = (_get_secret("ENABLE_SELF_REFLECTION", "true") or "true").lower() == "true"

# ─── Personal Details (from .env or st.secrets — never hardcode PII in source) ──
PERSONAL_NAME   = _get_secret("PERSONAL_NAME", "Farhan Aaqil")
PERSONAL_EMAIL  = _get_secret("EMAIL_ADDRESS", "fadurrani543@gmail.com")
AFFILIATION     = _get_secret("AFFILIATION", "Jayaprakash Narayan College of Engineering, Mahbubnagar, Telangana, India")
DEPARTMENT      = _get_secret("DEPARTMENT", "Artificial Intelligence and Machine Learning")


# ─── Model Selection ──────────────────────────────────────────────

def get_model(tier: str = "fast") -> str:
    """
    Centralised model resolver.
    tier: 'fast' (default) | 'smart' | 'selected' (honours UI override)
    """
    if tier == "selected":
        return os.getenv("SELECTED_SMART_MODEL", SMART_MODEL)
    if tier == "smart":
        return SMART_MODEL
    return FAST_MODEL

# ─── Agent Registry ───────────────────────────────────────────────
AGENTS = {
    "github": "Handles GitHub repos, READMEs, commits",
    "linkedin": "Handles LinkedIn scraping and outreach",
    "job": "Handles job/internship search and apply",
    "project_manager": "Tracks tasks, deadlines, progress",
    "career": "Tracks skills, resume, interview prep",
    "growth": "Handles content posting and reach",
    "research": "Writes papers and finds publishers",
    "email": "Handles all outreach and follow-ups",
    "briefing": "Daily morning summary agent",
}