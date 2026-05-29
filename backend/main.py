from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import chat, meetings, webhook
from config import get_settings
from db import init_db

# override=True so values in .env beat any stray vars already in the shell
# (e.g. a GOOGLE_APPLICATION_CREDENTIALS pointing at another project's key).
load_dotenv(override=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="AI Meeting Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
    # Any installed Chrome extension build will get a different ID, so we match
    # the scheme via regex instead of pinning a specific origin.
    allow_origin_regex=r"^chrome-extension://.*$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meetings.router)
app.include_router(chat.router)
app.include_router(webhook.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
