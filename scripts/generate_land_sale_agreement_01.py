#!/usr/bin/env python3
"""Generate blank Land Sale Agreement PDF (template #1) for DocuSign."""

from pathlib import Path

from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors

BLANK = "________________________"
BLANK_SHORT = "____________"
BLANK_MEDIUM = "____________________"
BLANK_LONG = "______________________________________________________________________________"

OUTPUT_PATHS = [
    Path(__file__).resolve().parent.parent / "contracts" / "land-sale-agreement-01.pdf",
    Path(__file__).resolve().parent.parent / "docs" / "contracts" / "land-sale-agreement-01.pdf",
]


def build_styles():
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=base["Normal"],
        fontName="Times-Roman",
        fontSize=11,
        leading=14,
        alignment=TA_LEFT,
        spaceAfter=6,
    )
    title = ParagraphStyle(
        "Title",
        parent=body,
        fontName="Times-Bold",
        fontSize=14,
        leading=18,
        alignment=TA_CENTER,
        spaceAfter=16,
    )
    sub = ParagraphStyle(
        "SubItem",
        parent=body,
        leftIndent=24,
        spaceAfter=4,
    )
    item = ParagraphStyle(
        "Item",
        parent=body,
        leftIndent=12,
        spaceAfter=6,
    )
    sig = ParagraphStyle(
        "Sig",
        parent=body,
        fontSize=11,
        leading=18,
        spaceAfter=2,
    )
    return body, title, sub, item, sig


def p(text, style):
    return Paragraph(text.replace("\n", "<br/>"), style)


def build_story(body, title, sub, item, sig):
    story = []

    story.append(p("Land Sale Agreement", title))

    header = (
        f"This Contract dated {BLANK_SHORT} in which Buyer: {BLANK_MEDIUM} and/or assigns, "
        f"offers to purchase from Seller(s): {BLANK_MEDIUM} the following described real estate, "
        "together with all improvements thereon and all appurtenant rights, located at:"
    )
    story.append(p(header, body))
    story.append(Spacer(1, 4))
    story.append(p(BLANK_LONG, body))
    story.append(Spacer(1, 10))
    story.append(p("Seller agrees:", body))

    story.append(
        p(
            f"1) The purchase price is to be $ {BLANK_SHORT} paid in full to the seller at closing.",
            item,
        )
    )
    story.append(p("2) The conditions of this Purchase are as follows:", item))
    story.append(
        p(
            'a) Property is sold in "AS IS" Condition with no warranties made by the seller. '
            "Seller will make the Buyer aware of any known facts that affect the value of the property.",
            sub,
        )
    )
    story.append(
        p(
            "b) If buyer is unable to complete purchase for any reason other than unknown issues "
            "during the feasibility study period then the earnest money deposit shall be forfeited "
            "to the seller as total liquidated damages and buyer shall be released from any further "
            "obligation under this contract.",
            sub,
        )
    )
    story.append(
        p(
            "c) If Seller cannot provide clear title or does not allow a feasibility study, Buyer will "
            "be released from any further obligation under this contract; otherwise, Seller promises to "
            "sell under this contract.",
            sub,
        )
    )
    story.append(
        p(
            "d) Buyer will, at Buyer's expense, perform a feasibility study to determine whether the "
            "property is suitable for desired use. The feasibility study period shall last until the "
            "closing date, to be paid for by the Buyer.",
            sub,
        )
    )
    story.append(p(f"e) Closing Agent Located at: {BLANK_MEDIUM}", sub))
    story.append(
        p(
            "f) If the Property must be rezoned, Buyer will, at Buyer's expense, obtain rezoning "
            "from the appropriate government agencies.",
            sub,
        )
    )
    story.append(
        p(
            f"3) In consideration of the sum of $ {BLANK_SHORT} Earnest Money will be deposited by "
            "Buyer and held at the closing attorney's office.",
            item,
        )
    )
    story.append(
        p(
            "4) Taxes to be prorated, any previous year's taxes to be paid by Seller. All attorney "
            "closing fees and customary closing costs shall be PAID BY BUYER.",
            item,
        )
    )
    story.append(
        p(
            f"5) Closing date shall be on or before {BLANK_SHORT} days from the date signed below by "
            "Seller. Seller grants any extension needed to clear title or to complete closing "
            "documentation. Not to exceed an additional 45 days. Title to the above-described real "
            "estate to be conveyed by Warranty Deed or other customary instrument of transfer. Title "
            "is to be free, clear, and unencumbered, free of any county, city, and federal liens. "
            "All liens against the property shall be paid at closing by the seller.",
            item,
        )
    )
    story.append(p(f"6) Additional Terms: {BLANK_LONG}", item))
    story.append(Spacer(1, 28))

    sig_table = Table(
        [
            [
                p(f"Date: {BLANK_SHORT}<br/><br/>Seller: {BLANK_MEDIUM}", sig),
                p(f"Date: {BLANK_SHORT}<br/><br/>Buyer: {BLANK_MEDIUM}", sig),
            ]
        ],
        colWidths=[3.4 * inch, 3.4 * inch],
        hAlign="LEFT",
    )
    sig_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    story.append(sig_table)
    return story


def main():
    for path in OUTPUT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)

    body, title, sub, item, sig = build_styles()
    story = build_story(body, title, sub, item, sig)

    for out in OUTPUT_PATHS:
        doc = SimpleDocTemplate(
            str(out),
            pagesize=letter,
            leftMargin=0.85 * inch,
            rightMargin=0.85 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
            title="Land Sale Agreement",
            author="Land Flip Dashboard",
        )
        doc.build(list(story))
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
