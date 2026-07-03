---
applyTo: "backend/**"
---

# Backend — Convenciones IaRadio

## Reglas fundamentales

### Async siempre
```python
# ✅ Correcto
async def get_campaigns(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.user_id == user.id))
    return result.scalars().all()

# ❌ Nunca — bloquea el event loop
def get_campaigns_sync(db: Session = Depends(get_db)):
    return db.query(Campaign).all()
```

### DB session pattern
```python
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

async def endpoint(db: AsyncSession = Depends(get_db)):
    ...
```

### SQL seguro — siempre parámetros vinculados
```python
# ✅ Correcto
await db.execute(select(User).where(User.email == email))
await db.execute(text("SELECT * FROM users WHERE id = :id"), {"id": user_id})

# ❌ SQL injection — NUNCA
await db.execute(text(f"SELECT * FROM users WHERE email = '{email}'"))
```

### Schemas Pydantic separados
```python
# Request (entrada del usuario)
class CampaignCreate(BaseModel):
    name: str
    message: str

# Response (lo que devuelve la API)
class CampaignResponse(BaseModel):
    id: UUID
    name: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

### HTTPException con códigos semánticos
```python
raise HTTPException(status_code=404, detail="Campaign not found")
raise HTTPException(status_code=403, detail="Not authorized")
raise HTTPException(status_code=422, detail="Invalid phone number format")
```

## Estructura de un nuevo endpoint

```python
# backend/app/api/v1/mi_modulo.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.schemas.mi_modulo import MiCreate, MiResponse

router = APIRouter(prefix="/mi-modulo", tags=["mi-modulo"])

@router.get("/", response_model=list[MiResponse])
async def list_items(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ...
```

Registrar el router en `backend/app/main.py`:
```python
from app.api.v1 import mi_modulo
app.include_router(mi_modulo.router, prefix="/api/v1")
```

## Migraciones Alembic
- SIEMPRE crear una nueva versión — NUNCA editar versiones existentes
- Nombrado: `NNNN_descripcion_corta.py` (ej: `0021_add_sms_column.py`)
- Generar: `cd backend && alembic revision --autogenerate -m "descripcion"`
- Aplicar: `alembic upgrade head`

## Celery tasks (`workers/tasks.py`)
- Tasks en `@celery_app.task(bind=True, max_retries=3)`
- Usa `self.retry(exc=exc, countdown=60)` para reintentos
- No importar modelos SQLAlchemy directamente en tasks — usar IDs y consultar dentro
- Anti-ban: usar `asyncio.sleep()` entre mensajes de campaña (delay configurado por plan)

## Servicios clave — NO instanciar directamente en endpoints

| Servicio | Import |
|----------|--------|
| Claude AI | `from app.services.claude_service import ClaudeService` |
| RAG | `from app.services.rag_service import RAGService` |
| Twilio WhatsApp | `from app.services.twilio_service import TwilioService` |
| Storage R2 | `from app.services.storage_service import StorageService` |
| Calendar | `from app.services.calendar_service import CalendarService` |

## Variables de entorno (desde `app/config.py`)
```python
from app.config import settings

settings.ANTHROPIC_API_KEY
settings.TWILIO_ACCOUNT_SID
settings.STRIPE_SECRET_KEY
settings.DATABASE_URL
settings.REDIS_URL
```
NUNCA usar `os.environ.get()` directamente — siempre `settings.*`

## Tests backend
- Ubicación: `backend/tests/` y archivos `test_*.py` en raíz de `backend/`
- Runner: `cd backend && pytest`
- Usar `pytest-asyncio` para tests async
- Fixtures de DB en `backend/tests/conftest.py`
- Mockear servicios externos (Twilio, Stripe, Anthropic) con `unittest.mock.patch`
