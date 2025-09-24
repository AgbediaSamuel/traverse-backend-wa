import os

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class Settings(BaseModel):
    aisuite_model: str = os.getenv("AISUITE_MODEL", "openai:gpt-4o-mini")


def get_settings() -> Settings:
    return Settings()
