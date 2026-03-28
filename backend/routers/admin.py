from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from decimal import Decimal

from database import get_db
from auth import get_current_admin
import models
import schemas

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ─── Schemas for price fetch preview ──────────────────────────────────────────

class PricePreviewItem(BaseModel):
    product_id:    int
    name_bn:       str
    name_en:       str
    unit:          str
    old_price:     float
    fetched_price: Optional[float]   # None = fetch failed / no URL
    chaldal_url:   Optional[str]
    changed:       bool
    fetch_status:  str               # "ok" | "no_url" | "failed" | "unchanged"


class PricePreviewResponse(BaseModel):
    items:        List[PricePreviewItem]
    fetched:      int
    failed:       int
    no_url:       int
    changed:      int


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


@router.get("/fetch-preview", response_model=PricePreviewResponse)
async def fetch_price_preview(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    """
    Fetch latest prices from Chaldal for all products that have a chaldal_url.
    Does NOT save to DB — returns a preview so admin can review & confirm.
    """
    import asyncio
    import httpx
    from bs4 import BeautifulSoup

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 13; SM-G991B) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.6261.119 Mobile Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "bn-BD,bn;q=0.9,en;q=0.8",
    }

    products = (
        db.query(models.Product)
        .filter(models.Product.is_active == True)
        .order_by(models.Product.name_bn)
        .all()
    )

    def _parse_price(html: str) -> Decimal | None:
        soup = BeautifulSoup(html, "lxml")
        # Chaldal uses React — price is in script JSON or visible spans
        # Try multiple selectors
        for sel in [
            "[class*='discountedPrice']",
            "[class*='price'] span",
            "span[class*='price']",
            ".price",
            "[data-price]",
        ]:
            el = soup.select_one(sel)
            if el:
                raw = el.get_text(strip=True).replace("৳","").replace(",","").strip()
                try:
                    val = Decimal(raw)
                    if 1 < val < 100000:   # sanity check
                        return val
                except Exception:
                    pass

        # Try JSON in script tags (Chaldal embeds price in __NEXT_DATA__)
        import re, json
        scripts = soup.find_all("script", {"id": "__NEXT_DATA__"})
        for sc in scripts:
            try:
                data = json.loads(sc.string or "")
                # walk the JSON looking for a price key
                text = json.dumps(data)
                matches = re.findall(r'"price"\s*:\s*(\d+(?:\.\d+)?)', text)
                if matches:
                    val = Decimal(matches[0])
                    if 1 < val < 100000:
                        return val
            except Exception:
                pass
        return None

    async def _fetch_one(product) -> PricePreviewItem:
        if not product.chaldal_url:
            return PricePreviewItem(
                product_id=product.id, name_bn=product.name_bn,
                name_en=product.name_en, unit=product.unit,
                old_price=float(product.current_price),
                fetched_price=None, chaldal_url=None,
                changed=False, fetch_status="no_url",
            )
        try:
            async with httpx.AsyncClient(
                headers=HEADERS, timeout=20,
                follow_redirects=True,
                limits=httpx.Limits(max_connections=10),
            ) as client:
                resp = await client.get(product.chaldal_url)
                if resp.status_code == 200:
                    fetched = _parse_price(resp.text)
                    if fetched:
                        changed = fetched != product.current_price
                        return PricePreviewItem(
                            product_id=product.id, name_bn=product.name_bn,
                            name_en=product.name_en, unit=product.unit,
                            old_price=float(product.current_price),
                            fetched_price=float(fetched),
                            chaldal_url=product.chaldal_url,
                            changed=changed,
                            fetch_status="ok" if changed else "unchanged",
                        )
                    else:
                        # Parse failed — return old price so admin can manually edit
                        return PricePreviewItem(
                            product_id=product.id, name_bn=product.name_bn,
                            name_en=product.name_en, unit=product.unit,
                            old_price=float(product.current_price),
                            fetched_price=None,
                            chaldal_url=product.chaldal_url,
                            changed=False, fetch_status="failed",
                        )
                else:
                    raise Exception(f"HTTP {resp.status_code}")
        except Exception as e:
            return PricePreviewItem(
                product_id=product.id, name_bn=product.name_bn,
                name_en=product.name_en, unit=product.unit,
                old_price=float(product.current_price),
                fetched_price=None, chaldal_url=product.chaldal_url,
                changed=False, fetch_status="failed",
            )

    # Run all fetches concurrently (max 10 at a time)
    semaphore = asyncio.Semaphore(10)
    async def _guarded(p):
        async with semaphore:
            return await _fetch_one(p)

    items = await asyncio.gather(*[_guarded(p) for p in products])

    fetched   = sum(1 for i in items if i.fetch_status in ("ok", "unchanged"))
    failed    = sum(1 for i in items if i.fetch_status == "failed")
    no_url    = sum(1 for i in items if i.fetch_status == "no_url")
    changed   = sum(1 for i in items if i.changed)

    return PricePreviewResponse(
        items=list(items),
        fetched=fetched, failed=failed, no_url=no_url, changed=changed,
    )


@router.post("/trigger-scrape")
def trigger_scrape(
    background_tasks: BackgroundTasks,
    _: models.User = Depends(get_current_admin),
):
    """Manually trigger Chaldal price scrape (background, no preview)."""
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
