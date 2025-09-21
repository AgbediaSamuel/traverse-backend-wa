from fastapi import FastAPI


def create_app() -> FastAPI:
    application = FastAPI(title="Kidenomics Backend")
    return application


app = create_app()