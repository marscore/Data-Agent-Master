"""App lifespan: init DB + seed default agents on startup."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.database import init_db
from app.platform import repository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s (provider=%s, auth=%s, region=%s)",
                settings.APP_NAME, settings.APP_VERSION, settings.LLM_PROVIDER,
                settings.BEDROCK_ANTHROPIC_AUTH_MODE, settings.BEDROCK_REGION)
    init_db()
    repository.seed_defaults()
    yield
    logger.info("Shutting down %s", settings.APP_NAME)
