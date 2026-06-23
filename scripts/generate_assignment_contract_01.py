#!/usr/bin/env python3
"""Generate blank assignment contract PDF (template #1) for DocuSign."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BLANK = "________________________"
BLANK_SHORT = "____________"
BLANK_MEDIUM = "____________________"
BLANK_LONG = "______________________________________________________________________________"

OUTPUT_PATHS = [
    Path(__file__).resolve().parent.parent / "contracts" / "assignment-contract-01.pdf",
    Path(__file__).resolve().parent.parent / "docs" / "contracts" / "assignment-contract-01.pdf",
]


def build_styles():
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=12,
        alignment=TA_LEFT,
        spaceAfter=5,
    )
    bullet = ParagraphStyle(
        "Bullet",
        parent=body,
        leftIndent=24,
        bulletIndent=12,
        spaceAfter=4,
    )
    item = ParagraphStyle(
        "Item",
        parent=body,
        spaceAfter=6,
    )
    return body, bullet, item


def p(text, style):
    return Paragraph(text.replace("\n", "<br/>"), style)


class SpacerFlowable(Flowable):
    def __init__(self, height):
        self.height = height

    def wrap(self, avail_width, avail_height):
        return avail_width, self.height

    def draw(self):
        pass


class UnderlineField(Flowable):
    """Solid write-on line with label beneath."""

    def __init__(self, label, width, line_y=20, height=36):
        self.label = label
        self.width = width
        self.line_y = line_y
        self.height = height

    def wrap(self, avail_width, avail_height):
        self.width = min(self.width, avail_width)
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.75)
        c.line(0, self.line_y, self.width, self.line_y)
        c.setFont("Helvetica", 9)
        c.drawString(0, 4, self.label)


class SigDateRow(Flowable):
    """Signature line + date line on one row, labels beneath each."""

    def __init__(self, sig_label, width, date_label="Date"):
        self.sig_label = sig_label
        self.width = width
        self.date_label = date_label
        self.height = 36
        self.sig_width = width * 0.68
        self.date_gap = 10
        self.date_width = width - self.sig_width - self.date_gap

    def wrap(self, avail_width, avail_height):
        self.width = min(self.width, avail_width)
        self.sig_width = self.width * 0.68
        self.date_width = self.width - self.sig_width - self.date_gap
        return self.width, self.height

    def draw(self):
        c = self.canv
        line_y = 20
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.75)
        c.line(0, line_y, self.sig_width, line_y)
        date_x = self.sig_width + self.date_gap
        c.line(date_x, line_y, date_x + self.date_width, line_y)
        c.setFont("Helvetica", 9)
        c.drawString(0, 4, self.sig_label)
        c.drawString(date_x, 4, self.date_label)


def build_signature_block(col_width):
    left = Table(
        [
            [SigDateRow("Buyer (Assignee) Signature", col_width)],
            [UnderlineField("Print Name", col_width)],
            [SigDateRow("Buyer (Assignee) Signature", col_width)],
        ],
        colWidths=[col_width],
    )
    left.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )

    right = Table(
        [
            [SigDateRow("Assignor", col_width)],
            [UnderlineField("Print Name", col_width)],
            [SpacerFlowable(36)],
        ],
        colWidths=[col_width],
    )
    right.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )

    block = Table([[left, right]], colWidths=[col_width + 0.15 * inch, col_width + 0.15 * inch])
    block.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 14),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ]
        )
    )
    return block


def build_story(body, bullet, item):
    story = []

    story.append(
        p(
            f"1. To submit an offer, please sign and initial all pages of this contract and send to "
            f"{BLANK_LONG}. Once confirmation of offer is received you must deposit earnest money to "
            "the designated title company for your offer and contract to be complete.",
            item,
        )
    )
    story.append(p("2. Escrow company will contact you to provide deposit instructions", item))
    story.append(
        p(
            "3. Buyer understands and agrees that failure to submit earnest money deposit by deadline "
            "voids the purchase of the property mentioned.",
            item,
        )
    )
    story.append(
        p(
            "4. The undersigned agrees that by signing below you agree that you have read, understand, "
            "and have full power and authority to enter into this legal agreement. If you do not "
            "understand this document, please seek legal counsel prior to signing, the undersigned "
            "acknowledges receipt of a copy of this document.",
            item,
        )
    )

    bullets = [
        'There is no financing contingency. This opportunity is for "cash" buyers only. If using a '
        "hard money lender or an IRA, a proof of funds is required at time of acceptance.",
        "All properties are sold As-Is where is. Ensure you verify all facts and estimates through "
        "your own vendors.",
        "This is a legally binding contract. Buyer must have performed <b>ALL</b> due diligence prior "
        "to signing contract. Assignor does not guarantee any walkthroughs of property after this "
        "contract has been signed and prior to completing escrow.",
        "Buyer understands that this contract is <b>non-cancellable</b>. Assignor has the right to "
        "pursue legal action, specific performance and punitive damages to enforce contract. "
        "Sacrificing earnest money deposit does not release buyer from closing on property.",
        "Assignor has an assignable purchase contract on this property. We are investors exploring "
        "the possibility of assigning our purchase contract on this property. Buyer understands that "
        "even though this contract is between Assignor and the buyer, if an assignment is used the "
        "buyer is simply purchasing a contract from Assignor. All deals and offers are subject to "
        "Assignor getting marketable title.",
        "Offer is not considered accepted until signed by Buyer &amp; Assignor.",
    ]
    for text in bullets:
        story.append(p(f"&bull; {text}", bullet))

    story.append(Spacer(1, 4))
    story.append(p("<b>5. THIS LEGALLY BINDING ASSIGNMENT</b> of Contract is made by:", item))
    story.append(p(f"(Seller or &quot;Assignor&quot;) and: {BLANK_LONG}", body))
    story.append(p(f"BUYER: {BLANK_LONG} (Buyer or &quot;Assignee&quot;)", body))
    story.append(p("For the sale or assignment of the property described below:", body))
    story.append(p(f"<b>ADDRESS:</b> {BLANK_LONG}", body))
    story.append(p(f"<b>PURCHASE PRICE:</b> {BLANK_LONG}", body))
    story.append(
        p(
            f"<b>EARNEST MONEY:</b> {BLANK_MEDIUM} Due to Closing Agent/Office Within 48 hours of acceptance",
            body,
        )
    )
    story.append(p(f"<b>CLOSING DATE: On or before:</b> {BLANK_MEDIUM}", body))
    story.append(p(f"<b>CLOSING AGENT/OFFICE:</b> {BLANK_LONG}", body))
    story.append(
        p(
            "6. <b>WHEREAS,</b> Assignor desires to assign, transfer, sell and convey to Assignee all of "
            "Assignor's right, title and interest in, to and under said Real Estate Purchase and Sale "
            "Agreement, and <b>NOW, THEREFORE</b> in consideration Assignee agrees to pay a total amount "
            "of purchase price listed above and other good and valuable considerations, the sufficiency "
            "of which is hereby acknowledged, Assignor has assigned, transferred, sold and conveyed unto "
            "Assignee all of Assignor's right, title, and interest to their Real Estate Purchase and "
            "Sale Agreement. Assignor is to receive their compensation at closing in the form of "
            "assignment fee.",
            item,
        )
    )
    story.append(PageBreak())
    story.append(
        p(
            "7. <b>EARNEST MONEY:</b> Assignee is to pay an Earnest Money Deposit as specified above by "
            "way of <b>non-refundable</b> check, money order or wire transfer made payable to designated "
            "title company. Deposit money will be credited to the final sales price at time of closing. "
            "Deposit will be returned to Assignee upon Assignor default or inability to close. Deposit "
            "will be released to Assignor upon Assignee Default or inability to close, and Assignee/Buyer "
            "gives express consent to release funds to Assignor upon default or cancellation without a "
            "signed release of escrow agreement. This property will still be marketed to other buyers "
            "until deposit is received by escrow. If another buyer places deposit, this contract is null "
            "or void. If this agreement is executed as designated, Assignee hereby releases Assignor from "
            "any and all liability and specific performance, to include any cost incurred by Assignee.",
            item,
        )
    )
    story.append(
        p(
            "8. <b>ATTORNEY FEES AND PROVISION:</b> In the event of litigation arising from breach of this "
            "agreement, or the services provided under this agreement, the prevailing party shall be "
            "entitled to recover from the non-prevailing party all reasonable cost including staff time, "
            "court cost, attorney's fees and all other related expenses incurred in such litigation "
            "including the enforcement of any resulting judgement.",
            item,
        )
    )
    story.append(
        p(
            "9. <b>TIME IS OF THE ESSENCE:</b> Buyer agrees to comply with all deadlines and complete the "
            "purchase of the property on or before the close date. Assignee agrees to allow Assignor to "
            "keep a sign in the front yard of property for up to 30 days after closing as reciprocal "
            "marketing. This Assignment contract is non-assignable without express written consent of "
            "<b>ASSIGNOR</b>. No changes to be made to purchase contract without express written consent "
            "of <b>ASSIGNEE</b>.",
            item,
        )
    )
    story.append(
        p(
            "10. <b>ASSIGNMENT OF DUTIES:</b> Assignee hereby assumes all of Assignor's duties and "
            "obligations under said contract for The Sale &amp; Purchase of Real Estate. Assignee agrees "
            "to perform all covenants, conditions and obligations required by Assignor under said Agreement "
            "and agree to defend, indemnify and hold Assignor harmless from any liability or obligation "
            "under said Agreement. Assignee further agrees to hold Assignor harmless from any deficiency "
            "or defect in the legality or enforceability of the terms of said agreement.",
            item,
        )
    )
    story.append(
        p(
            "11. <b>DISCLOSURE:</b> A valid purchase and sale agreement was signed with the seller(s) of "
            "the property. Assignee agrees and understands that Assignor is not acting as a real estate "
            "broker/agent in this transaction and is not representing either party, but rather acting as a "
            "principal in selling their interest in the above referenced contract to Assignee.",
            item,
        )
    )
    story.append(
        p(
            "12. Buyer will have a 5-day feasibility period from effective date for due diligence to "
            "complete a wildlife assessment, at Buyer's expense.",
            item,
        )
    )
    story.append(
        p(
            "13. Buyer to pay for Owner's Policy and Charges and charges for closing services related to "
            "Buyer's lender's policy, endorsements and loan closing.",
            item,
        )
    )
    story.append(
        p(
            "14. <b>THIS IS INTENDED TO BE A LEGALLY BINDING CONTRACT. IF NOT FULLY UNDERSTOOD, SEEK THE "
            "ADVICE OF AN ATTORNEY PRIOR TO SIGNING.</b>",
            item,
        )
    )

    story.append(Spacer(1, 14))
    story.append(build_signature_block(3.1 * inch))
    return story


def main():
    for path in OUTPUT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)

    body, bullet, item = build_styles()
    story = build_story(body, bullet, item)

    for out in OUTPUT_PATHS:
        doc = SimpleDocTemplate(
            str(out),
            pagesize=letter,
            leftMargin=0.85 * inch,
            rightMargin=0.85 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
            title="Assignment of Contract",
            author="Land Flip Dashboard",
        )
        doc.build(list(story))
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
