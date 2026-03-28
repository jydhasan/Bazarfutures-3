"""
Contract Router — create, bid, accept, settle
"""
import random
import string
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session, joinedload

from config import get_settings
from database import get_db
from auth import get_current_user, get_current_admin
import models, schemas

router  = APIRouter(prefix="/api/contracts", tags=["contracts"])
settings = get_settings()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _gen_code() -> str:
    return "CF" + "".join(random.choices(string.digits, k=6))


def _freeze_balance(db: Session, user: models.User, amount: Decimal):
    if user.balance < amount:
        raise HTTPException(400, f"অপর্যাপ্ত ব্যালেন্স। প্রয়োজন ৳{amount}, আপনার আছে ৳{user.balance}")
    user.balance -= amount
    user.frozen_balance += amount
    txn = models.Transaction(
        user_id=user.id,
        txn_type=models.TransactionType.security_lock,
        amount=amount,
        status=models.TransactionStatus.completed,
        note="জামানত ফ্রিজ করা হয়েছে",
    )
    db.add(txn)


def _release_balance(db: Session, user: models.User, amount: Decimal, note: str = ""):
    user.frozen_balance -= amount
    user.balance += amount
    txn = models.Transaction(
        user_id=user.id,
        txn_type=models.TransactionType.security_release,
        amount=amount,
        status=models.TransactionStatus.completed,
        note=note or "জামানত ছাড় করা হয়েছে",
    )
    db.add(txn)


# ─── List & Detail ────────────────────────────────────────────────────────────

@router.get("", response_model=List[schemas.ContractOut])
def list_contracts(
    status: Optional[str] = None,
    product_id: Optional[int] = None,
    my: bool = False,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user),
):
    q = db.query(models.Contract)
    if my and current_user:
        q = q.filter(models.Contract.seller_id == current_user.id)
    if status:
        q = q.filter(models.Contract.status == status)
    if product_id:
        q = q.filter(models.Contract.product_id == product_id)
    return q.order_by(models.Contract.created_at.desc()).all()


