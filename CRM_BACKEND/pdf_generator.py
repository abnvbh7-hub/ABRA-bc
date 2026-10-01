import io
import os
from datetime import datetime
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

def get_rabah_logo(width=130, height=46):
    """
    Safely locates and returns a ReportLab Image object for the Rabah Papyrus logo.
    """
    candidates = [
        os.path.join(os.path.dirname(__file__), "rabah-logo.png"),
        os.path.join(os.path.dirname(__file__), "rabah-logo-blk.png"),
        os.path.join(os.path.dirname(__file__), "..", "CRM-FRONTEND", "public", "rabah-logo.png"),
        os.path.join(os.path.dirname(__file__), "..", "CRM-FRONTEND", "public", "rabah-logo-blk.png"),
        "rabah-logo.png"
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                img = RLImage(p, width=width, height=height)
                img.hAlign = 'LEFT'
                return img
            except Exception as e:
                print(f"[PDF Generator] Could not load logo from {p}: {e}")
    return None

def build_pdf_styles():
    styles = getSampleStyleSheet()
    
    primary_color = colors.HexColor("#1e1b4b")
    accent_color = colors.HexColor("#4338ca")
    emerald_color = colors.HexColor("#059669")
    amber_color = colors.HexColor("#d97706")
    text_dark = colors.HexColor("#0f172a")
    text_muted = colors.HexColor("#64748b")
    bg_light = colors.HexColor("#f8fafc")
    border_color = colors.HexColor("#cbd5e1")

    custom_styles = {
        'primary_color': primary_color,
        'accent_color': accent_color,
        'emerald_color': emerald_color,
        'amber_color': amber_color,
        'text_dark': text_dark,
        'text_muted': text_muted,
        'bg_light': bg_light,
        'border_color': border_color,
        'title': ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontSize=16,
            leading=20,
            textColor=primary_color,
            fontName='Helvetica-Bold'
        ),
        'header_right': ParagraphStyle(
            'HeaderRight',
            parent=styles['Normal'],
            fontSize=8.5,
            leading=13,
            textColor=text_dark,
            alignment=TA_RIGHT
        ),
        'body_bold': ParagraphStyle(
            'BodyBold',
            parent=styles['Normal'],
            fontSize=8.5,
            leading=12,
            fontName='Helvetica-Bold',
            textColor=text_dark
        ),
        'body': ParagraphStyle(
            'BodyStyle',
            parent=styles['Normal'],
            fontSize=8.5,
            leading=12,
            textColor=text_dark
        ),
        'body_muted': ParagraphStyle(
            'BodyMuted',
            parent=styles['Normal'],
            fontSize=8,
            leading=11,
            textColor=text_muted
        ),
        'center_bold': ParagraphStyle(
            'CenterBold',
            parent=styles['Normal'],
            fontSize=9,
            leading=13,
            fontName='Helvetica-Bold',
            textColor=primary_color,
            alignment=TA_CENTER
        ),
        'table_cell_right': ParagraphStyle(
            'TableCellRight',
            parent=styles['Normal'],
            fontSize=8.5,
            leading=12,
            alignment=TA_RIGHT,
            textColor=text_dark
        ),
        'table_cell_right_bold': ParagraphStyle(
            'TableCellRightBold',
            parent=styles['Normal'],
            fontSize=8.5,
            leading=12,
            fontName='Helvetica-Bold',
            alignment=TA_RIGHT,
            textColor=text_dark
        )
    }
    return custom_styles


