import streamlit as st
import pandas as pd
import io, os, re, random, requests, sys
from datetime import datetime
import qrcode
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

st.set_page_config(page_title="Excise Taxation Vehicle Registration - Hyderabad", layout="wide")

st.title("Excise Taxation Vehicle Registration & Number Plate Section Hyderabad")
st.write("Upload Excel/CSV → Extract vehicle numbers → Generate official PDF with verification ID & QR code.")

# Determine if running on Streamlit Cloud
ON_CLOUD = "streamlit" in sys.modules and os.environ.get("STREAMLIT_SERVER_PORT") is not None

# If local, setup auto-save folder
if not ON_CLOUD:
    SAVE_FOLDER = os.path.join(os.getcwd(), "generated_reports")
    os.makedirs(SAVE_FOLDER, exist_ok=True)

report_date = datetime.today().date()
uploaded_file = st.file_uploader("Upload Excel (.xlsx, .xls) or CSV file", type=["xlsx", "xls", "csv"])

plate_pattern = re.compile(r"[A-Z0-9]{1,4}(?:[ -/][A-Z0-9]{1,4})*", re.IGNORECASE)

def extract_plates_from_series(s: pd.Series):
    plates = []
    for v in s.dropna().astype(str):
        for f in plate_pattern.findall(v):
            cleaned = re.sub(r"\s+", " ", f).strip().upper()
            plates.append(cleaned)
    return pd.Series(plates)

def generate_verification_id():
    year = datetime.now().year
    return f"ETNCH-{year}-{random.randint(0,99999):05d}"

