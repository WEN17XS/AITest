from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0")
    frontend_origins = {
        settings.frontend_origin,
    }
    for port in range(5173, 5180):
        frontend_origins.update(
            {
                f"http://localhost:{port}",
                f"http://127.0.0.1:{port}",
                f"http://0.0.0.0:{port}",
            }
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(frontend_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["系统"])
    def health_check() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    return app


app = create_app()
