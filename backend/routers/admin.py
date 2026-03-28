from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from auth import get_current_admin
import models
import schemas

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats")
def dashboard_stats(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    total_users = db.query(func.count(models.User.id)).scalar()
    total_products = db.query(func.count(models.Product.id)).filter(
        models.Product.is_active == True).scalar()
    open_contracts = db.query(func.count(models.Contract.id)).filter(
        models.Contract.status == "open").scalar()
    matched = db.query(func.count(models.Contract.id)).filter(
        models.Contract.status == "matched").scalar()
    settled = db.query(func.count(models.Contract.id)).filter(
        models.Contract.status == "settled").scalar()
    pending_deposits = db.query(func.count(models.Transaction.id)).filter(
        models.Transaction.txn_type == models.TransactionType.deposit,
        models.Transaction.status == models.TransactionStatus.pending,
    ).scalar()
    pending_withdrawals = db.query(func.count(models.Transaction.id)).filter(
        models.Transaction.txn_type == models.TransactionType.withdrawal,
        models.Transaction.status == models.TransactionStatus.pending,
    ).scalar()

    total_commission = db.query(func.sum(models.Transaction.amount)).filter(
        models.Transaction.txn_type == models.TransactionType.commission,
        models.Transaction.status == models.TransactionStatus.completed,
    ).scalar() or 0

    return {
        "total_users":          total_users,
        "total_products":       total_products,
        "open_contracts":       open_contracts,
        "matched_contracts":    matched,
        "settled_contracts":    settled,
        "pending_deposits":     pending_deposits,
        "pending_withdrawals":  pending_withdrawals,
        "total_commission":     float(total_commission),
    }


@router.get("/users", response_model=List[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    return db.query(models.User).order_by(models.User.created_at.desc()).all()


@router.patch("/users/{user_id}/toggle", response_model=schemas.UserOut)
def toggle_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "ব্যবহারকারী পাওয়া যায়নি")
    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)
    return user


@router.post("/trigger-scrape")
def trigger_scrape(
    background_tasks: BackgroundTasks,
    _: models.User = Depends(get_current_admin),
):
    """Manually trigger Chaldal price scrape."""
    from scraper import run_price_update
    background_tasks.add_task(run_price_update)
    return {"message": "স্ক্র্যাপিং শুরু হয়েছে (ব্যাকগ্রাউন্ডে চলছে)"}
    result = run_price_update()
    if result.get("error"):
        raise HTTPException(500, f"স্ক্র্যাপিং ব্যর্থ: {result['error']}")
    return {
        "message": (
            f"স্ক্র্যাপিং শেষ। {result['updated']}টি আপডেট, "
            f"{result['failed']}টি ব্যর্থ, মোট যাচাই {result['checked']}।"
        ),
        **result,
    }


@router.post("/preview-scrape")
def preview_scrape(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    """
    Fetch latest prices from Chaldal but DO NOT save in DB.
    Frontend can prefill "new price" inputs; admin decides what to save.
    """
    import asyncio
    from scraper import fetch_price_from_chaldal

    products = (
        db.query(models.Product)
        .filter(
            models.Product.is_active == True,
            models.Product.chaldal_url.isnot(None),
        )
        .all()
    )

    async def _collect():
        updates = []
        checked = 0
        found = 0
        for p in products:
            if not p.chaldal_url:
                continue
            checked += 1
            lookup_name = f"{p.name_en} {p.name_bn}".strip()
            fetched = await fetch_price_from_chaldal(p.chaldal_url, lookup_name)
            if fetched is not None:
                found += 1
            updates.append({
                "product_id": p.id,
                "name_bn": p.name_bn,
                "old_price": float(p.current_price),
                "new_price": float(fetched) if fetched is not None else None,
                "found": fetched is not None,
            })
        return {"checked": checked, "found": found, "updates": updates}

    result = asyncio.run(_collect())
    return {
        "message": f"ফেচ সম্পন্ন। {result['found']}/{result['checked']} দামের ডাটা পাওয়া গেছে।",
        **result,
    }


@router.post("/trigger-settlement")
def trigger_settlement(
    background_tasks: BackgroundTasks,
    _: models.User = Depends(get_current_admin),
):
    """Manually trigger settlement for today's matured contracts."""
    from scraper import run_settlement_job
    background_tasks.add_task(run_settlement_job)
    return {"message": "সেটেলমেন্ট জব শুরু হয়েছে"}


@router.get("/contracts", response_model=List[schemas.ContractOut])
def all_contracts(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    return db.query(models.Contract).order_by(models.Contract.created_at.desc()).all()