def split_title_two_lines(title):
    mid = len(title)//2
    left_space, right_space = title.rfind(" ",0,mid), title.find(" ",mid)
    split = left_space if left_space!=-1 else (right_space if right_space!=-1 else mid)
    return title[:split].strip(), title[split:].strip()

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith(("xls","xlsx")) else pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        st.stop()

    st.subheader("Raw Preview")
    st.dataframe(df.head(50))

    st.subheader("Extract Vehicle Number Plates")
    columns = ["Auto-detect"] + list(df.columns)
    chosen = st.selectbox("Select column containing vehicle numbers", columns)

    if chosen == "Auto-detect":
        scores = {c: df[c].astype(str).str.contains(r"[A-Z0-9]{2,}").sum() for c in df.columns}
        chosen = max(scores, key=scores.get)
        st.info(f"Auto-detected: {chosen}")

    extracted = extract_plates_from_series(df[chosen])
    for c in [c for c in df.columns if c != chosen]:
        extracted = pd.concat([extracted, extract_plates_from_series(df[c])])
    extracted = extracted.dropna().astype(str).str.strip()
    plates = pd.Series(sorted(extracted.unique()))
    st.write(f"Total unique plates: **{len(plates)}**")
    st.dataframe(pd.DataFrame({"vehicle_number_plate": plates}))

    verification_id = generate_verification_id()
    generated_on = datetime.combine(report_date, datetime.min.time()).strftime("%Y-%m-%d")

    st.markdown("---")
    st.write("Verification ID:", verification_id)

    logo_url = "https://propakistani.pk/wp-content/uploads/2021/09/image_2021-09-07_175929.png"
    logo_img = None
    try:
        resp = requests.get(logo_url, timeout=10)
        if resp.ok:
            logo_img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
    except Exception:
        st.warning("Logo not loaded, continuing without logo.")

    def generate_pdf(plates, title, date, ver_id, logo):
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        W, H = A4
        cols, gap = 4, 25
        L, B, top = 40, 70, 180
        row_h, recs_pg = 12, 140
        total, pages = len(plates), max(1, -(-len(plates)//recs_pg))

        qr_text = (f"Excise, Taxation & Narcotics Control Dept.\nHyderabad, Sindh\n"
                   f"Verification ID: {ver_id}\nDate: {date}\nTotal Plates: {total}")
        qr = qrcode.QRCode(box_size=3, border=2)
        qr.add_data(qr_text); qr.make(fit=True)
        qrim = qr.make_image(fill_color="darkgreen", back_color="white")
        qr_io = io.BytesIO(); qrim.save(qr_io,"PNG"); qr_io.seek(0)
        qr_img = ImageReader(qr_io)
        t1,t2 = split_title_two_lines(title)

        def page(pg, start):
            c.saveState(); c.translate(W/2,H/2); c.rotate(45)
            c.setFont("Helvetica-Bold",40); c.setFillColorRGB(.92,.92,.92)
            c.drawCentredString(0,0,"Verified Copy"); c.restoreState()

            if logo:
                lw, lh = 55, int(55 * (logo.height / logo.width))
                lbuf = io.BytesIO(); logo.save(lbuf, "PNG"); lbuf.seek(0)
                c.drawImage(ImageReader(lbuf), L, H - 60 - lh, width=lw, height=lh, mask="auto")

            c.setFillColor(colors.darkblue); c.setFont("Helvetica-Bold",14)
            c.drawString(L + 95, H - 60, t1); c.drawString(L + 95, H - 78, t2)
            c.setFont("Helvetica",9); c.setFillColor(colors.black)
            c.drawString(L + 95, H - 98, f"Generated on: {date}")
            c.drawString(L + 95, H - 112, f"Verification ID: {ver_id}")
            c.drawImage(qr_img, W - L - 90, H - 140, width=90, height=90, mask="auto")
            c.setFont("Helvetica",9); c.setFillColor(colors.darkblue)
            c.drawRightString(W - L, 30, f"{pg}/{pages}")

            cw = (W - 2 * L - (cols - 1) * gap) / cols
            xpos = [L + i * (cw + gap) for i in range(cols)]
            ypos = [H - top] * cols
            c.setFont("Helvetica",9); c.setFillColor(colors.black)
            alt, ci = False, 0
            for i in range(start, min(start + recs_pg, total)):
                txt = f"{i+1}. {plates.iloc[i]}"
                if alt: c.setFillColorRGB(.96, .96, .96)
                c.rect(xpos[ci]-2, ypos[ci]-row_h+2, cw+4, row_h, fill=alt, stroke=False)
                c.setFillColor(colors.black)
                c.drawString(xpos[ci], ypos[ci], txt)
                ypos[ci] -= row_h; alt = not alt
                if ypos[ci] < B: ci += 1; alt = False
                if ci >= cols: break
            c.setStrokeColor(colors.navy)
            for x in xpos: c.line(x-4, B, x-4, H-top+row_h)
            c.line(L, B-6, xpos[-1]+cw+4, B-6)
            c.setStrokeColor(colors.lightgrey); c.line(L, 50, W-L, 50)
            c.setFont("Helvetica-Oblique",8); c.setFillColor(colors.grey)
            c.drawCentredString(W/2, 40, "Excise, Taxation & Narcotics Control Department, Government of Sindh")
            if pg == pages:
                c.setFont("Helvetica",10); c.setFillColor(colors.black)
                c.drawString(W-260,80,"Approved by: ___________________")

        for pg in range(1, pages + 1):
            page(pg, (pg - 1) * recs_pg)
            if pg < pages: c.showPage()
        c.save(); buf.seek(0)
        return buf.read()

    title = "Excise Taxation Vehicle Registration & Number Plate Section Hyderabad"

    if st.button("📄 Generate & Download PDF"):
        pdf = generate_pdf(plates, title, generated_on, verification_id, logo_img)
        fname = f"Excise_Taxation_Vehicle_List_{generated_on}_{verification_id}.pdf"

        # Auto-save locally only if not on cloud
        if not ON_CLOUD:
            fpath = os.path.join(SAVE_FOLDER, fname)
            with open(fpath, "wb") as f: f.write(pdf)
            st.success(f"✅ PDF auto-saved locally: {fpath}")

        st.download_button("⬇️ Download PDF", data=pdf, file_name=fname, mime="application/pdf")

else:
    st.info("Please upload an Excel or CSV file to begin.")
