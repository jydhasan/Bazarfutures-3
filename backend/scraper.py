"""
Chaldal Price Scraper
Fetches product prices from chaldal.com and updates the database.
Runs daily via APScheduler.
"""
import logging
import re
import httpx
from bs4 import BeautifulSoup
from decimal import Decimal
from sqlalchemy.orm import Session

import models
from database import SessionLocal
from config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _name_match_score(target: str, candidate: str) -> float:
    t = set(_normalize_text(target).split())
    c = set(_normalize_text(candidate).split())
    if not t or not c:
        return 0.0
    inter = len(t & c)
    if inter == 0:
        return 0.0
    return inter / max(len(t), len(c))


def _parse_price_from_html(html: str) -> Decimal | None:
    """Extract the discounted/current price from a Chaldal product page."""
    soup = BeautifulSoup(html, "lxml")

    # Chaldal shows prices in spans like: ৳109
    # Try multiple selectors (Chaldal updates their markup occasionally)
    selectors = [
        "span.price",
        "[class*='discountedPrice']",
        "[class*='price']",
        "div.price span",
    ]

    def _extract_number(text: str) -> Decimal | None:
        match = re.search(r"(\d+(?:\.\d{1,2})?)", text.replace(",", ""))
        if not match:
            return None
        try:
            return Decimal(match.group(1))
        except Exception:
            return None

    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(" ", strip=True).replace("৳", "").strip()
            price = _extract_number(text)
            if price is not None:
                return price

    # fallback: check common JSON-LD / app script blocks
    for script in soup.find_all("script"):
        txt = (script.string or script.get_text() or "").strip()
        if not txt:
            continue
        match = re.search(r'"price"\s*:\s*"?(?P<price>\d+(?:\.\d+)?)"?', txt)
        if match:
            try:
                return Decimal(match.group("price"))
            except Exception:
                continue
    return None


def _extract_price_from_catalog_card(card) -> Decimal | None:
    """Handle Chaldal search-result card markup."""
    discounted = card.select_one(".productV2discountedPrice")
    if discounted:
        # current/discounted price is typically the first direct span
        for el in discounted.find_all("span", recursive=False):
            text = el.get_text(" ", strip=True).replace("৳", "").replace(",", "")
            m = re.search(r"(\d+(?:\.\d{1,2})?)", text)
            if m:
                return Decimal(m.group(1))

    for sel in [".price > span", ".price span", ".productV2discountedPrice span"]:
        el = card.select_one(sel)
        if not el:
            continue
        text = el.get_text(" ", strip=True).replace("৳", "").replace(",", "")
        m = re.search(r"(\d+(?:\.\d{1,2})?)", text)
        if m:
            return Decimal(m.group(1))
    return None


def _parse_price_from_search_results(html: str, target_name: str) -> Decimal | None:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(".productV2Catalog")
    if not cards:
        return None

    best_price = None
    best_score = 0.0
    for card in cards:
        name_el = card.select_one(".pvName .nameTextWithEllipsis") or card.select_one(".pvName")
        candidate_name = name_el.get_text(" ", strip=True) if name_el else ""
        score = _name_match_score(target_name, candidate_name)
        if score <= best_score:
            continue
        price = _extract_price_from_catalog_card(card)
        if price is None:
            continue
        best_price = price
        best_score = score

    # avoid accidental mismatch when URL returns unrelated list
    if best_score >= 0.34:
        return best_price
    return None


async def fetch_price_from_chaldal(url: str, product_name: str | None = None) -> Decimal | None:
    """Async fetch a single product price from Chaldal URL."""
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                if product_name:
                    from_search = _parse_price_from_search_results(resp.text, product_name)
                    if from_search is not None:
                        return from_search
                return _parse_price_from_html(resp.text)
    except Exception as e:
        logger.warning(f"Chaldal fetch error for {url}: {e}")
    return None


