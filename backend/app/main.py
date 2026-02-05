"""
AI Tender Architect - FastAPI Application
Main entry point for the backend API.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import health, tenders, companies, projects, anac


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    settings = get_settings()
    print(f"🚀 Starting {settings.project_name} v{settings.version}")
    print(f"📡 Supabase URL: {settings.supabase_url[:30]}...")
    
    yield
    
    # Shutdown
    print("👋 Shutting down...")


# Initialize FastAPI application
settings = get_settings()

app = FastAPI(
    title=settings.project_name,
    description="""
## AI Tender Architect API

Piattaforma SaaS per l'automazione della partecipazione ai bandi di gara pubblici.

### Funzionalità principali:
- 📄 **Tender Analysis**: Analisi automatica dei documenti di gara
- 🏢 **Company Knowledge Base**: Gestione documenti aziendali con RAG
- ✍️ **Proposal Generation**: Generazione automatica delle risposte ai bandi

### Autenticazione
L'API utilizza Supabase per l'autenticazione. I token JWT devono essere inclusi nell'header `Authorization`.
    """,
    version=settings.version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configure CORS for development
# TODO: Restrict origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Register Routers
# =============================================================================

# Health check router (no prefix, accessible at /health)
app.include_router(health.router)

# Tenders router
app.include_router(tenders.router, prefix="/api/v1/tenders", tags=["Tenders"])

# Companies router
app.include_router(companies.router, prefix="/api/v1/companies", tags=["Companies"])

# Projects router
app.include_router(projects.router, prefix="/api/v1/projects", tags=["Projects"])

# ANAC Public Tenders router (no auth required)
app.include_router(anac.router, prefix="/api/v1/anac", tags=["ANAC Tenders"])


# =============================================================================
# Root Endpoint
# =============================================================================

@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint - API welcome message.
    """
    return {
        "message": f"Welcome to {settings.project_name} API",
        "version": settings.version,
        "docs": "/docs",
        "health": "/health"
    }


# =============================================================================
# Run with Uvicorn (for development)
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug
    )
