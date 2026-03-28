"""
Seed script — populates DB with initial products and admin user.
Run once: docker exec bazarfutures_api python seed.py
"""
import sys
from decimal import Decimal
from sqlalchemy.orm import Session

from database import engine, SessionLocal
from models import Base, User, Product, UserRole, ProductCategory
from auth import hash_password
from config import get_settings

settings = get_settings()

PRODUCTS = [
    # (name_bn, name_en, unit, category, price, chaldal_url)
    ("ডিম (Layer)", "Chicken Eggs Layer", "১২ পিস", ProductCategory.others, 109, "https://chaldal.com/chicken-eggs-layer"),
    ("ডিম (সাদা)", "Chicken Eggs White", "১২ পিস", ProductCategory.others, 109, None),
    ("ডিম (ডিসকাউন্ট)", "Chicken Eggs Discounted", "১২ পিস", ProductCategory.others, 109, None),
    ("আলু (নিয়মিত)", "Potato Regular", "১ কেজি", ProductCategory.sobji, Decimal("23"), "https://chaldal.com/potato-regular"),
    ("লাল আলু (Cardinal)", "Red Potato Cardinal", "১ কেজি", ProductCategory.sobji, Decimal("25"), None),
    ("বড় আলু (Diamond)", "Big Diamond Potato", "১ কেজি", ProductCategory.sobji, Decimal("25"), None),
    ("লাল টমেটো", "Red Tomato", "৫০০ গ্রাম", ProductCategory.sobji, Decimal("29"), "https://chaldal.com/red-tomato"),
    ("ফুলকপি", "Cauliflower (Fulkopi)", "পিস", ProductCategory.sobji, Decimal("65"), "https://chaldal.com/cauliflower"),
    ("বাঁধাকপি", "Cabbage (Badhakopi)", "পিস", ProductCategory.sobji, Decimal("49"), "https://chaldal.com/cabbage"),
    ("শসা (দেশি)", "Deshi Cucumber", "৫০০ গ্রাম", ProductCategory.sobji, Decimal("35"), None),
    ("শসা", "Cucumber", "৫০০ গ্রাম", ProductCategory.sobji, Decimal("35"), None),
    ("করলা / ধুন্দল", "Ladies Finger (Dheros)", "৫০০ গ্রাম", ProductCategory.sobji, Decimal("45"), None),
    ("লম্বা বেগুন (কালো)", "Long Brinjal Black", "৫০০ গ্রাম", ProductCategory.sobji, Decimal("45"), None),
    ("মিষ্টি কুমড়া ফালি", "Sweet Pumpkin Slice", "১ কেজি", ProductCategory.sobji, Decimal("45"), None),
    ("মিষ্টি আলু", "Sweet Potato", "৫০০ গ্রাম", ProductCategory.sobji, Decimal("35"), None),
    ("শিম (Flat Bean)", "Flat Bean (Sheem)", "৫০০ গ্রাম", ProductCategory.sobji, Decimal("45"), None),
    ("গাজর (দেশি)", "Deshi Carrot", "৫০০ গ্রাম", ProductCategory.sobji, Decimal("29"), None),
    ("লাল শাক", "Red Spinach (Lal Shak)", "বান্ডেল", ProductCategory.sobji, Decimal("19"), None),
    ("পালং শাক", "Palong Spinach", "বান্ডেল", ProductCategory.sobji, Decimal("19"), None),
    ("কাঁচা পেঁপে", "Green Papaya", "১.৪ কেজি", ProductCategory.sobji, Decimal("55"), None),
    ("পেঁয়াজ (দেশি)", "Deshi Onion", "১ কেজি", ProductCategory.moshla, Decimal("39"), "https://chaldal.com/deshi-onion"),
    ("রসুন (আমদানি)", "Garlic Imported", "৫০০ গ্রাম", ProductCategory.moshla, Decimal("109"), "https://chaldal.com/garlic-imported"),
    ("রসুন (দেশি)", "Deshi Garlic", "৫০০ গ্রাম", ProductCategory.moshla, Decimal("49"), None),
    ("আদা (আমদানি)", "Imported Ginger", "৫০০ গ্রাম", ProductCategory.moshla, Decimal("99"), None),
    ("আদা (দেশি)", "Deshi Ginger", "৫০০ গ্রাম", ProductCategory.moshla, Decimal("79"), None),
    ("কাঁচা মরিচ", "Green Chilli", "২৫০ গ্রাম", ProductCategory.moshla, Decimal("29"), "https://chaldal.com/green-chilli"),
    ("কাঁচা মরিচ (ছোট)", "Green Chilli Small", "১০০ গ্রাম", ProductCategory.moshla, Decimal("15"), None),
    ("ধনিয়া পাতা", "Coriander Leaves", "১০০ গ্রাম", ProductCategory.moshla, Decimal("15"), None),
    ("জিরা", "Cumin (Jira)", "১০০ গ্রাম", ProductCategory.moshla, Decimal("79"), None),
    ("হলুদ গুড়া (Radhuni)", "Radhuni Turmeric Powder", "২০০ গ্রাম", ProductCategory.moshla, Decimal("145"), None),
    ("মরিচ গুড়া (Radhuni)", "Radhuni Chilli Powder", "২০০ গ্রাম", ProductCategory.moshla, Decimal("140"), None),
    ("সরিষার তেল (Radhuni)", "Radhuni Mustard Oil", "৫০০ মিলি", ProductCategory.moshla, Decimal("185"), None),
    ("বিরিয়ানি মশলা (Radhuni)", "Radhuni Biryani Masala", "৪০ গ্রাম", ProductCategory.moshla, Decimal("60"), None),
    ("দারুচিনি (Cinnamon)", "Cinnamon Whole", "১০০ গ্রাম", ProductCategory.moshla, Decimal("65"), None),
    ("তেজপাতা", "Bay Leaf (Tejpata)", "১০০ গ্রাম", ProductCategory.moshla, Decimal("35"), None),
    ("লবঙ্গ", "Clove (Lobongo)", "৫০ গ্রাম", ProductCategory.moshla, Decimal("89"), None),
    ("শুকনো মরিচ", "Dried Chillies", "১০০ গ্রাম", ProductCategory.moshla, Decimal("49"), None),
    ("কিশমিশ", "Raisins (Kishmish)", "১০০ গ্রাম", ProductCategory.moshla, Decimal("89"), None),
    ("সবুজ ক্যাপসিকাম", "Green Capsicum", "৩০০ গ্রাম", ProductCategory.sobji, Decimal("49"), None),
    ("কলা (সাগর)", "Banana Sagor", "৪ পিস", ProductCategory.fol, Decimal("55"), None),
    ("কলা (চম্পা)", "Banana Chompa", "৪ পিস", ProductCategory.fol, Decimal("29"), None),
    ("পেয়ারা (প্রিমিয়াম)", "Guava Premium", "১ কেজি", ProductCategory.fol, Decimal("129"), None),
    ("মাল্টা", "Malta", "১ কেজি", ProductCategory.fol, Decimal("339"), None),
    ("লম্বা লেবু", "Long Lemon", "৪ পিস", ProductCategory.fol, Decimal("75"), None),
    ("গোল লেবু", "Round Lemon", "৪ পিস", ProductCategory.fol, Decimal("75"), None),
    ("সবুজ আঙুর", "Green Grapes", "২৫০ গ্রাম", ProductCategory.fol, Decimal("109"), None),
    ("মিনিকেট চাল (বয়েলড)", "Miniket Rice Premium Boiled", "৫ কেজি", ProductCategory.dal_chal, Decimal("429"), "https://chaldal.com/miniket-rice-premium-boiled"),
    ("নাজিরশাইল চাল", "Nazirshail Rice Premium", "৫ কেজি", ProductCategory.dal_chal, Decimal("449"), None),
    ("চিনিগুড়া চাল (Chashi)", "Chashi Aromatic Chinigura Rice", "২ কেজি", ProductCategory.dal_chal, Decimal("340"), None),
    ("চিনিগুড়া চাল (প্রিমিয়াম)", "Chinigura Rice Premium", "১ কেজি", ProductCategory.dal_chal, Decimal("139"), None),
    ("কাটারি আতপ চাল", "Katari Atop Rice", "২৫ কেজি", ProductCategory.dal_chal, Decimal("2229"), None),
    ("মসুর ডাল (আমদানি)", "Moshur Dal Imported", "১ কেজি", ProductCategory.dal_chal, Decimal("99"), None),
    ("মসুর ডাল (দেশি)", "Moshur Dal Deshi", "১ কেজি", ProductCategory.dal_chal, Decimal("165"), None),
    ("মুগ ডাল", "Mug Dal", "৫০০ গ্রাম", ProductCategory.dal_chal, Decimal("89"), None),
    ("বুট ডাল", "Boot Dal", "৫০০ গ্রাম", ProductCategory.dal_chal, Decimal("59"), None),
    ("খেসারি ডাল", "Kheshari Dal", "৫০০ গ্রাম", ProductCategory.dal_chal, Decimal("75"), None),
    ("ডুবলি বুট", "Dubli Boot", "৫০০ গ্রাম", ProductCategory.dal_chal, Decimal("39"), None),
    ("ছোলা (Chick Peas)", "Chola Boot Chick Peas", "১ কেজি", ProductCategory.dal_chal, Decimal("95"), None),
    ("বেসন (Chickpea Flour)", "Chickpea Flour Boot Beshon", "৫০০ গ্রাম", ProductCategory.dal_chal, Decimal("69"), None),
    ("আটা (Fresh)", "Fresh Flour Atta", "২ কেজি", ProductCategory.dal_chal, Decimal("130"), None),
    ("আটা (Teer)", "Teer Flour Atta", "২ কেজি", ProductCategory.dal_chal, Decimal("130"), None),
    ("ময়দা (Fresh)", "Fresh White Flour Maida", "২ কেজি", ProductCategory.dal_chal, Decimal("140"), None),
    ("ময়দা (Teer)", "Teer White Flour Maida", "২ কেজি", ProductCategory.dal_chal, Decimal("140"), None),
    ("চিড়া (Pran)", "Pran Flattened Rice Chira", "৫০০ গ্রাম", ProductCategory.dal_chal, Decimal("70"), None),
    ("মুড়ি (Pran)", "Pran Puffed Rice Muri", "৫০০ গ্রাম", ProductCategory.dal_chal, Decimal("75"), None),
    ("আড়ং পাস্তুরাইজড দুধ", "Aarong Dairy Pasteurized Milk", "১ লিটার", ProductCategory.dairy, Decimal("105"), "https://chaldal.com/aarong-dairy-pasteurized-milk"),
    ("আড়ং টক দই", "Aarong Dairy Sour Curd", "৫০০ গ্রাম", ProductCategory.dairy, Decimal("120"), None),
    ("Starship মিল্ক পাউডার", "Starship Full Cream Milk Powder", "৫০০ গ্রাম", ProductCategory.dairy, Decimal("375"), None),
    ("চিনি (Fresh)", "Fresh Refined Sugar", "১ কেজি", ProductCategory.others, Decimal("105"), None),
    ("চিনি (Teer)", "Teer Sugar", "১ কেজি", ProductCategory.others, Decimal("105"), None),
    ("লবণ (ACI)", "ACI Pure Salt", "১ কেজি", ProductCategory.others, Decimal("42"), None),
    ("লবণ (Fresh Super Premium)", "Fresh Super Premium Salt", "১ কেজি", ProductCategory.others, Decimal("42"), None),
    ("তাতা চা", "Tata Tea Premium", "৪০০ গ্রাম", ProductCategory.others, Decimal("149"), None),
    ("ভিম বার (ছোট)", "Vim Dishwashing Bar Small", "১২৫ গ্রাম", ProductCategory.others, Decimal("15"), None),
    ("ভিম বার (বড়)", "Vim Dishwashing Bar Large", "৩০০ গ্রাম", ProductCategory.others, Decimal("40"), None),
    ("ভিম লিকুইড পাউচ", "Vim Dishwashing Liquid Pouch", "২০০ মিলি", ProductCategory.others, Decimal("50"), None),
    ("Wheel লন্ড্রি বার", "Wheel Washing Laundry Bar", "১২৫ গ্রাম", ProductCategory.others, Decimal("30"), None),
    ("Wheel ওয়াশিং পাউডার (৫০০গ্রাম)", "Wheel Washing Powder 500g", "৫০০ গ্রাম", ProductCategory.others, Decimal("75"), None),
    ("Wheel ওয়াশিং পাউডার (১কেজি)", "Wheel Washing Powder 1kg", "১ কেজি", ProductCategory.others, Decimal("145"), None),
    ("Wheel ওয়াশিং পাউডার (২কেজি)", "Wheel Washing Powder 2kg", "২ কেজি", ProductCategory.others, Decimal("260"), None),
    ("Rin ডিটারজেন্ট পাউডার", "Rin Advanced Detergent Powder", "১ কেজি", ProductCategory.others, Decimal("185"), None),
    ("Partex টয়লেট টিস্যু", "Partex Cleen Toilet Tissue", "৪ পিস", ProductCategory.others, Decimal("95"), None),
    ("Partex হ্যান্ড টাওয়েল", "Partex Cleen Hand Towel", "পিস", ProductCategory.others, Decimal("85"), None),
    ("Bashundhara টয়লেট টিস্যু", "Bashundhara Toilet Tissue", "৪ পিস", ProductCategory.others, Decimal("100"), None),
    ("Bashundhara পেপার ন্যাপকিন", "Bashundhara Paper Napkins", "১০০ পিস", ProductCategory.others, Decimal("75"), None),
    ("বানৌল লাচ্ছা সেমাই", "Banoful Lashcha Shemai", "২০০ গ্রাম", ProductCategory.others, Decimal("50"), None),
    ("ভার্মিসেলি (Kolson Cock)", "Kolson Cock Vermicelli", "২০০ গ্রাম", ProductCategory.others, Decimal("45"), None),
]


def seed():
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()

    try:
        # Admin user
        if not db.query(User).filter(User.email == settings.ADMIN_EMAIL).first():
            admin = User(
                name=           "Admin",
                email=          settings.ADMIN_EMAIL,
                hashed_password=hash_password(settings.ADMIN_PASSWORD),
                role=           UserRole.admin,
                balance=        Decimal("0"),
            )
            db.add(admin)
            print(f"✅ Admin created: {settings.ADMIN_EMAIL}")
        else:
            print("ℹ️  Admin already exists")

        # Products
        added = 0
        for row in PRODUCTS:
            name_bn, name_en, unit, cat, price, url = row
            if not db.query(Product).filter(Product.name_en == name_en).first():
                p = Product(
                    name_bn=name_bn, name_en=name_en,
                    unit=unit, category=cat,
                    current_price=price,
                    chaldal_url=url,
                )
                db.add(p)
                added += 1

        db.commit()
        total = db.query(Product).count()
        print(f"✅ Products: {added} added, {total} total")

    except Exception as e:
        print(f"❌ Seed failed: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