def run_price_update():
    """
    Main scheduled job: iterate all active products with a Chaldal URL,
    fetch the latest price, and update the database.
    Called by APScheduler every day at SCRAPE_SCHEDULE_HOUR:SCRAPE_SCHEDULE_MINUTE.
    """
    import asyncio

    db: Session = SessionLocal()
    try:
        products = (
            db.query(models.Product)
            .filter(
                models.Product.is_active == True,
                models.Product.chaldal_url.isnot(None),
            )
            .all()
        )
        total_products = len(products)
        logger.info(f"Starting price update for {total_products} products...")

        async def _update_all():
            updated = 0
            failed = 0
            checked = 0
            for product in products:
                if not product.chaldal_url:
                    continue
                checked += 1
                lookup_name = f"{product.name_en} {product.name_bn}".strip()
                price = await fetch_price_from_chaldal(product.chaldal_url, lookup_name)
                if price is None:
                    failed += 1
                    logger.warning(f"  No price found for: {product.name_en} ({product.chaldal_url})")
                    continue
                if price and price != product.current_price:
                    old = product.current_price
                    product.current_price = price
                    hist = models.PriceHistory(
                        product_id=product.id,
                        price=price,
                        source="chaldal_auto",
                    )
                    db.add(hist)
                    updated += 1
                    logger.info(f"  {product.name_en}: ৳{old} → ৳{price}")
            db.commit()
            logger.info(f"Price update complete. {updated}/{checked} changed, {failed} failed.")
            return {
                "total_products": total_products,
                "checked": checked,
                "updated": updated,
                "failed": failed,
            }

        return asyncio.run(_update_all())

    except Exception as e:
        logger.error(f"Price update job failed: {e}")
        db.rollback()
        return {
            "total_products": 0,
            "checked": 0,
            "updated": 0,
            "failed": 0,
            "error": str(e),
        }
    finally:
        db.close()


def run_settlement_job():
    """
    Auto-settle contracts whose maturity_date == today.
    Called daily after price update.
    """
    from datetime import date, datetime, timezone
    from decimal import Decimal
    from config import get_settings

    cfg = get_settings()
    db: Session = SessionLocal()
    try:
        today = date.today()
        contracts = (
            db.query(models.Contract)
            .filter(
                models.Contract.maturity_date == today,
                models.Contract.status == models.ContractStatus.matched,
            )
            .all()
        )
        logger.info(f"Settlement job: {len(contracts)} contracts to settle.")

        for contract in contracts:
            product = db.query(models.Product).filter(models.Product.id == contract.product_id).first()
            seller  = db.query(models.User).filter(models.User.id == contract.seller_id).first()
            buyer   = db.query(models.User).filter(models.User.id == contract.buyer_id).first()
            if not (product and seller and buyer):
                continue

            market_price    = product.current_price
            price_diff      = contract.contract_price - market_price
            gross_pnl       = price_diff * contract.quantity
            commission      = (abs(gross_pnl) * Decimal(str(cfg.PLATFORM_COMMISSION_RATE))).quantize(Decimal("0.01"))
            net_pnl         = gross_pnl - (commission if gross_pnl > 0 else -commission)
            security        = contract.security_amount

            def add_txn(uid, cid, ttype, amt, note):
                db.add(models.Transaction(
                    user_id=uid, contract_id=cid,
                    txn_type=ttype, amount=abs(amt),
                    status=models.TransactionStatus.completed, note=note,
                ))

            if net_pnl >= 0:
                seller_r = security + net_pnl
                buyer_r  = max(security - net_pnl, Decimal("0"))
                seller.frozen_balance -= security; seller.balance += seller_r
                buyer.frozen_balance  -= security; buyer.balance  += buyer_r
                add_txn(seller.id, contract.id, models.TransactionType.settlement_gain, net_pnl, "Auto settlement gain")
                add_txn(buyer.id,  contract.id, models.TransactionType.settlement_loss, net_pnl, "Auto settlement loss")
            else:
                loss     = abs(net_pnl)
                buyer_r  = security + loss
                seller_r = max(security - loss, Decimal("0"))
                buyer.frozen_balance  -= security; buyer.balance  += buyer_r
                seller.frozen_balance -= security; seller.balance += seller_r
                add_txn(buyer.id,  contract.id, models.TransactionType.settlement_gain, loss, "Auto settlement gain")
                add_txn(seller.id, contract.id, models.TransactionType.settlement_loss, loss, "Auto settlement loss")

            contract.status           = models.ContractStatus.settled
            contract.settlement_price = market_price
            contract.pnl              = gross_pnl
            contract.settled_at       = datetime.now(timezone.utc)
            logger.info(f"  Settled {contract.contract_code} — PnL: ৳{gross_pnl}")

        db.commit()
        logger.info("Settlement job done.")

    except Exception as e:
        logger.error(f"Settlement job failed: {e}")
        db.rollback()
    finally:
        db.close()
