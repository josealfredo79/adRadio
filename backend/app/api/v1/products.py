"""Product/service catalog — /api/v1/products"""
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.product import Product
from app.models.user import User
from app.services.storage_service import upload_bytes

router = APIRouter(prefix="/products", tags=["products"])

logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    name: str
    description: str | None = None
    price: Decimal | None = None
    category: str | None = None
    active: bool = True


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: Decimal | None = None
    category: str | None = None
    active: bool | None = None


class ProductOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    price: Decimal | None
    category: str | None
    photo_url: str | None
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True


ALLOWED_PHOTO_MIME_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5MB


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ProductOut])
async def list_products(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProductOut]:
    result = await db.execute(
        select(Product)
        .where(Product.advertiser_id == current_user.id)
        .order_by(Product.category, Product.name)
    )
    return result.scalars().all()


@router.post("", response_model=ProductOut, status_code=201)
async def create_product(
    body: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductOut:
    product = Product(
        advertiser_id=current_user.id,
        name=body.name,
        description=body.description,
        price=body.price,
        category=body.category,
        active=body.active,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductOut:
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.advertiser_id == current_user.id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.advertiser_id == current_user.id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    await db.delete(product)
    await db.commit()


@router.post("/{product_id}/photo", response_model=ProductOut)
async def upload_product_photo(
    product_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductOut:
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.advertiser_id == current_user.id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    if file.content_type not in ALLOWED_PHOTO_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Tipo de archivo no soportado: {file.content_type}")

    content = await file.read()
    if len(content) > MAX_PHOTO_SIZE:
        raise HTTPException(status_code=413, detail="La imagen supera el límite de 5MB")

    ext = ALLOWED_PHOTO_MIME_TYPES[file.content_type]
    key = f"products/{current_user.id}/{uuid.uuid4()}.{ext}"
    url = await upload_bytes(content, key, file.content_type)
    if not url:
        raise HTTPException(status_code=502, detail="No se pudo guardar la imagen")

    product.photo_url = url
    await db.commit()
    await db.refresh(product)
    return product
