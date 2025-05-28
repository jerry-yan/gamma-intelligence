"""
OpenAI client utilities for Gamma Intelligence
"""
import os
from openai import OpenAI
from django.conf import settings


def get_openai_client():
    """
    Initialize and return OpenAI client with API key
    """
    api_key = getattr(settings, 'OPENAI_API_KEY', None) or os.getenv('OPENAI_API_KEY')

    if not api_key:
        raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY in settings or environment variables.")

    return OpenAI(api_key=api_key)