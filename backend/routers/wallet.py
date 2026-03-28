from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, get_current_admin
import models, schemas

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


@router.get("/balance")
def get_balance(current_user: models.User = Depends(get_current_user)):
    return {
        "balance": current_user.balance,
        "frozen_balance": current_user.frozen_balance,
        "available": current_user.balance,
    }


@router.post("/deposit", response_model=schemas.TransactionOut, status_code=201)
def request_deposit(
    payload: schemas.DepositRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """User submits deposit proof — admin approves."""
    # Check duplicate TrxID
    existing = db.query(models.Transaction).filter(
        models.Transaction.external_txn_id == payload.external_txn_id
    ).first()
    if existing:
        raise HTTPException(400, "এই ট্রানজেকশন ID ইতোমধ্যে ব্যবহৃত হয়েছে")

    txn = models.Transaction(
        user_id         = current_user.id,
        txn_type        = models.TransactionType.deposit,
        amount          = payload.amount,
        status          = models.TransactionStatus.pending,  # admin approves
        payment_method  = payload.payment_method,
        account_number  = payload.account_number,
        external_txn_id = payload.external_txn_id,
        note            = "জমার আবেদন — অ্যাডমিন অনুমোদনের অপেক্ষায়",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@router.post("/withdraw", response_model=schemas.TransactionOut, status_code=201)
def request_withdraw(
    payload: schemas.WithdrawRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.balance < payload.amount:
        raise HTTPException(400, f"অপর্যাপ্ত ব্যালেন্স। আপনার আছে ৳{current_user.balance}")

    # Hold the amount immediately
    current_user.balance -= payload.amount
    current_user.frozen_balance += payload.amount

    txn = models.Transaction(
        user_id        = current_user.id,
        txn_type       = models.TransactionType.withdrawal,
        amount         = payload.amount,
        status         = models.TransactionStatus.pending,
        payment_method = payload.payment_method,
        account_number = payload.account_number,
        note           = "উইথড্র আবেদন — প্রক্রিয়াধীন",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@router.get("/transactions", response_model=List[schemas.TransactionOut])
def list_transactions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Transaction)
        .filter(models.Transaction.user_id == current_user.id)
        .order_by(models.Transaction.created_at.desc())
        .limit(50)
        .all()
    )


# ─── Admin Actions ────────────────────────────────────────────────────────────

@router.post("/admin/approve-deposit/{txn_id}", response_model=schemas.TransactionOut)
def approve_deposit(
    txn_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    txn = db.query(models.Transaction).filter(
        models.Transaction.id == txn_id,
        models.Transaction.txn_type == models.TransactionType.deposit,
        models.Transaction.status == models.TransactionStatus.pending,
    ).first()
    if not txn:
        raise HTTPException(404, "লেনদেন পাওয়া যায়নি বা ইতোমধ্যে প্রক্রিয়া হয়েছে")

    user = db.query(models.User).filter(models.User.id == txn.user_id).first()
    user.balance  += txn.amount
    txn.status     = models.TransactionStatus.completed
    txn.completed_at = datetime.now(timezone.utc)
    txn.note       = "অ্যাডমিন অনুমোদিত"

    db.commit()
    db.refresh(txn)
    return txn


@router.post("/admin/approve-withdrawal/{txn_id}", response_model=schemas.TransactionOut)
def approve_withdrawal(
    txn_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    txn = db.query(models.Transaction).filter(
        models.Transaction.id == txn_id,
        models.Transaction.txn_type == models.TransactionType.withdrawal,
        models.Transaction.status == models.TransactionStatus.pending,
    ).first()
    if not txn:
        raise HTTPException(404, "লেনদেন পাওয়া যায়নি")

    user = db.query(models.User).filter(models.User.id == txn.user_id).first()
    user.frozen_balance -= txn.amount  # release hold
    txn.status           = models.TransactionStatus.completed
    txn.completed_at     = datetime.now(timezone.utc)
    txn.note             = "উইথড্র সম্পন্ন"

    db.commit()
    db.refresh(txn)
    return txn


@router.post("/admin/reject/{txn_id}", response_model=schemas.TransactionOut)
def reject_transaction(
    txn_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    txn = db.query(models.Transaction).filter(
        models.Transaction.id == txn_id,
        models.Transaction.status == models.TransactionStatus.pending,
    ).first()
    if not txn:
        raise HTTPException(404, "লেনদেন পাওয়া যায়নি")

    user = db.query(models.User).filter(models.User.id == txn.user_id).first()

    # If withdrawal was held, release it back
    if txn.txn_type == models.TransactionType.withdrawal:
        user.frozen_balance -= txn.amount
        user.balance        += txn.amount

    txn.status       = models.TransactionStatus.failed
    txn.completed_at = datetime.now(timezone.utc)
    txn.note         = "অ্যাডমিন প্রত্যাখ্যান করেছেন"

    db.commit()
    db.refresh(txn)
    return txn


@router.get("/admin/pending", response_model=List[schemas.TransactionOut])
def list_pending(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    return (
        db.query(models.Transaction)
        .filter(models.Transaction.status == models.TransactionStatus.pending)
        .order_by(models.Transaction.created_at.asc())
        .all()
    )
