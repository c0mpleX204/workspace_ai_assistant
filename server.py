import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config.config import settings
from infra.db import close_pool
from api.routers.chat_router import router as chat_router
from api.routers.companion_router import router as companion_router
from api.routers.courses_router import router as courses_router
from api.routers.health_router import router as health_router
from api.routers.materials_router import router as materials_router
from api.routers.speech_router import router as speech_router
from services.startup_service import run_startup_tasks

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="AI Assistant Backend", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(materials_router)
app.include_router(courses_router)
app.include_router(companion_router)
app.include_router(speech_router)


@app.on_event("startup")
def on_startup() -> None:
    run_startup_tasks()


@app.on_event("shutdown")
def on_shutdown() -> None:
    close_pool()


if __name__ == "__main__":
    uvicorn.run("server:app", host=settings.host, port=settings.port, reload=False)
