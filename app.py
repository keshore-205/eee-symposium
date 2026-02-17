from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
import mysql.connector, os, io, qrcode
from openpyxl import Workbook
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message

app = Flask(__name__)
app.secret_key = "admin_secret"

# ---------- FOLDERS ----------
UPLOAD_FOLDER = "static/uploads"
QR_FOLDER = "static/qr"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

# ---------- DATABASE FUNCTION (FreeDB) ----------
def get_db():
    return mysql.connector.connect(
        host="sql.freedb.tech",
        user="freedb_kishore",          # ← your DB username
        password="4Wv9wYM@X9Y8$VM",   # ← change this
        database="freedb_symposium_db",# ← your DB name
        port=3306
    )

# ---------- ADMIN ----------
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = generate_password_hash("admin123")

# ================= REGISTRATION =================
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        data = request.form
        payment_method = data.get("payment_method")
        file = request.files.get("payment_proof")
        filename = None

        if payment_method in ["GPay", "PhonePe", "Paytm"]:
            if not file or file.filename == "":
                flash("❌ Payment proof is required", "danger")
                return redirect("/")

        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))

        db = get_db()
        cursor = db.cursor()

        cursor.execute("""
            INSERT INTO registrations
            (student_name, college, reg_no, email, phone, department, year,
             tech_event, nontech_event, payment_method, payment_proof,
             payment_status, attendance)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Pending',0)
        """, (
            data.get("student_name"),
            data.get("college"),
            data.get("reg_no"),
            data.get("email"),
            data.get("number"),
            data.get("department"),
            data.get("year"),
            data.get("tech_event"),
            data.get("nontech_event"),
            payment_method,
            filename
        ))

        db.commit()
        cursor.close()
        db.close()

        return redirect("/success")

    return render_template("index.html")

# ================= SUCCESS =================
@app.route("/success")
def success():
    return render_template("success.html")

# ================= ADMIN LOGIN =================
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if (
            request.form.get("username") == ADMIN_USERNAME and
            check_password_hash(ADMIN_PASSWORD_HASH, request.form.get("password"))
        ):
            session["admin"] = True
            return redirect("/dashboard")

        flash("Invalid admin login", "danger")

    return render_template("admin_login.html")

# ================= DASHBOARD =================
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if not session.get("admin"):
        return redirect("/admin")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    search = request.form.get("search")

    if search:
        cursor.execute(
            "SELECT * FROM registrations WHERE student_name LIKE %s ORDER BY id DESC",
            (f"%{search}%",)
        )
    else:
        cursor.execute("SELECT * FROM registrations ORDER BY id DESC")

    data = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template("admin_dashboard.html", data=data, search=search)

# ================= VERIFY =================
@app.route("/verify/<int:id>")
def verify(id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT student_name, email FROM registrations WHERE id=%s", (id,))
    student = cursor.fetchone()

    cursor.execute(
        "UPDATE registrations SET payment_status='Verified' WHERE id=%s",
        (id,)
    )
    db.commit()

    if student:
        msg = Message(
            subject="Symposium Registration Verified ✅",
            sender=app.config['MAIL_USERNAME'],
            recipients=[student["email"]]
        )

        msg.body = f"""
Hello {student['student_name']},

Your symposium registration has been VERIFIED successfully ✅

Thank you,
Symposium Team
"""
        mail.send(msg)

    cursor.close()
    db.close()

    return redirect(url_for("dashboard"))

# ================= REJECT =================
@app.route("/reject/<int:id>")
def reject(id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT student_name, email FROM registrations WHERE id=%s", (id,))
    student = cursor.fetchone()

    cursor.execute(
        "UPDATE registrations SET payment_status='Rejected' WHERE id=%s",
        (id,)
    )
    db.commit()

    if student:
        msg = Message(
            subject="Symposium Registration Rejected ❌",
            sender=app.config['MAIL_USERNAME'],
            recipients=[student["email"]]
        )

        msg.body = f"""
Hello {student['student_name']},

Your registration was REJECTED ❌

Contact coordinator.

Symposium Team
"""
        mail.send(msg)

    cursor.close()
    db.close()

    return redirect(url_for("dashboard"))

# ================= DELETE =================
@app.route("/delete/<int:id>")
def delete(id):
    if not session.get("admin"):
        return redirect("/admin")

    db = get_db()
    cursor = db.cursor()

    cursor.execute("DELETE FROM registrations WHERE id=%s", (id,))
    db.commit()

    cursor.close()
    db.close()

    flash("Registration deleted", "danger")
    return redirect("/dashboard")

# ================= ATTENDANCE =================
@app.route("/attendance/<int:id>")
def attendance(id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        UPDATE registrations
        SET attendance=1, attendance_time=NOW()
        WHERE id=%s AND attendance=0
    """, (id,))

    db.commit()
    cursor.close()
    db.close()

    return "<h2 style='text-align:center;color:green'>Attendance Marked</h2>"

# ================= EXPORT =================
@app.route("/export")
def export():
    if not session.get("admin"):
        return redirect("/admin")

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT student_name,college,reg_no,email,phone,
               department,year,tech_event,nontech_event,
               payment_method,payment_status,attendance,created_at
        FROM registrations
        ORDER BY id DESC
    """)

    rows = cursor.fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = "Registrations"

    ws.append([
        "Name","College","Reg No","Email","Phone",
        "Dept","Year","Tech","NonTech",
        "Payment","Status","Attendance","Registered At"
    ])

    for r in rows:
        ws.append([
            r[0],r[1],r[2],r[3],r[4],
            r[5],r[6],r[7],r[8],
            r[9],r[10],
            "Present" if r[11]==1 else "Absent",
            r[12]
        ])

    file = io.BytesIO()
    wb.save(file)
    file.seek(0)

    cursor.close()
    db.close()

    return send_file(
        file,
        as_attachment=True,
        download_name="symposium_registrations.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ---------------- EMAIL CONFIG ----------------
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = "eeespartans08@gmail.com"
app.config["MAIL_PASSWORD"] = "tnsb sglw xzbm xekk"

mail = Mail(app)

# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/admin")

# ================= RUN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)
