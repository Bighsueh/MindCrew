import logging
import logging.config
from contextlib import asynccontextmanager

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(asctime)s %(levelname)s [%(name)s] %(message)s", "datefmt": "%H:%M:%S"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "default"},
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        "app": {"level": "INFO"},
        "uvicorn": {"level": "INFO"},
    },
})

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import engine
from app.events.bus import event_bus
from app.auth.router import router as auth_router
from app.users.router import router as users_router
from app.projects.router import router as projects_router
from app.projects.persona_router import router as persona_router
from app.chat.router import router as chat_router
from app.ws.chat_ws import router as chat_ws_router
from app.ws.teacher_ws import router as teacher_ws_router
from app.ws.yjs_ws import router as yjs_ws_router
from app.stages.router import router as stages_router
from app.teacher.router import router as teacher_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await event_bus.initialize()

    # Verify LLM endpoint connectivity
    try:
        from app.llm.factory import LLMProviderFactory

        llm = LLMProviderFactory.get_service()
        healthy = await llm.health_check()
        if healthy:
            logger.info("LLM health check passed")
        else:
            logger.warning("LLM health check FAILED — agents may not generate responses")
    except Exception as exc:
        logger.warning("LLM health check error: %s", exc)

    # Resume agents for all active projects (handles server restart)
    try:
        from sqlalchemy import select

        from app.db.models.project import Project
        from app.db.session import async_session_factory
        from app.seats.manager import seat_manager

        async with async_session_factory() as session:
            result = await session.execute(
                select(Project).where(Project.status == "active")
            )
            active_projects = result.scalars().all()

        for project in active_projects:
            await seat_manager.start_all_agents(project.id)
            logger.info("Resumed agents for project %s (%s)", project.name, project.id)
    except Exception as exc:
        logger.warning("Failed to resume agents on startup: %s", exc)

    # Spec 14 A10: silent_rearrange auto-advance watcher
    stability_task = None
    try:
        import asyncio
        from app.canvas.stability_watcher import stability_watcher_loop
        stability_task = asyncio.create_task(stability_watcher_loop())
        logger.info("Stability watcher task started")
    except Exception as exc:
        logger.warning("Failed to start stability watcher: %s", exc)

    # Spec 15: Timer warnings + timeout watcher
    timer_task = None
    try:
        import asyncio
        from app.timer.watcher import timer_watcher_loop
        timer_task = asyncio.create_task(timer_watcher_loop())
        logger.info("Timer watcher task started")
    except Exception as exc:
        logger.warning("Failed to start timer watcher: %s", exc)

    # Spec 14 N2: Crew advance vote watcher
    crew_vote_task = None
    try:
        import asyncio
        from app.agents.crew_advance_vote_watcher import crew_vote_watcher_loop
        crew_vote_task = asyncio.create_task(crew_vote_watcher_loop())
        logger.info("Crew advance vote watcher task started")
    except Exception as exc:
        logger.warning("Failed to start crew vote watcher: %s", exc)

    yield

    # Shutdown
    try:
        from app.canvas.stability_watcher import stop_stability_watcher
        from app.timer.watcher import stop_timer_watcher
        from app.agents.crew_advance_vote_watcher import stop_crew_vote_watcher
        await stop_stability_watcher()
        await stop_timer_watcher()
        await stop_crew_vote_watcher()
        if stability_task is not None:
            stability_task.cancel()
        if timer_task is not None:
            timer_task.cancel()
        if crew_vote_task is not None:
            crew_vote_task.cancel()
    except Exception as exc:
        logger.warning("Error stopping watcher tasks: %s", exc)

    try:
        from app.seats.manager import seat_manager

        await seat_manager.stop_all()
        logger.info("All agents stopped")
    except Exception as exc:
        logger.warning("Error stopping agents: %s", exc)

    await event_bus.close()
    await engine.dispose()


app = FastAPI(
    title="DTAI API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(projects_router)
app.include_router(persona_router)
app.include_router(chat_router)
app.include_router(chat_ws_router)
app.include_router(teacher_ws_router)
app.include_router(yjs_ws_router)
app.include_router(stages_router)
app.include_router(teacher_router)
