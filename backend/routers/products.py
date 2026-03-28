from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db
from auth import get_current_user, get_current_admin
import models, schemas

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=List[schemas.ProductOut])
def list_products(
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Product).filter(models.Product.is_active == True)
    if category:
        q = q.filter(models.Product.category == category)
    if search:
        q = q.filter(
            models.Product.name_bn.ilike(f"%{search}%") |
            models.Product.name_en.ilike(f"%{search}%")
        )
    return q.order_by(models.Product.name_bn).all()


@router.get("/{product_id}", response_model=schemas.ProductWithHistory)
def get_product(product_id: int, days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(404, "পণ্য পাওয়া যায়নি")

    since = datetime.now(timezone.utc) - timedelta(days=days)
    history = (
        db.query(models.PriceHistory)
        .filter(
            models.PriceHistory.product_id == product_id,
            models.PriceHistory.recorded_at >= since,
        )
        .order_by(models.PriceHistory.recorded_at)
        .all()
    )
    product.price_history = history
    return product


@router.get("/{product_id}/history", response_model=List[schemas.PriceHistoryOut])
def price_history(
    product_id: int,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return (
        db.query(models.PriceHistory)
        .filter(
            models.PriceHistory.product_id == product_id,
            models.PriceHistory.recorded_at >= since,
        )
        .order_by(models.PriceHistory.recorded_at)
        .all()
    )


# ─── Admin Only ───────────────────────────────────────────────────────────────

@router.post("", response_model=schemas.ProductOut, status_code=201)
def create_product(
    payload: schemas.ProductCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    product = models.Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    # Record initial price in history
    _record_price(db, product.id, product.current_price)
    return product


@router.patch("/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: int,
    payload: schemas.ProductUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(404, "পণ্য পাওয়া যায়নি")

    old_price = product.current_price
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(product, field, value)

    # If price changed, record in history
    if payload.current_price and payload.current_price != old_price:
        _record_price(db, product_id, payload.current_price)

    db.commit()
    db.refresh(product)
    return product


@router.post("/bulk-price-update", response_model=dict)
def bulk_price_update(
    payload: schemas.AdminPriceUpdateBulk,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    """Admin updates multiple product prices at once (from Chaldal)."""
    updated = 0
    for item in payload.updates:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        if product and product.current_price != item.new_price:
            product.current_price = item.new_price
            _record_price(db, product.id, item.new_price)
            updated += 1
    db.commit()
    return {"updated": updated, "total": len(payload.updates)}


def _record_price(db: Session, product_id: int, price):
    hist = models.PriceHistory(product_id=product_id, price=price)
    db.add(hist)
    db.flush()
