from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import tempfile
from fpdf import FPDF
from PIL import Image, ExifTags
import json
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import unicodedata
import re

# ----------------- FLASK SETUP -----------------
app = Flask(__name__)
CORS(app)

# ----------------- EMAIL CONFIGURATION -----------------
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
EMAIL_ADDRESS = 'bucherincsd@gmail.com'
EMAIL_PASSWORD = 'bthu ukag jwje epwq'
RECIPIENT_EMAILS = ['san.diego@bucherinc.com', 'trafico@bucherinc.com', 'bucherincsd@gmail.com']

# ----------------- FILENAME SANITIZER -----------------
def clean_filename(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    return re.sub(r'[^a-zA-Z0-9_\-\.]', '_', text)

def correct_image_orientation(image):
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == "Orientation":
                break
        exif = image._getexif()
        if exif is not None:
            orientation_value = exif.get(orientation, None)
            if orientation_value == 3:
                image = image.rotate(180, expand=True)
            elif orientation_value == 6:
                image = image.rotate(270, expand=True)
            elif orientation_value == 8:
                image = image.rotate(90, expand=True)
    except Exception as e:
        print(f"EXIF orientation fix failed: {e}")
    return image

class PDF(FPDF):
    def header(self):
        logo_path = os.path.join(os.path.expanduser("~"), "Desktop", "logo", "logo.png")
        if os.path.exists(logo_path):
            self.image(logo_path, x=10, y=8, w=66)
        else:
            print("Logo not found at", logo_path)
        self.set_font("Arial", "B", 15)
        self.cell(80)
        self.cell(0, 10, "Damage Report", ln=True, align="C")
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")

def send_email_with_attachment(pdf_data, pdf_name):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = ", ".join(RECIPIENT_EMAILS)
    msg['Subject'] = f"Damage Report - {pdf_name}"
    
    body = "Good morning,\n\nAttached is the damage report.\n\nBest regards."
    msg.attach(MIMEText(body, 'plain'))

    part = MIMEApplication(pdf_data, _subtype="pdf")
    part.add_header('Content-Disposition', 'attachment', filename=pdf_name)
    msg.attach(part)

    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    server.send_message(msg)
    server.quit()

@app.route('/upload', methods=['POST'])
def upload_files():
    if 'files' not in request.files:
        return jsonify({"error": "No files found"}), 400
    if 'pdf_name' not in request.form or not request.form['pdf_name'].strip():
        return jsonify({"error": "No PDF name provided"}), 400

    raw_name = request.form['pdf_name'].strip()
    pdf_name_clean = clean_filename(raw_name)
    pdf_name = pdf_name_clean + ".pdf"

    with tempfile.TemporaryDirectory() as temp_dir:
        pdf = PDF()
        pdf.set_auto_page_break(auto=True, margin=10)

        # Cover Page
        pdf.add_page()
        current_date = datetime.datetime.now().strftime("%m/%d/%Y")
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, f"PO Number: {pdf_name_clean}", ln=True, align="C")
        pdf.cell(0, 10, f"Date: {current_date}", ln=True, align="C")
        pdf.ln(10)

        # Damage Section
        if 'damage_data' in request.form:
            try:
                damage_data = json.loads(request.form['damage_data'])
                pdf.set_font("Arial", "B", 14)
                pdf.cell(0, 10, "Damage Details:", ln=True)
                pdf.ln(3)

                pdf.set_font("Arial", "", 12)
                for key, data in damage_data.items():
                    if data.get("checked") or data.get("quantity") or data.get("note"):
                        line = f"- {key}"
                        if data.get("note"):
                            line += f": {data['note']}"
                        if data.get("quantity"):
                            line += f" (Qty: {data['quantity']})"
                        pdf.multi_cell(0, 10, line)
                pdf.ln(5)
            except Exception as e:
                return jsonify({"error": f"Failed to parse damage data: {str(e)}"}), 500

        # Image Pages
        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "No valid images uploaded"}), 400

        for file in files:
            image_path = os.path.join(temp_dir, file.filename)
            file.save(image_path)
            try:
                with Image.open(image_path) as image:
                    image = correct_image_orientation(image)
                    fixed_path = os.path.join(temp_dir, file.filename.replace(".jpg", "_fixed.jpg"))
                    image.save(fixed_path)
                    pdf.add_page()
                    pdf.image(fixed_path, x=10, y=10, w=180)
                os.remove(image_path)
                os.remove(fixed_path)
            except Exception as e:
                return jsonify({"error": f"Failed to process image: {str(e)}"}), 500

        # Generate PDF
        pdf_data = pdf.output(dest="S").encode('latin1')

    # Send Email
    try:
        send_email_with_attachment(pdf_data, pdf_name)
    except Exception as e:
        return jsonify({"message": f"PDF generated but failed to send email: {str(e)}"}), 200

    return jsonify({"message": "✅ PDF generated and email sent."}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