def generate_quotation_pdf(quote_data: dict) -> bytes:
    """
    Generates an official, highly detailed Quotation PDF for Rabah Papyrus CRM.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=32,
        leftMargin=32,
        topMargin=28,
        bottomMargin=28
    )

    st = build_pdf_styles()
    story = []

    # 1. Top Header with Logo & Company Info + Document Meta
    logo_img = get_rabah_logo(width=135, height=48)
    company_text = """
    <b><font size="11" color="#1e1b4b">RABAH PAPYRUS</font></b><br/>
    <font size="7.5" color="#64748b">Manufacturer of Premium Paper Bags & Hygiene Products</font><br/>
    <font size="7.5" color="#64748b">19-148/1, Anakapalli Rd, Gurrampalem, Pendurthi, Visakhapatnam - 531173<br/>
    <b>GSTIN:</b> 37AAECR1234F1Z5 | <b>Phone:</b> +91 79890 98789<br/>
    <b>Email:</b> sales@rabahpapyrus.com | <b>Web:</b> www.rabahpapyrus.com</font>
    """

    quote_no = quote_data.get("quote_number", f"QUO-{quote_data.get('lead_id', '000')}")
    quote_date = quote_data.get("date", datetime.now().strftime("%d-%b-%Y"))

    doc_meta = f"""
    <b><font size="13" color="#4338ca">COMMERCIAL QUOTATION</font></b><br/>
    <b>Quotation No:</b> {quote_no}<br/>
    <b>Date of Issue:</b> {quote_date}<br/>
    <b>Valid Until:</b> 15 Days from Date<br/>
    <b>Sales Executive:</b> {quote_data.get('sales_rep') or 'Sales Desk'}
    """

    left_cell = [logo_img, Spacer(1, 4), Paragraph(company_text, st['body'])] if logo_img else [Paragraph(company_text, st['body'])]

    header_table = Table(
        [[left_cell, Paragraph(doc_meta, st['header_right'])]],
        colWidths=[330, 200]
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=1.5, color=st['accent_color'], spaceBefore=2, spaceAfter=10))

    # 2. Client & Assignment Details
    cust_name = quote_data.get("customer_name") or quote_data.get("contact_person") or "Valued Customer"
    company_name = quote_data.get("company_name") or "-"
    phone = quote_data.get("phone") or "-"
    email = quote_data.get("email") or "-"
    address = quote_data.get("address") or quote_data.get("location") or "Client Location"

    cust_block = f"""
    <b><font color="#1e1b4b">QUOTATION PREPARED FOR:</font></b><br/>
    <b>Client Name:</b> {cust_name}<br/>
    <b>Company / Firm:</b> {company_name}<br/>
    <b>Contact Phone:</b> {phone}<br/>
    <b>Email Address:</b> {email}<br/>
    <b>Delivery Location:</b> {address}
    """

    delivery_est = quote_data.get("expected_delivery") or quote_data.get("expected_delivery_date") or "~3-4 Days (In Stock) / ~6-7 Days (Production)"

    terms_summary = f"""
    <b><font color="#1e1b4b">ORDER & FULFILLMENT SUMMARY:</font></b><br/>
    <b>Delivery Timeline:</b> {delivery_est}<br/>
    <b>Payment Terms:</b> 50% Advance, Balance on Dispatch<br/>
    <b>Dispatch Mode:</b> Safe Cargo Transport / Logistics<br/>
    <b>Status:</b> Official Price Proposal
    """

    info_table = Table(
        [[Paragraph(cust_block, st['body']), Paragraph(terms_summary, st['body'])]],
        colWidths=[310, 220]
    )
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), st['bg_light']),
        ('BOX', (0, 0), (-1, -1), 0.5, st['border_color']),
        ('PADDING', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 10))

    # 3. Product Specifications Header
    story.append(Paragraph("<b>Itemized Specifications & Price Breakdown</b>", ParagraphStyle('SubHeading', parent=st['title'], fontSize=10, leading=13)))
    story.append(Spacer(1, 4))

    prod_type = quote_data.get("product_type") or "Custom Paper Bags"
    size = quote_data.get("size") or "-"
    gsm = f"{quote_data.get('gsm')} GSM" if quote_data.get('gsm') else "-"
    color = quote_data.get("color") or "-"
    qty = int(quote_data.get("quantity") or 0)
    base_unit_rate = float(quote_data.get("unit_price") or 0.0)
    color_addon = float(quote_data.get("color_addon") or 0.0)
    effective_rate = base_unit_rate if base_unit_rate > 0 else color_addon
    items_subtotal = effective_rate * qty

    spec_lines = [f"<b>{prod_type}</b>", f"• Size: <b>{size}</b> | GSM: <b>{gsm}</b> | Paper Color: <b>{color}</b>"]
    if quote_data.get("handles") and quote_data.get("handles") != "None":
        spec_lines.append(f"• Handle Style: <b>{quote_data.get('handles')}</b>")
    if quote_data.get("print_color") and quote_data.get("print_color") != "None":
        side_text = f" ({quote_data.get('print_side')})" if quote_data.get('print_side') else ""
        spec_lines.append(f"• Custom Branding / Print: <b>{quote_data.get('print_color')}{side_text}</b>")
    
    spec_html = "<br/>".join(spec_lines)

    table_data = [
        [
            Paragraph("<b>#</b>", st['body_bold']),
            Paragraph("<b>Item Description & Specifications</b>", st['body_bold']),
            Paragraph("<b>Qty</b>", st['table_cell_right_bold']),
            Paragraph("<b>Unit Rate</b>", st['table_cell_right_bold']),
            Paragraph("<b>Amount (₹)</b>", st['table_cell_right_bold'])
        ],
        [
            Paragraph("1", st['body']),
            Paragraph(spec_html, st['body']),
            Paragraph(f"{qty:,}", st['table_cell_right']),
            Paragraph(f"₹ {effective_rate:,.2f}", st['table_cell_right']),
            Paragraph(f"₹ {items_subtotal:,.2f}", st['table_cell_right_bold'])
        ]
    ]

    item_idx = 2
    stereo_count = int(quote_data.get("stereo_count", 0))
    stereo_price = float(quote_data.get("stereo_charge", 0.0))
    if stereo_price > 0 or stereo_count > 0:
        if stereo_price == 0 and stereo_count > 0:
            stereo_price = stereo_count * 1770
        stereo_desc = f"<b>Printing Cylinder Block / Stereo Charge</b><br/><font size='7.5' color='#64748b'>({stereo_count} Cylinder Block{'s' if stereo_count>1 else ''} - One-time tooling & setup cost)</font>"
        table_data.append([
            Paragraph(str(item_idx), st['body']),
            Paragraph(stereo_desc, st['body']),
            Paragraph(f"{stereo_count}", st['table_cell_right']),
            Paragraph(f"₹ {(stereo_price / max(stereo_count, 1)):,.2f}", st['table_cell_right']),
            Paragraph(f"₹ {stereo_price:,.2f}", st['table_cell_right_bold'])
        ])
        item_idx += 1

    transport_charge = float(quote_data.get("transport_charge", 0.0))
    if transport_charge > 0:
        table_data.append([
            Paragraph(str(item_idx), st['body']),
            Paragraph("<b>Freight & Packaging Charges</b>", st['body']),
            Paragraph("1", st['table_cell_right']),
            Paragraph(f"₹ {transport_charge:,.2f}", st['table_cell_right']),
            Paragraph(f"₹ {transport_charge:,.2f}", st['table_cell_right_bold'])
        ])

    items_table = Table(table_data, colWidths=[24, 280, 56, 75, 95])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 0.5, st['border_color']),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, st['border_color']),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 8))

    # 4. Summary Calculation Breakdown Table
    subtotal_no_gst = items_subtotal + stereo_price + transport_charge
    gst_rate = float(quote_data.get("gst_rate", 5.0))
    gst_amount = float(quote_data.get("gst_amount") or (subtotal_no_gst * gst_rate / 100))
    grand_total = float(quote_data.get("grand_total") or (subtotal_no_gst + gst_amount))
    advance_50 = grand_total * 0.50
    balance_50 = grand_total - advance_50

    summary_rows = [
        [Paragraph("Subtotal (Excl. Taxes):", st['body']), Paragraph(f"₹ {subtotal_no_gst:,.2f}", st['table_cell_right_bold'])],
        [Paragraph(f"GST Output ({gst_rate:g}%):", st['body']), Paragraph(f"₹ {gst_amount:,.2f}", st['table_cell_right_bold'])],
        [Paragraph("<b>Grand Total (Incl. GST):</b>", st['body_bold']), Paragraph(f"<b>₹ {grand_total:,.2f}</b>", ParagraphStyle('GT', parent=st['table_cell_right_bold'], fontSize=9.5, textColor=st['accent_color']))],
        [Paragraph("<b>50% Advance Required:</b>", ParagraphStyle('Adv', parent=st['body_bold'], textColor=st['emerald_color'])),
         Paragraph(f"<b>₹ {advance_50:,.2f}</b>", ParagraphStyle('AdvVal', parent=st['table_cell_right_bold'], fontSize=9, textColor=st['emerald_color']))],
        [Paragraph("Balance on Dispatch:", st['body_muted']), Paragraph(f"₹ {balance_50:,.2f}", st['table_cell_right'])]
    ]

    summary_table = Table(summary_rows, colWidths=[150, 110])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('PADDING', (0, 0), (-1, -1), 3.5),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor("#eef2ff")),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor("#ecfdf5")),
        ('BOX', (0, 0), (-1, -1), 0.5, st['border_color']),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, st['border_color']),
    ]))

    custom_notes_text = quote_data.get("custom_note") or quote_data.get("note") or "Standard packaging in 30KG Master Bundles included. Color & print proofs will be shared prior to final cylinder etching."
    notes_box = f"<b>Quotation Notes & Instructions:</b><br/>{custom_notes_text}"

    layout_table = Table(
        [[Paragraph(notes_box, ParagraphStyle('Notes', parent=st['body_muted'], fontSize=7.5, leading=10.5)), summary_table]],
        colWidths=[270, 260]
    )
    layout_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(layout_table)
    story.append(Spacer(1, 10))

    # 5. Bank Account & Payment Instructions
    bank_info = """
    <b><font color="#1e1b4b">BANK PAYMENT DETAILS (FOR NEFT / RTGS / IMPS):</font></b><br/>
    <b>Account Name:</b> RABAH PAPYRUS | <b>Bank:</b> HDFC Bank Limited<br/>
    <b>Account Number:</b> 50200087654321 | <b>IFSC Code:</b> HDFC0001234 | <b>Branch:</b> Pendurthi, Visakhapatnam<br/>
    <b>UPI ID:</b> rabahpapyrus@hdfcbank <i>(Please share payment screenshot with quotation reference)</i>
    """
    bank_table = Table([[Paragraph(bank_info, ParagraphStyle('Bank', parent=st['body'], fontSize=7.5, leading=11))]], colWidths=[530])
    bank_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ('BOX', (0, 0), (-1, -1), 0.5, st['border_color']),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(bank_table)
    story.append(Spacer(1, 8))

    # 6. Terms & Authorized Signature
    terms_text = """
    <b>Terms & Conditions:</b><br/>
    1. <b>Order Confirmation:</b> Production begins upon receipt of 50% advance payment and artwork approval.<br/>
    2. <b>Stereo Charges:</b> One-time block charge. Stereos are retained for future repeat orders without additional block fee.<br/>
    3. <b>Tolerances:</b> Industry standard production tolerance of ±5% quantity applies.<br/>
    4. <b>Validity:</b> This quotation is valid for 15 days from date of issue.
    """
    
    sign_block = """
    <br/><br/>
    <b>For RABAH PAPYRUS</b><br/><br/>
    ____________________________<br/>
    <b>Authorized Signatory</b>
    """

    footer_table = Table(
        [[Paragraph(terms_text, ParagraphStyle('Terms', parent=st['body_muted'], fontSize=7, leading=9.5)),
          Paragraph(sign_block, ParagraphStyle('Sign', parent=st['body'], fontSize=7.5, leading=10.5, alignment=TA_RIGHT))]],
        colWidths=[370, 160]
    )
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(footer_table)

    doc.build(story)
    return buffer.getvalue()


def generate_invoice_pdf(invoice_data: dict) -> bytes:
    """
    Generates an official Tax Invoice PDF for Rabah Papyrus CRM.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=32,
        leftMargin=32,
        topMargin=28,
        bottomMargin=28
    )

    st = build_pdf_styles()
    story = []

    logo_img = get_rabah_logo(width=135, height=48)
    company_text = """
    <b><font size="11" color="#1e1b4b">RABAH PAPYRUS</font></b><br/>
    <font size="7.5" color="#64748b">Manufacturer of Premium Paper Bags & Hygiene Products</font><br/>
    <font size="7.5" color="#64748b">19-148/1, Anakapalli Rd, Gurrampalem, Pendurthi, Visakhapatnam - 531173<br/>
    <b>GSTIN:</b> 37AAECR1234F1Z5 | <b>State:</b> Andhra Pradesh (Code: 37)<br/>
    <b>Phone:</b> +91 79890 98789 | <b>Web:</b> www.rabahpapyrus.com</font>
    """

    inv_no = invoice_data.get("invoice_number") or f"INV-{invoice_data.get('order_id', '000')}"
    inv_date = invoice_data.get("date", datetime.now().strftime("%d-%b-%Y"))
    ord_ref = invoice_data.get("order_number") or f"ORD-{invoice_data.get('order_id', '000')}"

    doc_meta = f"""
    <b><font size="13" color="#059669">TAX INVOICE</font></b><br/>
    <b>Invoice No:</b> {inv_no}<br/>
    <b>Invoice Date:</b> {inv_date}<br/>
    <b>Order Ref:</b> {ord_ref}<br/>
    <b>Payment Status:</b> {invoice_data.get('payment_status', 'PARTIALLY PAID')}
    """

    left_cell = [logo_img, Spacer(1, 4), Paragraph(company_text, st['body'])] if logo_img else [Paragraph(company_text, st['body'])]

    header_table = Table(
        [[left_cell, Paragraph(doc_meta, st['header_right'])]],
        colWidths=[330, 200]
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=1.5, color=st['emerald_color'], spaceBefore=2, spaceAfter=10))

    cust_name = invoice_data.get("customer_name") or invoice_data.get("contact_person") or "Customer"
    company_name = invoice_data.get("company_name") or "-"
    phone = invoice_data.get("phone") or "-"
    email = invoice_data.get("email") or "-"
    address = invoice_data.get("address") or invoice_data.get("location") or "-"
    cust_gstin = invoice_data.get("gst_number") or invoice_data.get("gstin") or "Unregistered / Consumer"

    billed_to = f"""
    <b><font color="#1e1b4b">BILLED TO (BUYER):</font></b><br/>
    <b>Name:</b> {cust_name}<br/>
    <b>Company:</b> {company_name}<br/>
    <b>GSTIN:</b> {cust_gstin}<br/>
    <b>Address:</b> {address}<br/>
    <b>Phone:</b> {phone} | <b>Email:</b> {email}
    """

    dispatch_info = f"""
    <b><font color="#1e1b4b">DISPATCH & TAX DETAILS:</font></b><br/>
    <b>Place of Supply:</b> {invoice_data.get('place_of_supply', 'Andhra Pradesh (37)')}<br/>
    <b>Transport / Carrier:</b> Surface Transport Logistics<br/>
    <b>LR / Docket No:</b> {invoice_data.get('lr_number', 'PENDING')}<br/>
    <b>Reverse Charge:</b> No (Regular GST)
    """

    info_table = Table(
        [[Paragraph(billed_to, st['body']), Paragraph(dispatch_info, st['body'])]],
        colWidths=[310, 220]
    )
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), st['bg_light']),
        ('BOX', (0, 0), (-1, -1), 0.5, st['border_color']),
        ('PADDING', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 10))

    # Items Table
    prod_type = invoice_data.get("product_type") or "Paper Packaging Bags"
    size = invoice_data.get("size") or "-"
    gsm = f"{invoice_data.get('gsm')} GSM" if invoice_data.get('gsm') else "-"
    qty = int(invoice_data.get("quantity") or 0)
    unit_rate = float(invoice_data.get("unit_price") or 0.0)
    items_subtotal = float(invoice_data.get("subtotal") or (unit_rate * qty))

    spec_lines = [f"<b>{prod_type}</b>", f"• Size: {size} | GSM: {gsm}"]
    if invoice_data.get("handles"):
        spec_lines.append(f"• Handles: {invoice_data.get('handles')}")
    if invoice_data.get("print_color"):
        spec_lines.append(f"• Print: {invoice_data.get('print_color')}")
    spec_html = "<br/>".join(spec_lines)

    hsn_code = "4819" if "bag" in prod_type.lower() or "pouch" in prod_type.lower() else "4818"

    table_data = [
        [
            Paragraph("<b>#</b>", st['body_bold']),
            Paragraph("<b>Description of Goods</b>", st['body_bold']),
            Paragraph("<b>HSN</b>", st['center_bold']),
            Paragraph("<b>Qty</b>", st['table_cell_right_bold']),
            Paragraph("<b>Rate (₹)</b>", st['table_cell_right_bold']),
            Paragraph("<b>Amount (₹)</b>", st['table_cell_right_bold'])
        ],
        [
            Paragraph("1", st['body']),
            Paragraph(spec_html, st['body']),
            Paragraph(hsn_code, ParagraphStyle('Hsn', parent=st['body'], alignment=TA_CENTER)),
            Paragraph(f"{qty:,}", st['table_cell_right']),
            Paragraph(f"₹ {unit_rate:,.2f}", st['table_cell_right']),
            Paragraph(f"₹ {items_subtotal:,.2f}", st['table_cell_right_bold'])
        ]
    ]

    item_idx = 2
    stereo_charge = float(invoice_data.get("stereo_charge") or 0.0)
    if stereo_charge > 0:
        table_data.append([
            Paragraph(str(item_idx), st['body']),
            Paragraph("<b>Printing Cylinder / Stereo Tooling Charges</b>", st['body']),
            Paragraph("9988", ParagraphStyle('Hsn', parent=st['body'], alignment=TA_CENTER)),
            Paragraph("1", st['table_cell_right']),
            Paragraph(f"₹ {stereo_charge:,.2f}", st['table_cell_right']),
            Paragraph(f"₹ {stereo_charge:,.2f}", st['table_cell_right_bold'])
        ])
        item_idx += 1

    transport_charge = float(invoice_data.get("transport_charge") or 0.0)
    if transport_charge > 0:
        table_data.append([
            Paragraph(str(item_idx), st['body']),
            Paragraph("<b>Packaging & Freight Charges</b>", st['body']),
            Paragraph("9965", ParagraphStyle('Hsn', parent=st['body'], alignment=TA_CENTER)),
            Paragraph("1", st['table_cell_right']),
            Paragraph(f"₹ {transport_charge:,.2f}", st['table_cell_right']),
            Paragraph(f"₹ {transport_charge:,.2f}", st['table_cell_right_bold'])
        ])

    items_table = Table(table_data, colWidths=[24, 240, 46, 50, 75, 95])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 0.5, st['border_color']),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, st['border_color']),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 8))

    # Summary Table
    taxable_val = items_subtotal + stereo_charge + transport_charge
    gst_rate = float(invoice_data.get("gst_rate", 5.0))
    gst_amount = float(invoice_data.get("gst") or invoice_data.get("gst_amount") or (taxable_val * gst_rate / 100))
    total_amount = float(invoice_data.get("total_amount") or invoice_data.get("grand_total") or (taxable_val + gst_amount))
    advance_received = float(invoice_data.get("advance_received") or 0.0)
    balance_due = max(0.0, total_amount - advance_received)

    summary_rows = [
        [Paragraph("Taxable Subtotal:", st['body']), Paragraph(f"₹ {taxable_val:,.2f}", st['table_cell_right_bold'])],
        [Paragraph(f"GST Output ({gst_rate:g}%):", st['body']), Paragraph(f"₹ {gst_amount:,.2f}", st['table_cell_right_bold'])],
        [Paragraph("<b>Total Invoice Amount:</b>", st['body_bold']), Paragraph(f"<b>₹ {total_amount:,.2f}</b>", ParagraphStyle('GT', parent=st['table_cell_right_bold'], fontSize=9.5, textColor=st['emerald_color']))],
        [Paragraph("Less Advance Received:", st['body']), Paragraph(f"₹ {advance_received:,.2f}", st['table_cell_right'])],
        [Paragraph("<b>Net Balance Due:</b>", ParagraphStyle('Bal', parent=st['body_bold'], textColor=colors.HexColor("#dc2626"))),
         Paragraph(f"<b>₹ {balance_due:,.2f}</b>", ParagraphStyle('BalVal', parent=st['table_cell_right_bold'], fontSize=9, textColor=colors.HexColor("#dc2626")))]
    ]

    summary_table = Table(summary_rows, colWidths=[150, 110])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('PADDING', (0, 0), (-1, -1), 3.5),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor("#ecfdf5")),
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor("#fef2f2") if balance_due > 0 else colors.HexColor("#ecfdf5")),
        ('BOX', (0, 0), (-1, -1), 0.5, st['border_color']),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, st['border_color']),
    ]))

    bank_info = """
    <b>BANK DETAILS FOR REMITTANCE:</b><br/>
    <b>Account Name:</b> RABAH PAPYRUS<br/>
    <b>Account No:</b> 50200087654321 | <b>IFSC:</b> HDFC0001234<br/>
    <b>Bank:</b> HDFC Bank, Pendurthi Branch
    """
    layout_table = Table(
        [[Paragraph(bank_info, ParagraphStyle('Bank', parent=st['body'], fontSize=7.5, leading=11)), summary_table]],
        colWidths=[270, 260]
    )
    layout_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(layout_table)
    story.append(Spacer(1, 10))

    # Declaration & Sign
    declaration = """
    <b>Declaration:</b> We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct.
    """
    sign_block = """
    <br/><br/>
    <b>For RABAH PAPYRUS</b><br/><br/>
    ____________________________<br/>
    <b>Authorized Signatory</b>
    """

    footer_table = Table(
        [[Paragraph(declaration, ParagraphStyle('Decl', parent=st['body_muted'], fontSize=7.5, leading=10)),
          Paragraph(sign_block, ParagraphStyle('Sign', parent=st['body'], fontSize=7.5, leading=10.5, alignment=TA_RIGHT))]],
        colWidths=[370, 160]
    )
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(footer_table)

    doc.build(story)
    return buffer.getvalue()


