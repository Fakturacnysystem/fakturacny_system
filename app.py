from flask import Flask, render_template, request, redirect, url_for, send_file
import sqlite3
import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import config

app = Flask(__name__)

DATABASE = "database.db"

def init_db():
    """Vytvorenie databázy, ak neexistuje"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    email TEXT,
                    phone TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    price REAL)''')

    c.execute('''CREATE TABLE IF NOT EXISTS invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER,
                    total_price REAL,
                    date TEXT,
                    status TEXT,
                    FOREIGN KEY(customer_id) REFERENCES customers(id))''')
    conn.commit()
    conn.close()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/customers")
def customers():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT * FROM customers")
    customers_list = c.fetchall()
    conn.close()
    return render_template("customers.html", customers=customers_list)

@app.route("/add_customer", methods=["POST"])
def add_customer():
    name = request.form["name"]
    email = request.form["email"]
    phone = request.form["phone"]
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("INSERT INTO customers (name, email, phone) VALUES (?, ?, ?)",
              (name, email, phone))
    conn.commit()
    conn.close()
    return redirect(url_for("customers"))

@app.route("/generate_invoice/<int:customer_id>")
def generate_invoice(customer_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT * FROM customers WHERE id=?", (customer_id,))
    customer = c.fetchone()
    c.execute("SELECT * FROM products")
    products = c.fetchall()
    conn.close()

    pdf_filename = f"invoice_{customer[1]}.pdf"
    c = canvas.Canvas(pdf_filename, pagesize=A4)
    c.drawString(100, 800, f"Faktúra pre: {customer[1]}")
    c.drawString(100, 780, f"Email: {customer[2]}")
    c.drawString(100, 760, f"Tel: {customer[3]}")
    c.drawString(100, 740, "--------------------------------------------")

    y = 720
    total = 0
    for product in products:
        c.drawString(100, y, f"{product[1]} - {product[2]} €")
        total += product[2]
        y -= 20

    c.drawString(100, y - 20, f"Celková suma: {total} €")
    c.save()

    return send_file(pdf_filename, as_attachment=True)

@app.route("/send_invoice/<int:customer_id>")
def send_invoice(customer_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT * FROM customers WHERE id=?", (customer_id,))
    customer = c.fetchone()
    conn.close()

    pdf_filename = f"invoice_{customer[1]}.pdf"

    msg = MIMEMultipart()
    msg["From"] = config.EMAIL_SENDER
    msg["To"] = customer[2]
    msg["Subject"] = "Vaša faktúra"
    
    attachment = open(pdf_filename, "rb")
    part = MIMEBase("application", "octet-stream")
    part.set_payload(attachment.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={pdf_filename}")
    msg.attach(part)
    
    server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT)
    server.starttls()
    server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
    server.sendmail(config.EMAIL_SENDER, customer[2], msg.as_string())
    server.quit()

    return f"✅ Faktúra pre {customer[1]} bola odoslaná!"

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
