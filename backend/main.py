"""
BazarFutures — FastAPI Application Entry Point
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from config import get_settings
from database import engine
from models import Base
import seed as seed_module

# Routers
from routers import auth, products, contracts, wallet, admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger   = logging.getLogger(__name__)
settings = get_settings()

# ─── Scheduler ────────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler(timezone="Asia/Dhaka")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database tables ready")

    # Seed initial data
    seed_module.seed()

    # Schedule daily price update (Chaldal scrape) + settlement
    from scraper import run_price_update, run_settlement_job

    scheduler.add_job(
        run_price_update,
        trigger="cron",
        hour=settings.SCRAPE_SCHEDULE_HOUR,
        minute=settings.SCRAPE_SCHEDULE_MINUTE,
        id="price_update",
        replace_existing=True,
    )
    scheduler.add_job(
        run_settlement_job,
        trigger="cron",
        hour=settings.SCRAPE_SCHEDULE_HOUR,
        minute=settings.SCRAPE_SCHEDULE_MINUTE + 10,  # 10 min after price update
        id="settlement",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        f"✅ Scheduler started — price update at "
        f"{settings.SCRAPE_SCHEDULE_HOUR:02d}:{settings.SCRAPE_SCHEDULE_MINUTE:02d} Asia/Dhaka"
    )

    yield

    scheduler.shutdown()
    logger.info("Scheduler stopped")


# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="BazarFutures API",
    description="Bangladesh Agricultural Futures Contract Platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(contracts.router)
app.include_router(wallet.router)
app.include_router(admin.router)


@app.get("/")
def root():
    return {
        "app":     "BazarFutures API",
        "version": "1.0.0",
        "docs":    "/docs",
        "status":  "running",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
