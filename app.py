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

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# ----------------- EMAIL CONFIGURATION -----------------
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
EMAIL_ADDRESS = 'bucherincsd@gmail.com'
# Use your app-specific password for Gmail here.
EMAIL_PASSWORD = 'bthu ukag jwje epwq'
# List of recipients (multiple emails)
RECIPIENT_EMAILS = ['san.diego@bucherinc.com', 'trafico@bucherinc.com']

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

# Custom PDF class with header and footer, with a larger logo
class PDF(FPDF):
    def header(self):
        # Adjust the logo path as needed; here it's assumed to be on your Desktop in the "logo" folder.
        logo_path = os.path.join(os.path.expanduser("~"), "Desktop", "logo", "logo.png")
        if os.path.exists(logo_path):
            # Use width=66 to double the size of the logo.
            self.image(logo_path, x=10, y=8, w=66)
        else:
            print("Logo file not found at", logo_path)
        self.set_font("Arial", "B", 15)
        self.cell(80)
        self.cell(0, 10, "Reporte de Daños", ln=True, align="C")
        self.ln(10)
    
    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Página {self.page_no()}", 0, 0, "C")

def send_email_with_attachment(pdf_data, pdf_name):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = ", ".join(RECIPIENT_EMAILS)
    msg['Subject'] = f"Reporte de Daños - {pdf_name}"
    
    body = "Buen día, adjunto el reporte de daños.\n\nSaludos cordiales."
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

    pdf_name_raw = request.form['pdf_name'].strip()
    pdf_name = pdf_name_raw + ".pdf"
    
    # Use a temporary directory for processing; files will not be stored permanently.
    with tempfile.TemporaryDirectory() as temp_dir:
        pdf = PDF()
        pdf.set_auto_page_break(auto=True, margin=10)
        
        # ----------------- COVER PAGE -----------------
        pdf.add_page()
        current_date = datetime.datetime.now().strftime("%d/%m/%Y")
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, f"PO Number: {pdf_name_raw}", ln=True, align="C")
        pdf.cell(0, 10, f"Fecha: {current_date}", ln=True, align="C")
        pdf.ln(10)
        
        # ----------------- DAMAGE REPORT SECTION -----------------
        if 'damage_data' in request.form:
            try:
                damage_data = json.loads(request.form['damage_data'])
                pdf.set_font("Arial", "B", 14)
                pdf.cell(0, 10, "Detalle de Daños:", ln=True)
                pdf.ln(3)
                
                pdf.set_font("Arial", "", 12)
                translations = {
                    "Damages": "Daños",
                    "Water damage": "Daño por agua",
                    "Broken straps": "Correas rotas",
                    "Other": "Otro"
                }
                for key, data in damage_data.items():
                    # Include the info if the checkbox is checked or if quantity/note is filled out.
                    if data.get("checked") or data.get("quantity") or data.get("note"):
                        translated_key = translations.get(key, key)
                        line = f"- {translated_key}"
                        if translated_key == "Otro" and data.get("note"):
                            line += f": {data['note']}"
                        if data.get("quantity"):
                            line += f" (Cantidad: {data['quantity']})"
                        pdf.multi_cell(0, 10, line)
                pdf.ln(5)
            except Exception as e:
                return jsonify({"error": f"Failed to parse damage data: {str(e)}"}), 500
        
        # ----------------- IMAGES SECTION -----------------
        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "No valid images uploaded"}), 400
        
        for file in files:
            image_path = os.path.join(temp_dir, file.filename)
            file.save(image_path)
            
            try:
                with Image.open(image_path) as image:
                    image = correct_image_orientation(image)
                    corrected_image_path = os.path.join(temp_dir, file.filename.replace(".jpg", "_fixed.jpg"))
                    image.save(corrected_image_path)
                    pdf.add_page()
                    pdf.image(corrected_image_path, x=10, y=10, w=180)
                os.remove(image_path)
                os.remove(corrected_image_path)
            except Exception as e:
                return jsonify({"error": f"Failed to process image: {str(e)}"}), 500
        
        # Generate the PDF in memory (as bytes)
        pdf_data = pdf.output(dest="S").encode('latin1')
    
    try:
        send_email_with_attachment(pdf_data, pdf_name)
    except Exception as e:
        return jsonify({"message": f"PDF generated but failed to send email: {str(e)}"}), 200
    
    return jsonify({"message": f"✅ PDF generated and email sent."}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
