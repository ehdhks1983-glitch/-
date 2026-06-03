import secrets

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import AdminUser, DbSession
from app.core.errors import ApiError
from app.models.product import Product
from app.schemas.product import (
    ProductCreate,
    ProductOut,
    ProductSecretOut,
    ProductUpdate,
)

router = APIRouter(prefix="/products", tags=["products"])


def _generate_secret() -> str:
    return secrets.token_urlsafe(32)


def _get_or_404(db, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise ApiError(404, "not_found", "제품을 찾을 수 없습니다.")
    return product


@router.get("", response_model=list[ProductOut])
def list_products(db: DbSession, _: AdminUser, include_inactive: bool = False):
    stmt = select(Product).order_by(Product.id)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    return list(db.scalars(stmt))


@router.post("", response_model=ProductSecretOut, status_code=201)
def create_product(payload: ProductCreate, db: DbSession, _: AdminUser):
    if db.scalar(select(Product).where(Product.code == payload.code)):
        raise ApiError(409, "code_exists", "이미 존재하는 제품 코드입니다.")
    if db.scalar(select(Product).where(Product.prefix == payload.prefix)):
        raise ApiError(409, "prefix_exists", "이미 사용 중인 prefix입니다.")
    product = Product(
        code=payload.code,
        name=payload.name,
        prefix=payload.prefix,
        description=payload.description,
        secret_key=_generate_secret(),
        max_hwid_count=payload.max_hwid_count,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductSecretOut)
def get_product(product_id: int, db: DbSession, _: AdminUser):
    return _get_or_404(db, product_id)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, db: DbSession, _: AdminUser):
    product = _get_or_404(db, product_id)
    if payload.name is not None:
        product.name = payload.name
    if payload.description is not None:
        product.description = payload.description
    if payload.is_active is not None:
        product.is_active = payload.is_active
    if payload.max_hwid_count is not None:
        product.max_hwid_count = payload.max_hwid_count
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}")
def delete_product(product_id: int, db: DbSession, _: AdminUser):
    """Soft delete (is_active=False)."""
    product = _get_or_404(db, product_id)
    product.is_active = False
    db.add(product)
    db.commit()
    return {"ok": True, "id": product_id}


@router.post("/{product_id}/rotate-secret", response_model=ProductSecretOut)
def rotate_secret(product_id: int, db: DbSession, _: AdminUser):
    product = _get_or_404(db, product_id)
    product.secret_key = _generate_secret()
    db.add(product)
    db.commit()
    db.refresh(product)
    return product
