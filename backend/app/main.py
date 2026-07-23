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
from app.coach.router import router as coach_router
from app.admin.router import router as admin_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await event_bus.initialize()

    # Warm up multi-provider registry and verify LLM endpoint connectivity
    try:
        from app.llm.factory import LLMProviderFactory
        from app.llm.registry import ProviderRegistry

        await ProviderRegistry.warmup()
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

    # Phase 43 (spec 20 §3/§11.7)：在席感知休眠/喚醒——人離席（grace 後）全房休眠、
    # 重連自動解凍。接 presence_tracker 的 present↔absent hook 到 room_hibernation。
    try:
        from app.agents.room_hibernation import resume_room, suspend_room
        from app.ws.presence_tracker import presence_tracker

        presence_tracker.set_presence_hooks(
            on_absent=suspend_room, on_present=resume_room
        )
        logger.info("Presence-aware room hibernation hooks registered")
    except Exception as exc:
        logger.warning("Failed to register presence hibernation hooks: %s", exc)

    # Spec 15: Timer warnings + timeout watcher
    timer_task = None
    try:
        import asyncio
        from app.timer.watcher import timer_watcher_loop
        timer_task = asyncio.create_task(timer_watcher_loop())
        logger.info("Timer watcher task started")
    except Exception as exc:
        logger.warning("Failed to start timer watcher: %s", exc)

    # Spec 04-06 §5.8 (v4.15): Facilitator-paced progression watcher。
    # 取代 crew advance vote watcher + stability watcher：成為 micro 內細格 sub_phase
    # 的單一推進驅動者（readiness / time-box / time-floor + 決定性轉場交代）。
    # 跨 micro / macro 邊界仍由 Evaluator 驅動。
    progression_task = None
    try:
        import asyncio
        from app.progression.watcher import progression_watcher_loop
        progression_task = asyncio.create_task(progression_watcher_loop())
        logger.info("Progression watcher task started")
    except Exception as exc:
        logger.warning("Failed to start progression watcher: %s", exc)

    # Phase 42 D5 (G14 / #35, spec 20 §13.2)：LLM 健康背景監測（proactive 每 30s
    # ping providers）；判定持續 down → fail-stop 全房暫停，恢復 → 自動續跑。
    llm_health_task = None
    try:
        import asyncio
        from app.llm.health_monitor import health_monitor
        llm_health_task = asyncio.create_task(health_monitor.background_loop())
        logger.info("LLM health monitor task started")
        # Phase 42 補正 R4（P1-7）：startup reconciliation——收復 outage 期間重啟
        # 而永久卡 pause_reason=llm_down 的孤兒房（monitor 純 in-memory 邊緣觸發，
        # 重啟即弄丟 recovered 邊緣；spec 20 §13.4）。背景執行不擋啟動。
        from app.llm.fail_stop import reconcile_on_startup
        asyncio.create_task(reconcile_on_startup())
    except Exception as exc:
        logger.warning("Failed to start LLM health monitor: %s", exc)

    yield

    # Shutdown
    try:
        from app.timer.watcher import stop_timer_watcher
        from app.progression.watcher import stop_progression_watcher
        from app.llm.health_monitor import stop_llm_health_monitor
        await stop_timer_watcher()
        await stop_progression_watcher()
        await stop_llm_health_monitor()
        if timer_task is not None:
            timer_task.cancel()
        if progression_task is not None:
            progression_task.cancel()
        if llm_health_task is not None:
            llm_health_task.cancel()
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
app.include_router(coach_router)
app.include_router(admin_router)
