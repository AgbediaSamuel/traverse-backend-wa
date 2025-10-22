import os

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class Settings(BaseModel):
    aisuite_model: str = os.getenv("AISUITE_MODEL", "openai:gpt-4o-mini")
    resend_api_key: str = os.getenv("RESEND_API_KEY", "")
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3456")


def get_settings() -> Settings:
    return Settings()
