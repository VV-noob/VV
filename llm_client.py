"""Thin wrapper around DeepSeek's OpenAI-compatible API."""

import os

BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"


def create_client():
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set; use --mock to run without an API key.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is required: python -m pip install openai") from exc
    return OpenAI(api_key=key, base_url=BASE_URL)
