"""
create_sample_pdf.py — Generate a sample eComBot PDF for Day 06 RAG testing
=============================================================================
This script creates data/ecom_faq.pdf — a realistic e-commerce FAQ document
that can be indexed by src/rag/embed_catalog.py.

Requirements:
    pip install fpdf2

Usage:
    python scripts/create_sample_pdf.py

The generated PDF is placed at data/ecom_faq.pdf relative to the project root.
After running this script, rebuild the ChromaDB index:
    python src/rag/embed_catalog.py --reset
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _ROOT / "data"

def main() -> None:
    try:
        from fpdf import FPDF
    except ImportError:
        print("fpdf2 is required. Install it with:  pip install fpdf2")
        sys.exit(1)

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _DATA_DIR / "ecom_faq.pdf"

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(20, 20, 20)

    # ── Title page ────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(0, 20, "eComBot Store", ln=True, align="C")
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Customer Support FAQ", ln=True, align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "Version 1.0  |  Electronics E-Commerce Support Guide", ln=True, align="C")
    pdf.ln(10)

    # ── Helper ─────────────────────────────────────────────────────────────
    def heading(title: str) -> None:
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(0, 8, title, ln=True, fill=True)
        pdf.ln(2)

    def body(text: str) -> None:
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, text)
        pdf.ln(4)

    # ── Page 2: Returns & Shipping ─────────────────────────────────────────
    pdf.add_page()
    heading("Returns Policy")
    body(
        "You may return most items within 30 days of delivery for a full refund. "
        "Items must be in their original condition and original packaging. "
        "Opened televisions and large appliances are accepted within 14 days if undamaged.\n\n"
        "To start a return, contact our support team with your order ID and the reason "
        "for return. Refunds are processed within 5-7 business days after we receive the item.\n\n"
        "Return shipping is free for defective or incorrectly shipped items. "
        "For change-of-mind returns, the customer is responsible for return shipping costs.\n\n"
        "Digital downloads and gift cards are non-refundable once redeemed."
    )

    heading("Shipping Options")
    body(
        "Standard Shipping: 3-5 business days. Free on orders over $50.\n"
        "Express Shipping: 1-2 business days. Available for $9.99.\n"
        "Overnight Delivery: Available in select metro areas for $19.99.\n"
        "Oversized Items (TVs, large appliances): Free kerbside delivery within 7-10 business days.\n"
        "Same-Day Delivery: Available for select products in major cities. "
        "Orders must be placed before 2pm local time.\n\n"
        "Once your order ships, you will receive a tracking number by email. "
        "If tracking shows 'delivered' but you have not received the package, "
        "wait 24 hours and then contact support with your order ID."
    )

    # ── Page 3: Orders & Cancellation ─────────────────────────────────────
    pdf.add_page()
    heading("Order Cancellation")
    body(
        "You can cancel an order at any time before it ships by contacting support "
        "or using the 'Cancel Order' button in your account page.\n\n"
        "Orders typically ship within 1-2 business days of placement. "
        "Once an order has shipped, it cannot be cancelled — you must wait for delivery "
        "and then initiate a return.\n\n"
        "Refunds for cancelled orders are processed within 3-5 business days to the "
        "original payment method.\n\n"
        "Digital downloads and gift cards cannot be cancelled once redeemed."
    )

    heading("Order Tracking")
    body(
        "After your order ships, you will receive an email with a tracking number. "
        "Use this number on our website or the carrier's website to track your delivery.\n\n"
        "If your tracking shows 'delivered' but you have not received the package, "
        "please wait 24 hours as carriers sometimes update tracking in advance. "
        "If the package is still missing after 24 hours, contact support with your order ID.\n\n"
        "We ship using FedEx, UPS, USPS, and DHL depending on your location and the item size."
    )

    # ── Page 4: Warranty ──────────────────────────────────────────────────
    pdf.add_page()
    heading("Warranty Coverage")
    body(
        "All products include a manufacturer's limited warranty:\n"
        "  - Most electronics: 1 year\n"
        "  - Televisions: 2 years\n"
        "  - Portable SSDs: 3 years\n\n"
        "The warranty covers manufacturing defects and hardware failure under normal use.\n\n"
        "NOT covered:\n"
        "  - Physical damage (drops, cracks, scratches)\n"
        "  - Liquid or water damage\n"
        "  - Accessories such as cables and ear tips\n"
        "  - Consumable parts (mouse feet, keycaps) after 90 days\n"
        "  - Damage from unauthorized modifications or repairs\n\n"
        "To make a warranty claim, contact support with your order ID, product ID, "
        "and a description and photos of the defect. "
        "Approved warranty claims receive a replacement or repair within 7-10 business days."
    )

    # ── Page 5: Payment & Availability ────────────────────────────────────
    pdf.add_page()
    heading("Payment Methods")
    body(
        "We accept:\n"
        "  - Visa, Mastercard, American Express\n"
        "  - PayPal, Apple Pay, Google Pay\n"
        "  - Store credit and gift cards\n"
        "  - Buy Now Pay Later via Klarna and Afterpay (orders over $100)\n\n"
        "All transactions are SSL-encrypted. We do not store full card numbers. "
        "If a payment fails, verify that your billing address matches your card and "
        "that the card has sufficient funds."
    )

    heading("Price Match Guarantee")
    body(
        "We will match the price of any identical in-stock item from a major authorized retailer. "
        "Contact support before placing your order with a link to the competitor's listing.\n\n"
        "Price matches are not available: after purchase, from marketplace sellers (eBay, "
        "Amazon third-party), on refurbished or open-box items, bundle deals, or clearance items.\n\n"
        "If we lower our own price within 7 days of your purchase, contact us for a price adjustment."
    )

    heading("Stock and Availability")
    body(
        "'In Stock' — item is ready to ship within 1-2 business days.\n"
        "'Out of Stock' — temporarily unavailable; click 'Notify Me' for restock alerts.\n"
        "'Pre-Order' — item can be ordered but will not ship until the listed release date.\n\n"
        "If an item goes out of stock after you order, we will notify you and offer "
        "a full refund or the option to wait for restock."
    )

    # ── Page 6: Damaged Items & International ─────────────────────────────
    pdf.add_page()
    heading("Damaged or Defective Items on Arrival")
    body(
        "If your item arrives damaged or defective, contact us within 48 hours of delivery. "
        "Please photograph the damage and the outer packaging before contacting us.\n\n"
        "We will arrange a free return and send a replacement, or issue a full refund — "
        "whichever you prefer. Do not discard the original packaging until the issue is resolved, "
        "as we may need it for a carrier damage claim.\n\n"
        "Items reported as damaged more than 48 hours after delivery are handled under the "
        "standard returns or warranty process instead."
    )

    heading("International Shipping")
    body(
        "We ship to over 50 countries. International delivery typically takes 7-21 business days "
        "depending on destination and customs processing.\n\n"
        "Import duties, taxes, and customs fees are the customer's responsibility and are not "
        "included in our prices. We declare the full value of goods on customs forms and cannot "
        "under-declare for customs purposes.\n\n"
        "Some products cannot be shipped internationally due to regulatory restrictions — "
        "this is indicated on the product page. Contact support for a shipping quote to your "
        "country before ordering."
    )

    pdf.output(str(out_path))
    print(f"PDF created: {out_path}")
    print("Rebuild the ChromaDB index with:  python src/rag/embed_catalog.py --reset")

if __name__ == "__main__":
    main()
