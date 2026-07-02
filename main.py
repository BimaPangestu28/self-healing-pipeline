from contextlib import asynccontextmanager
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.config.model_registry import refresh_runtime_model_from_registry
from src.config.observability import setup_langfuse_otel

# Load environment variables from .env file
load_dotenv()

# Global dispatcher instance
_dispatcher = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - initialize dispatcher on startup."""
    global _dispatcher

    # Setup Langfuse OpenTelemetry observability
    if setup_langfuse_otel():
        print("Langfuse OTEL observability enabled")
    else:
        print("Langfuse OTEL observability disabled or not configured")

    # Load active model from registry (optional) before creating agents
    await refresh_runtime_model_from_registry()

    # Initialize router-tier dispatcher and all participating agents
    print("Initializing SRE router-tier agents...")
    import src.api.routes as routes_module

    _dispatcher = await routes_module._get_dispatcher()
    routes_module._dispatcher = _dispatcher
    print("SRE router-tier agents ready!")

    yield

    # Cleanup on shutdown
    print("Shutting down SRE router-tier agents...")


# Create FastAPI application
app = FastAPI(
    title="AI DevOps SRE Agent",
    description=(
        "Multi-agent SRE system powered by Microsoft Agent Framework. "
        "Provides Kubernetes operations, monitoring, node management, "
        "issue tracking, and log analysis capabilities."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1", tags=["SRE Agent"])


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": "AI DevOps SRE Agent",
        "version": "1.0.0",
        "description": "Multi-agent SRE system powered by Microsoft Agent Framework",
        "endpoints": {
            "chat": "/api/v1/chat",
            "approve": "/api/v1/approve",
            "health": "/api/v1/health",
            "threads": "/api/v1/threads",
            "webhook_alerts": "/api/v1/webhook/alerts",
        },
        "documentation": "/docs",
    }


def main():
    """Run the application with uvicorn."""
    import uvicorn

    app_port = int(os.getenv("APP_PORT", "8001"))

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=app_port,
        reload=True,  # Enable auto-reload for development
    )


if __name__ == "__main__":
    main()