@router.get("/public", response_model=List[schemas.ContractOut])
def list_public_contracts(
    status: Optional[str] = Query("open"),
    product_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Public endpoint — no auth required."""
    q = db.query(models.Contract)
    if status:
        q = q.filter(models.Contract.status == status)
    if product_id:
        q = q.filter(models.Contract.product_id == product_id)
    return q.order_by(models.Contract.created_at.desc()).all()


@router.get("/{contract_id}", response_model=schemas.ContractDetail)
def get_contract(contract_id: int, db: Session = Depends(get_db)):
    contract = (
        db.query(models.Contract)
        .options(
            joinedload(models.Contract.product),
            joinedload(models.Contract.seller),
            joinedload(models.Contract.buyer),
            joinedload(models.Contract.bids).joinedload(models.Bid.bidder),
            joinedload(models.Contract.proposals),
        )
        .filter(models.Contract.id == contract_id)
        .first()
    )
    if not contract:
        raise HTTPException(404, "কন্ট্র্যাক্ট পাওয়া যায়নি")
    return contract


# ─── Create Contract ──────────────────────────────────────────────────────────

@router.post("", response_model=schemas.ContractOut, status_code=201)
def create_contract(
    payload: schemas.ContractCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    product = db.query(models.Product).filter(
        models.Product.id == payload.product_id,
        models.Product.is_active == True,
    ).first()
    if not product:
        raise HTTPException(404, "পণ্য পাওয়া যায়নি")

    total_value     = payload.quantity * payload.contract_price
    security_amount = (total_value * Decimal(str(settings.SECURITY_DEPOSIT_RATE))).quantize(Decimal("0.01"))

    # Freeze security from seller
    _freeze_balance(db, current_user, security_amount)

    contract = models.Contract(
        contract_code   = _gen_code(),
        product_id      = payload.product_id,
        seller_id       = current_user.id,
        contract_type   = payload.contract_type,
        quantity        = payload.quantity,
        contract_price  = payload.contract_price,
        total_value     = total_value,
        security_amount = security_amount,
        maturity_date   = payload.maturity_date,
        terms           = payload.terms,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return contract


# ─── Bid ──────────────────────────────────────────────────────────────────────

@router.post("/{contract_id}/bids", response_model=schemas.BidOut, status_code=201)
def place_bid(
    contract_id: int,
    payload: schemas.BidCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    contract = db.query(models.Contract).filter(models.Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(404, "কন্ট্র্যাক্ট পাওয়া যায়নি")
    if contract.status != models.ContractStatus.open:
        raise HTTPException(400, "এই কন্ট্র্যাক্টে আর বিড করা যাবে না")
    if contract.seller_id == current_user.id:
        raise HTTPException(400, "নিজের কন্ট্র্যাক্টে বিড করা যাবে না")

    # Check duplicate pending bid from same user
    existing = db.query(models.Bid).filter(
        models.Bid.contract_id == contract_id,
        models.Bid.bidder_id   == current_user.id,
        models.Bid.status      == models.BidStatus.pending,
    ).first()
    if existing:
        raise HTTPException(400, "আপনার একটি বিড ইতোমধ্যে অপেক্ষায় আছে")

    bid = models.Bid(
        contract_id = contract_id,
        bidder_id   = current_user.id,
        bid_price   = payload.bid_price,
        message     = payload.message,
    )
    db.add(bid)
    db.commit()
    db.refresh(bid)
    return bid


@router.post("/{contract_id}/bids/{bid_id}/accept", response_model=schemas.ContractOut)
def accept_bid(
    contract_id: int,
    bid_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    contract = db.query(models.Contract).filter(models.Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(404, "কন্ট্র্যাক্ট পাওয়া যায়নি")
    if contract.seller_id != current_user.id:
        raise HTTPException(403, "শুধুমাত্র seller বিড গ্রহণ করতে পারবেন")
    if contract.status != models.ContractStatus.open:
        raise HTTPException(400, "কন্ট্র্যাক্ট আর খোলা নেই")

    bid = db.query(models.Bid).filter(
        models.Bid.id == bid_id,
        models.Bid.contract_id == contract_id,
        models.Bid.status == models.BidStatus.pending,
    ).first()
    if not bid:
        raise HTTPException(404, "বিড পাওয়া যায়নি")

    buyer = db.query(models.User).filter(models.User.id == bid.bidder_id).first()

    # Freeze buyer's security too (buyer side security)
    buyer_security = contract.security_amount
    _freeze_balance(db, buyer, buyer_security)

    # Accept this bid
    bid.status = models.BidStatus.accepted
    bid.responded_at = datetime.now(timezone.utc)

    # Reject all other pending bids & release their security (bidders had no security yet — proposals only)
    other_bids = db.query(models.Bid).filter(
        models.Bid.contract_id == contract_id,
        models.Bid.id != bid_id,
        models.Bid.status == models.BidStatus.pending,
    ).all()
    for b in other_bids:
        b.status = models.BidStatus.rejected
        b.responded_at = datetime.now(timezone.utc)

    # Reject all proposals
    db.query(models.Proposal).filter(
        models.Proposal.contract_id == contract_id,
        models.Proposal.status == models.ProposalStatus.pending,
    ).update({"status": models.ProposalStatus.rejected})

    # Update contract
    contract.status     = models.ContractStatus.matched
    contract.buyer_id   = bid.bidder_id
    contract.matched_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(contract)
    return contract


# ─── Proposal (Custom Negotiation) ────────────────────────────────────────────

@router.post("/{contract_id}/proposals", response_model=schemas.ProposalOut, status_code=201)
def send_proposal(
    contract_id: int,
    payload: schemas.ProposalCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    contract = db.query(models.Contract).filter(models.Contract.id == contract_id).first()
    if not contract or contract.status != models.ContractStatus.open:
        raise HTTPException(400, "কন্ট্র্যাক্ট পাওয়া যায়নি বা খোলা নেই")
    if contract.seller_id == current_user.id:
        raise HTTPException(400, "নিজের কন্ট্র্যাক্টে প্রপোজাল পাঠানো যাবে না")

    proposal = models.Proposal(
        contract_id    = contract_id,
        proposer_id    = current_user.id,
        proposed_price = payload.proposed_price,
        proposed_qty   = payload.proposed_qty,
        proposed_date  = payload.proposed_date,
        message        = payload.message,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


@router.post("/{contract_id}/proposals/{proposal_id}/accept", response_model=schemas.ContractOut)
def accept_proposal(
    contract_id: int,
    proposal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    contract = db.query(models.Contract).filter(models.Contract.id == contract_id).first()
    if not contract or contract.seller_id != current_user.id:
        raise HTTPException(403, "শুধুমাত্র seller প্রপোজাল গ্রহণ করতে পারবেন")
    if contract.status != models.ContractStatus.open:
        raise HTTPException(400, "কন্ট্র্যাক্ট আর খোলা নেই")

    proposal = db.query(models.Proposal).filter(
        models.Proposal.id == proposal_id,
        models.Proposal.contract_id == contract_id,
        models.Proposal.status == models.ProposalStatus.pending,
    ).first()
    if not proposal:
        raise HTTPException(404, "প্রপোজাল পাওয়া যায়নি")

    buyer = db.query(models.User).filter(models.User.id == proposal.proposer_id).first()

    # Update contract with negotiated terms
    new_price  = proposal.proposed_price
    new_qty    = proposal.proposed_qty or contract.quantity
    new_date   = proposal.proposed_date or contract.maturity_date
    total      = new_price * new_qty
    security   = (total * Decimal(str(settings.SECURITY_DEPOSIT_RATE))).quantize(Decimal("0.01"))

    # Refund old seller security, lock new one
    _release_balance(db, current_user, contract.security_amount, "পুরনো জামানত ফেরত")
    _freeze_balance(db, current_user, security)
    _freeze_balance(db, buyer, security)

    # Update contract
    contract.contract_price  = new_price
    contract.quantity        = new_qty
    contract.maturity_date   = new_date
    contract.total_value     = total
    contract.security_amount = security
    contract.status          = models.ContractStatus.matched
    contract.buyer_id        = proposal.proposer_id
    contract.matched_at      = datetime.now(timezone.utc)

    proposal.status       = models.ProposalStatus.accepted
    proposal.responded_at = datetime.now(timezone.utc)

    # Reject all other pending bids/proposals
    db.query(models.Bid).filter(
        models.Bid.contract_id == contract_id,
        models.Bid.status      == models.BidStatus.pending,
    ).update({"status": models.BidStatus.rejected})
    db.query(models.Proposal).filter(
        models.Proposal.contract_id == contract_id,
        models.Proposal.id          != proposal_id,
        models.Proposal.status      == models.ProposalStatus.pending,
    ).update({"status": models.ProposalStatus.rejected})

    db.commit()
    db.refresh(contract)
    return contract


# ─── Settlement (Admin triggers, or auto via scheduler) ───────────────────────

@router.post("/{contract_id}/settle", response_model=schemas.SettlementPreview)
def settle_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    """
    Settle a matched contract.
    Called by admin or automatically by the daily scheduler on maturity date.
    """
    contract = (
        db.query(models.Contract)
        .options(
            joinedload(models.Contract.product),
            joinedload(models.Contract.seller),
            joinedload(models.Contract.buyer),
        )
        .filter(models.Contract.id == contract_id)
        .first()
    )
    if not contract:
        raise HTTPException(404, "কন্ট্র্যাক্ট পাওয়া যায়নি")
    if contract.status != models.ContractStatus.matched:
        raise HTTPException(400, f"শুধুমাত্র matched কন্ট্র্যাক্ট settle করা যাবে (বর্তমান: {contract.status})")

    market_price     = contract.product.current_price
    contract_price   = contract.contract_price
    qty              = contract.quantity
    security         = contract.security_amount
    commission_rate  = Decimal(str(settings.PLATFORM_COMMISSION_RATE))

    # P&L from seller's perspective:
    # seller SELL contract → gains if contract_price > market_price
    price_diff = contract_price - market_price   # positive → seller gain
    gross_pnl  = price_diff * qty

    commission = (abs(gross_pnl) * commission_rate).quantize(Decimal("0.01"))
    net_pnl    = gross_pnl - (commission if gross_pnl > 0 else -commission)

    seller = contract.seller
    buyer  = contract.buyer

    if net_pnl >= 0:
        # Seller gains — buyer pays from their security
        seller_receives = security + net_pnl
        buyer_receives  = security - net_pnl
        buyer_receives  = max(buyer_receives, Decimal("0"))

        # Release seller security + add gain
        seller.frozen_balance -= security
        seller.balance        += seller_receives

        # Deduct from buyer security
        buyer.frozen_balance  -= security
        buyer.balance         += buyer_receives

        # Commission to platform (just record as transaction — admin wallet not modelled)
        _record_txn(db, seller.id, contract.id, models.TransactionType.settlement_gain, net_pnl, "কন্ট্র্যাক্ট লাভ")
        _record_txn(db, buyer.id,  contract.id, models.TransactionType.settlement_loss, net_pnl, "কন্ট্র্যাক্ট লোকসান")
    else:
        # Buyer gains — seller pays
        loss = abs(net_pnl)
        buyer_receives  = security + loss
        seller_receives = security - loss
        seller_receives = max(seller_receives, Decimal("0"))

        seller.frozen_balance -= security
        seller.balance        += seller_receives

        buyer.frozen_balance  -= security
        buyer.balance         += buyer_receives

        _record_txn(db, buyer.id,  contract.id, models.TransactionType.settlement_gain, loss, "কন্ট্র্যাক্ট লাভ")
        _record_txn(db, seller.id, contract.id, models.TransactionType.settlement_loss, loss, "কন্ট্র্যাক্ট লোকসান")

    contract.status           = models.ContractStatus.settled
    contract.settlement_price = market_price
    contract.pnl              = gross_pnl
    contract.settled_at       = datetime.now(timezone.utc)

    db.commit()

    return schemas.SettlementPreview(
        contract_id        = contract.id,
        contract_code      = contract.contract_code,
        product_name       = contract.product.name_bn,
        contract_price     = contract_price,
        market_price       = market_price,
        quantity           = qty,
        pnl                = gross_pnl,
        seller_receives    = seller_receives,
        buyer_receives     = buyer_receives,
        platform_commission= commission,
    )


def _record_txn(db, user_id, contract_id, txn_type, amount, note):
    db.add(models.Transaction(
        user_id=user_id, contract_id=contract_id,
        txn_type=txn_type, amount=abs(amount),
        status=models.TransactionStatus.completed,
        note=note,
    ))
