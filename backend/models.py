"""
SQLAlchemy ORM Models — BazarFutures
"""
from datetime import datetime, date
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, DateTime, Date,
    ForeignKey, Text, Enum, UniqueConstraint, Index, func
)
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    pass


# ─── Enums ────────────────────────────────────────────────────────────────────

class UserRole(str, PyEnum):
    user  = "user"
    admin = "admin"

class ContractType(str, PyEnum):
    sell = "sell"   # seller creates — wants to sell at fixed price
    buy  = "buy"    # buyer creates  — wants to buy  at fixed price

class ContractStatus(str, PyEnum):
    open     = "open"       # accepting bids
    matched  = "matched"    # one bid accepted, locked
    settled  = "settled"    # maturity passed, P&L distributed
    expired  = "expired"    # no bid accepted before maturity
    cancelled = "cancelled"

class BidStatus(str, PyEnum):
    pending  = "pending"
    accepted = "accepted"
    rejected = "rejected"
    expired  = "expired"

class ProposalStatus(str, PyEnum):
    pending  = "pending"
    accepted = "accepted"
    rejected = "rejected"
    countered = "countered"

class TransactionType(str, PyEnum):
    deposit          = "deposit"
    withdrawal       = "withdrawal"
    security_lock    = "security_lock"
    security_release = "security_release"
    settlement_gain  = "settlement_gain"
    settlement_loss  = "settlement_loss"
    commission       = "commission"

class TransactionStatus(str, PyEnum):
    pending   = "pending"
    completed = "completed"
    failed    = "failed"
    cancelled = "cancelled"

class PaymentMethod(str, PyEnum):
    bkash   = "bkash"
    nagad   = "nagad"
    rocket  = "rocket"
    bank    = "bank"
    card    = "card"

class ProductCategory(str, PyEnum):
    sobji    = "সবজি"
    fol      = "ফল"
    dal_chal = "ডাল/চাল"
    moshla   = "মশলা"
    dairy    = "ডেইরি"
    others   = "অন্যান্য"


# ─── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(120), nullable=False)
    email         = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role          = Column(Enum(UserRole), default=UserRole.user, nullable=False)
    is_active     = Column(Boolean, default=True)
    balance       = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    frozen_balance = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    bkash_number  = Column(String(20))
    nagad_number  = Column(String(20))
    rocket_number = Column(String(20))
    bank_account  = Column(String(50))
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())

    contracts     = relationship("Contract", back_populates="seller",
                                 foreign_keys="Contract.seller_id")
    bids          = relationship("Bid", back_populates="bidder")
    proposals     = relationship("Proposal", back_populates="proposer")
    transactions  = relationship("Transaction", back_populates="user")


class Product(Base):
    __tablename__ = "products"

    id            = Column(Integer, primary_key=True, index=True)
    name_bn       = Column(String(120), nullable=False)
    name_en       = Column(String(120), nullable=False)
    unit          = Column(String(50), nullable=False)   # e.g. "12 pcs", "1 kg"
    category      = Column(Enum(ProductCategory), nullable=False)
    current_price = Column(Numeric(10, 2), nullable=False)
    chaldal_url   = Column(String(500))
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())

    price_history = relationship("PriceHistory", back_populates="product",
                                 order_by="PriceHistory.recorded_at.desc()")
    contracts     = relationship("Contract", back_populates="product")


class PriceHistory(Base):
    __tablename__ = "price_history"

    id          = Column(Integer, primary_key=True, index=True)
    product_id  = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    price       = Column(Numeric(10, 2), nullable=False)
    source      = Column(String(50), default="chaldal")
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    product     = relationship("Product", back_populates="price_history")

    __table_args__ = (
        Index("ix_price_history_product_date", "product_id", "recorded_at"),
    )


class Contract(Base):
    __tablename__ = "contracts"

    id              = Column(Integer, primary_key=True, index=True)
    contract_code   = Column(String(20), unique=True, nullable=False, index=True)
    product_id      = Column(Integer, ForeignKey("products.id"), nullable=False)
    seller_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    buyer_id        = Column(Integer, ForeignKey("users.id"))          # set after match

    contract_type   = Column(Enum(ContractType), default=ContractType.sell, nullable=False)
    quantity        = Column(Numeric(10, 2), nullable=False)           # in product units
    contract_price  = Column(Numeric(10, 2), nullable=False)           # per unit
    total_value     = Column(Numeric(12, 2), nullable=False)           # qty × price
    security_amount = Column(Numeric(10, 2), nullable=False)           # 15% of total

    maturity_date   = Column(Date, nullable=False, index=True)
    settlement_price= Column(Numeric(10, 2))                           # filled at settlement
    pnl             = Column(Numeric(10, 2))                           # profit/loss

    status          = Column(Enum(ContractStatus), default=ContractStatus.open, nullable=False, index=True)
    terms           = Column(Text)                                     # optional conditions

    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    matched_at      = Column(DateTime(timezone=True))
    settled_at      = Column(DateTime(timezone=True))

    product  = relationship("Product", back_populates="contracts")
    seller   = relationship("User", back_populates="contracts", foreign_keys=[seller_id])
    buyer    = relationship("User", foreign_keys=[buyer_id])
    bids     = relationship("Bid", back_populates="contract",
                             cascade="all, delete-orphan")
    proposals = relationship("Proposal", back_populates="contract",
                              cascade="all, delete-orphan")


class Bid(Base):
    __tablename__ = "bids"

    id          = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False)
    bidder_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    bid_price   = Column(Numeric(10, 2), nullable=False)   # per unit
    status      = Column(Enum(BidStatus), default=BidStatus.pending, nullable=False)
    message     = Column(Text)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    responded_at = Column(DateTime(timezone=True))

    contract    = relationship("Contract", back_populates="bids")
    bidder      = relationship("User", back_populates="bids")


class Proposal(Base):
    """Custom negotiation proposal from a potential buyer."""
    __tablename__ = "proposals"

    id              = Column(Integer, primary_key=True, index=True)
    contract_id     = Column(Integer, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False)
    proposer_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    proposed_price  = Column(Numeric(10, 2), nullable=False)
    proposed_qty    = Column(Numeric(10, 2))
    proposed_date   = Column(Date)
    message         = Column(Text)
    status          = Column(Enum(ProposalStatus), default=ProposalStatus.pending, nullable=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    responded_at    = Column(DateTime(timezone=True))

    contract        = relationship("Contract", back_populates="proposals")
    proposer        = relationship("User", back_populates="proposals")


class Transaction(Base):
    __tablename__ = "transactions"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=False)
    contract_id     = Column(Integer, ForeignKey("contracts.id"), nullable=True)
    txn_type        = Column(Enum(TransactionType), nullable=False, index=True)
    amount          = Column(Numeric(12, 2), nullable=False)
    status          = Column(Enum(TransactionStatus), default=TransactionStatus.pending)
    payment_method  = Column(Enum(PaymentMethod))
    external_txn_id = Column(String(100))   # bkash TrxID etc.
    account_number  = Column(String(50))    # bkash/nagad number
    note            = Column(Text)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    completed_at    = Column(DateTime(timezone=True))

    user            = relationship("User", back_populates="transactions")
