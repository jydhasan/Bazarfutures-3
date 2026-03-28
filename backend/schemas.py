"""
Pydantic v2 Schemas — BazarFutures
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, model_validator

from models import (
    UserRole, ContractType, ContractStatus, BidStatus,
    ProposalStatus, TransactionType, TransactionStatus,
    PaymentMethod, ProductCategory
)


# ─── Auth ─────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    name: str
    email: str
    role: UserRole
    is_active: bool
    balance: Decimal
    frozen_balance: Decimal
    bkash_number: Optional[str] = None
    nagad_number: Optional[str] = None
    rocket_number: Optional[str] = None
    bank_account: Optional[str] = None
    created_at: datetime


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    bkash_number: Optional[str] = None
    nagad_number: Optional[str] = None
    rocket_number: Optional[str] = None
    bank_account: Optional[str] = None


# ─── Product ──────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    name_bn: str = Field(..., min_length=2, max_length=120)
    name_en: str = Field(..., min_length=2, max_length=120)
    unit: str = Field(..., min_length=1, max_length=50)
    category: ProductCategory
    current_price: Decimal = Field(..., gt=0)
    chaldal_url: Optional[str] = None


class ProductUpdate(BaseModel):
    name_bn: Optional[str] = None
    name_en: Optional[str] = None
    unit: Optional[str] = None
    category: Optional[ProductCategory] = None
    current_price: Optional[Decimal] = Field(None, gt=0)
    chaldal_url: Optional[str] = None
    is_active: Optional[bool] = None


class ProductOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    name_bn: str
    name_en: str
    unit: str
    category: ProductCategory
    current_price: Decimal
    chaldal_url: Optional[str] = None
    is_active: bool
    updated_at: Optional[datetime] = None


class PriceHistoryOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    product_id: int
    price: Decimal
    source: str
    recorded_at: datetime


class ProductWithHistory(ProductOut):
    price_history: List[PriceHistoryOut] = []


class BulkPriceUpdate(BaseModel):
    """Admin bulk price update from Chaldal."""
    updates: List[dict]   # [{product_id: int, new_price: float}]


# ─── Contract ─────────────────────────────────────────────────────────────────

class ContractCreate(BaseModel):
    product_id: int
    contract_type: ContractType = ContractType.sell
    quantity: Decimal = Field(..., gt=0)
    contract_price: Decimal = Field(..., gt=0)
    maturity_date: date
    terms: Optional[str] = None

    @model_validator(mode="after")
    def maturity_must_be_future(self):
        from datetime import date as dt
        if self.maturity_date <= dt.today():
            raise ValueError("ম্যাচিউরিটি তারিখ অবশ্যই ভবিষ্যতে হতে হবে")
        return self


class ContractOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    contract_code: str
    product_id: int
    seller_id: int
    buyer_id: Optional[int] = None
    contract_type: ContractType
    quantity: Decimal
    contract_price: Decimal
    total_value: Decimal
    security_amount: Decimal
    maturity_date: date
    settlement_price: Optional[Decimal] = None
    pnl: Optional[Decimal] = None
    status: ContractStatus
    terms: Optional[str] = None
    created_at: datetime
    matched_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None


class ContractDetail(ContractOut):
    product: ProductOut
    seller: UserOut
    buyer: Optional[UserOut] = None
    bids: List["BidOut"] = []
    proposals: List["ProposalOut"] = []


# ─── Bid ──────────────────────────────────────────────────────────────────────

class BidCreate(BaseModel):
    bid_price: Decimal = Field(..., gt=0)
    message: Optional[str] = None


class BidOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    contract_id: int
    bidder_id: int
    bid_price: Decimal
    status: BidStatus
    message: Optional[str] = None
    created_at: datetime
    responded_at: Optional[datetime] = None


class BidWithBidder(BidOut):
    bidder: UserOut


# ─── Proposal ─────────────────────────────────────────────────────────────────

class ProposalCreate(BaseModel):
    proposed_price: Decimal = Field(..., gt=0)
    proposed_qty: Optional[Decimal] = Field(None, gt=0)
    proposed_date: Optional[date] = None
    message: Optional[str] = None

    @model_validator(mode="after")
    def date_must_be_future(self):
        from datetime import date as dt
        if self.proposed_date and self.proposed_date <= dt.today():
            raise ValueError("প্রস্তাবিত তারিখ ভবিষ্যতে হতে হবে")
        return self


class ProposalOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    contract_id: int
    proposer_id: int
    proposed_price: Decimal
    proposed_qty: Optional[Decimal] = None
    proposed_date: Optional[date] = None
    message: Optional[str] = None
    status: ProposalStatus
    created_at: datetime


# ─── Transaction / Wallet ─────────────────────────────────────────────────────

class DepositRequest(BaseModel):
    amount: Decimal = Field(..., ge=500)   # min ৳500
    payment_method: PaymentMethod
    account_number: str = Field(..., min_length=10)
    external_txn_id: str = Field(..., min_length=5)   # bkash TrxID


class WithdrawRequest(BaseModel):
    amount: Decimal = Field(..., ge=200)
    payment_method: PaymentMethod
    account_number: str = Field(..., min_length=10)


class TransactionOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    user_id: int
    contract_id: Optional[int] = None
    txn_type: TransactionType
    amount: Decimal
    status: TransactionStatus
    payment_method: Optional[PaymentMethod] = None
    external_txn_id: Optional[str] = None
    account_number: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


# ─── Settlement Preview ────────────────────────────────────────────────────────

class SettlementPreview(BaseModel):
    contract_id: int
    contract_code: str
    product_name: str
    contract_price: Decimal
    market_price: Decimal
    quantity: Decimal
    pnl: Decimal                  # positive = seller gain
    seller_receives: Decimal
    buyer_receives: Decimal
    platform_commission: Decimal


# ─── Admin ────────────────────────────────────────────────────────────────────

class AdminPriceUpdateItem(BaseModel):
    product_id: int
    new_price: Decimal = Field(..., gt=0)


class AdminPriceUpdateBulk(BaseModel):
    updates: List[AdminPriceUpdateItem]


# Update forward refs
ContractDetail.model_rebuild()
