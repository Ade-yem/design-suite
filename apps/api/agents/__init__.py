"""
Agents module
"""

from config import settings
from langchain_google_genai import ChatGoogleGenerativeAI


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=settings.ACTION_MODEL,
        temperature=0,
        google_api_key=settings.GEMINI_API_KEY,
    )