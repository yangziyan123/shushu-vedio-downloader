from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import video
from .config import ensure_data_dirs, settings


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("startup")
def startup() -> None:
    ensure_data_dirs()


app.include_router(video.router)