def generate_reminder_pdf(reminder_data: dict) -> bytes:
    """
    Generates an official Payment & Quotation Follow-up Reminder Note PDF for Rabah Papyrus CRM.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=32,
        leftMargin=32,
        topMargin=28,
        bottomMargin=28
    )

    st = build_pdf_styles()
    story = []

    logo_img = get_rabah_logo(width=135, height=48)
    company_text = """
    <b><font size="11" color="#1e1b4b">RABAH PAPYRUS</font></b><br/>
    <font size="7.5" color="#64748b">Manufacturer of Premium Paper Bags & Hygiene Products</font><br/>
    <font size="7.5" color="#64748b">19-148/1, Anakapalli Rd, Gurrampalem, Pendurthi, Visakhapatnam - 531173<br/>
    <b>Phone:</b> +91 79890 98789 | <b>Email:</b> accounts@rabahpapyrus.com</font>
    """

    ref_no = reminder_data.get("quote_number") or reminder_data.get("deal_name") or f"REF-{reminder_data.get('id', '000')}"
    doc_date = reminder_data.get("date", datetime.now().strftime("%d-%b-%Y"))

    doc_meta = f"""
    <b><font size="13" color="#d97706">PAYMENT & ORDER REMINDER</font></b><br/>
    <b>Notice Date:</b> {doc_date}<br/>
    <b>Reference:</b> {ref_no}<br/>
    <b>Sales Desk:</b> {reminder_data.get('sales_rep') or 'Customer Support'}
    """

    left_cell = [logo_img, Spacer(1, 4), Paragraph(company_text, st['body'])] if logo_img else [Paragraph(company_text, st['body'])]

    header_table = Table(
        [[left_cell, Paragraph(doc_meta, st['header_right'])]],
        colWidths=[330, 200]
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=1.5, color=st['amber_color'], spaceBefore=2, spaceAfter=12))

    cust_name = reminder_data.get("customer_name") or reminder_data.get("contact_person") or "Valued Customer"
    company_name = reminder_data.get("company_name") or "-"
    phone = reminder_data.get("phone") or "-"

    cust_block = f"""
    <b>DEAR {cust_name.upper()} ({company_name}):</b><br/>
    We hope this message finds you well. This is a polite reminder regarding your pending order quotation / outstanding advance payment with <b>Rabah Papyrus</b>.
    """
    story.append(Paragraph(cust_block, st['body']))
    story.append(Spacer(1, 10))

    # Reminder Summary Box
    total_val = float(reminder_data.get("grand_total") or reminder_data.get("deal_value") or 0.0)
    adv_req = float(reminder_data.get("advance_due") or reminder_data.get("advance_50") or (total_val * 0.50))
    prod_type = reminder_data.get("product_type") or "Packaging Bags / Goods"
    qty = reminder_data.get("quantity") or 0

    remind_rows = [
        [Paragraph("<b>Item / Quotation Subject:</b>", st['body_bold']), Paragraph(f"{prod_type} ({qty:,} units)" if qty else prod_type, st['body'])],
        [Paragraph("<b>Total Quoted Value (incl. GST):</b>", st['body_bold']), Paragraph(f"₹ {total_val:,.2f}", st['body_bold'])],
        [Paragraph("<b>Required Advance Payment (50%):</b>", ParagraphStyle('Adv', parent=st['body_bold'], textColor=st['amber_color'])),
         Paragraph(f"<b>₹ {adv_req:,.2f}</b>", ParagraphStyle('AdvVal', parent=st['body_bold'], fontSize=9.5, textColor=st['amber_color']))],
    ]
    remind_table = Table(remind_rows, colWidths=[200, 330])
    remind_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), st['bg_light']),
        ('BOX', (0, 0), (-1, -1), 0.5, st['border_color']),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, st['border_color']),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(remind_table)
    story.append(Spacer(1, 12))

    custom_msg = reminder_data.get("custom_note") or "To ensure priority scheduling in our manufacturing queue and timely dispatch, kindly process the 50% advance payment at your earliest convenience."
    msg_block = f"""
    <b>Message from Sales Desk:</b><br/>
    {custom_msg}<br/><br/>
    <i>Upon payment, please reply with the transaction UTR / screenshot so we can instantly lock your production slot and proceed with plate etching & printing.</i>
    """
    story.append(Paragraph(msg_block, st['body']))
    story.append(Spacer(1, 12))

    # Bank Details Box
    bank_info = """
    <b>BANK PAYMENT DETAILS:</b><br/>
    <b>Account Name:</b> RABAH PAPYRUS<br/>
    <b>Account Number:</b> 50200087654321 | <b>IFSC Code:</b> HDFC0001234<br/>
    <b>Bank:</b> HDFC Bank, Pendurthi Branch, Visakhapatnam | <b>UPI ID:</b> rabahpapyrus@hdfcbank
    """
    bank_table = Table([[Paragraph(bank_info, ParagraphStyle('Bank', parent=st['body'], fontSize=8, leading=12))]], colWidths=[530])
    bank_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#fefce8")),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#fef08a")),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(bank_table)
    story.append(Spacer(1, 16))

    sign_block = """
    <b>Warm Regards,</b><br/>
    <b>Team Rabah Papyrus</b><br/>
    Helpline: +91 79890 98789 | sales@rabahpapyrus.com
    """
    story.append(Paragraph(sign_block, st['body']))

    doc.build(story)
    return buffer.getvalue()
