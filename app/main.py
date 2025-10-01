from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.chat import router as chat_router
from app.api.routers.itineraries import router as itineraries_router
from app.core.llm_provider import LLMProvider
from app.core.repository import repo
from app.core.settings import get_settings

load_dotenv()


def create_app() -> FastAPI:
    application = FastAPI(title="Traverse Backend")

    # CORS: adjust origins when frontend domain is known
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize shared dependencies
    settings = get_settings()
    application.state.llm_provider = LLMProvider(model=settings.aisuite_model)
    application.state.repo = repo

    application.include_router(itineraries_router)
    application.include_router(chat_router)
    return application


app = create_app()
