from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import create_db_and_tables
from routes import customers, orders, segments, campaigns, copilot, receipts
from seed.generate import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    seed_if_empty()
    yield


app = FastAPI(title="Bare CRM API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(customers.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(segments.router, prefix="/api")
app.include_router(campaigns.router, prefix="/api")
app.include_router(copilot.router, prefix="/api")
app.include_router(receipts.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "service": "crm-backend"}
