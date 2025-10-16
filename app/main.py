from app.api.routers.auth import router as auth_router
from app.api.routers.calendar import router as calendar_router
from app.api.routers.chat import router as chat_router
from app.api.routers.itineraries import router as itineraries_router
from app.api.routers.places import router as places_router
from app.api.routers.webhooks import api_webhook_router, webhook_router
from app.core.repository import repo
from app.core.settings import get_settings
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    _ = get_settings()
    application.state.repo = repo

    application.include_router(auth_router)
    application.include_router(webhook_router)
    application.include_router(api_webhook_router)  # Add API webhooks route
    application.include_router(itineraries_router)
    application.include_router(chat_router)
    application.include_router(calendar_router)
    application.include_router(places_router)
    return application


app = create_app()
