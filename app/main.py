import os

from app.api.routers.auth import router as auth_router
from app.api.routers.calendar import router as calendar_router
from app.api.routers.itineraries import router as itineraries_router
from app.api.routers.places import router as places_router
from app.core.csrf_middleware import CSRFProtectionMiddleware
from app.core.repository import repo
from app.core.settings import get_settings
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()


def create_app() -> FastAPI:
    application = FastAPI(title="Traverse Backend")

    # CORS: restrict to localhost ports for development
    # Frontend: localhost:3456 (Next.js)
    # Itinerary Template: localhost:5174 (Vite)
    allowed_origins = [
        "http://localhost:3456",
        "http://localhost:5174",
        "http://127.0.0.1:3456",
        "http://127.0.0.1:5174",
    ]

    # Add production origins from environment if set
    prod_origins = os.getenv("ALLOWED_ORIGINS", "")
    if prod_origins:
        allowed_origins.extend(
            [origin.strip() for origin in prod_origins.split(",") if origin.strip()]
        )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # CSRF Protection: Validate Origin header for state-changing requests
    application.add_middleware(CSRFProtectionMiddleware)

    # Initialize shared dependencies
    _ = get_settings()
    application.state.repo = repo

    application.include_router(auth_router)
    application.include_router(itineraries_router)
    application.include_router(calendar_router)
    application.include_router(places_router)
    return application


app = create_app()
