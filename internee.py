from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, abort
from google.cloud import firestore
from datetime import datetime, timedelta, timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os, secrets, math
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = "your_secret_key"
# Don't let browsers/proxies hold a stale copy of ui.js / CSS after a deploy;
# static files are revalidated each load (cheap 304s) instead of cached for hours.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# -------------------------
# Timezone: pin to Pakistan Standard Time (UTC+5, no DST) so date/time
# is correct regardless of the server's timezone (e.g. Render runs in UTC).
# -------------------------
PKT = timezone(timedelta(hours=5))

def now_pk():
    return datetime.now(PKT)

# -------------------------
# Firestore client
# -------------------------
db = firestore.Client.from_service_account_json("traineedata-a1379-8c9c23dd84c8.json")

# -------------------------
# Cloudinary Config
# -------------------------
cloudinary.config(
    cloud_name="dvhlxd4da",
    api_key="245219356924251",
    api_secret="YkrL125ing29yT574dvjqjbjGJE"
)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# -------------------------
# Geofencing helpers
# -------------------------
def haversine_distance(lat1, lon1, lat2, lon2):
    """Distance in meters between two lat/lng points."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def get_company_settings():
    """Return the company geofence settings dict, or None if not configured."""
    doc = db.collection("settings").document("company").get()
    return doc.to_dict() if doc.exists else None

# -------------------------
# Invite Token Storage
# -------------------------
invite_tokens = {}  # {token: expiry_datetime}

# -------------------------
# Login System
# -------------------------
USERNAME = "Ismail"
PASSWORD = "1234567890"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username == USERNAME and password == PASSWORD:
            session["user"] = username
            session["role"] = "admin"
            flash("✅ Logged in successfully!", "success")
            return redirect(url_for("index"))
        else:
            flash("❌ Invalid username or password", "danger")
    return render_template("login.html")

# -------------------------
# Employee Login (phone + password)
# -------------------------
@app.route("/staff_login", methods=["GET", "POST"])
def staff_login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        matched, matched_id = None, None
        for doc in db.collection("aghaz_staff").where("phone", "==", phone).stream():
            d = doc.to_dict()
            if d.get("password") and check_password_hash(d["password"], password):
                matched, matched_id = d, doc.id
                break

        if matched:
            session["user"] = matched.get("name")
            session["role"] = "employee"
            session["staff_id"] = matched_id
            session["cnic"] = matched.get("cnic")
            flash("✅ Logged in successfully!", "success")
            return redirect(url_for("employee_dashboard"))
        else:
            flash("❌ Invalid phone number or password", "danger")
    return render_template("staff_login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -------------------------
# Protect main routes (role-aware)
# -------------------------
PUBLIC_ENDPOINTS = {"login", "staff_login", "logout", "static", "letter_by_name", "invite_form"}
EMPLOYEE_ENDPOINTS = {"employee_dashboard", "mark_attendance", "submit_leave"}

@app.before_request
def require_login():
    endpoint = request.endpoint
    if endpoint is None or endpoint in PUBLIC_ENDPOINTS:
        return
    role = session.get("role")
    if not role:
        return redirect(url_for("login"))
    if endpoint in EMPLOYEE_ENDPOINTS:
        if role != "employee":
            return redirect(url_for("staff_login"))
        return
    # Every other protected endpoint is admin-only
    if role != "admin":
        return redirect(url_for("staff_login"))

# -------------------------
# Home → Show internee list
# -------------------------
@app.route("/")
def index():
    docs = db.collection("aghaz_staff").stream()
    internees = []
    today = now_pk().date()
    is_direct_open = request.referrer is None or request.referrer.endswith(request.host_url)

    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        if is_direct_open:
            try:
                end_date = datetime.strptime(d["end"], "%Y-%m-%d").date()
                days_left = (end_date - today).days
                if days_left in [2, 3]:
                    flash(f"⚠️ {d['name']}'s internship ends in {days_left} days!", "warning")
            except Exception as e:
                print("Date parse error:", e)
        internees.append(d)

    return render_template("index.html", internees=internees)

# -------------------------
# Generate secure invite link (valid 10 min)
# -------------------------
@app.route("/generate_invite")
def generate_invite():
    token = secrets.token_urlsafe(16)
    expiry = datetime.utcnow() + timedelta(hours=24)   # 24 hours validity
    invite_tokens[token] = expiry
    invite_link = url_for("invite_form", token=token, _external=True)
    flash(f"🔗 Invite link (valid 24 hours): {invite_link}", "success")
    return redirect(url_for("index"))


@app.route("/invite/<token>", methods=["GET", "POST"])
def invite_form(token):
    expiry = invite_tokens.get(token)
    if not expiry or datetime.utcnow() > expiry:
        return abort(403, description="❌ This invite link has expired")

    if request.method == "POST":
        cnic = request.form["cnic"].strip()

        # 🔎 Check if CNIC already exists
        existing = db.collection("aghaz_staff").where("cnic", "==", cnic).stream()
        if any(existing):
            flash("⚠️ CNIC already exists! Staff cannot be added again.", "warning")
            return redirect(url_for("invite_form", token=token))

        data = {
            "name": request.form["name"],
            "father": request.form["father"],
            "cnic": cnic,
            "phone": request.form["phone"],
            "gender": request.form["gender"],

            "field": request.form["field"],
            "start": request.form["start"],
            "end": request.form["end"],
        }

        # ✅ Upload to Cloudinary
        image_file = request.files.get("image")
        cnic_file = request.files.get("cnic_image")

        if image_file and allowed_file(image_file.filename):
            upload_result = cloudinary.uploader.upload(image_file, folder="aghaz_staff")
            data["image"] = upload_result["secure_url"]

        if cnic_file and allowed_file(cnic_file.filename):
            upload_result = cloudinary.uploader.upload(cnic_file, folder="aghaz_staff/cnic")
            data["cnic_image"] = upload_result["secure_url"]

        # Employee login password (set by staff on registration)
        password = request.form.get("password", "").strip()
        if password:
            data["password"] = generate_password_hash(password)

        db.collection("aghaz_staff").add(data)

        # Invalidate token after use
        invite_tokens.pop(token, None)

        flash("✅ Staff data added successfully!", "success")
        return redirect(url_for("login"))

    return render_template("invite_form.html")

# -------------------------
# Add internee (Admin only)
# -------------------------
@app.route("/add", methods=["POST"])
def add_internee():
    cnic = request.form["cnic"].strip()

    # 🔎 Check if CNIC already exists
    existing = db.collection("aghaz_staff").where("cnic", "==", cnic).stream()
    if any(existing):
        flash("⚠️ CNIC already exists! Internee cannot be added again.", "warning")
        return redirect(url_for("index"))

    data = {
        "name": request.form["name"],
        "father": request.form["father"],
        "cnic": cnic,
        "phone": request.form["phone"],
        "gender": request.form["gender"],

        "field": request.form["field"],
        "start": request.form["start"],
        "end": request.form["end"],
    }

    # ✅ Upload to Cloudinary
    image_file = request.files.get("image")
    cnic_file = request.files.get("cnic_image")

    if image_file and allowed_file(image_file.filename):
        upload_result = cloudinary.uploader.upload(image_file, folder="aghaz_staff")
        data["image"] = upload_result["secure_url"]

    if cnic_file and allowed_file(cnic_file.filename):
        upload_result = cloudinary.uploader.upload(cnic_file, folder="aghaz_staff/cnic")
        data["cnic_image"] = upload_result["secure_url"]

    # Employee login password (optional, set by admin)
    password = request.form.get("password", "").strip()
    if password:
        data["password"] = generate_password_hash(password)

    db.collection("aghaz_staff").add(data)
    flash("✅ Internee Added Successfully!", "success")
    return redirect(url_for("index"))


# -------------------------
# Edit internee
# -------------------------
@app.route("/edit/<id>", methods=["GET", "POST"])
def edit_internee(id):
    doc_ref = db.collection("aghaz_staff").document(id)
    data = doc_ref.get().to_dict()
    if request.method == "POST":
        update_data = {
            "name": request.form["name"],
            "father": request.form["father"],
            "cnic": request.form["cnic"],
            "phone": request.form["phone"],
            "gender": request.form["gender"],

            "field": request.form["field"],
            "start": request.form["start"],
            "end": request.form["end"]
        }

        # ✅ Upload new image if provided
        image_file = request.files.get("image")
        if image_file and allowed_file(image_file.filename):
            upload_result = cloudinary.uploader.upload(image_file, folder="aghaz_staff")
            update_data["image"] = upload_result["secure_url"]

        # Reset employee login password (optional — leave blank to keep current)
        new_password = request.form.get("password", "").strip()
        if new_password:
            update_data["password"] = generate_password_hash(new_password)

        doc_ref.update(update_data)
        flash("✅ Internee Updated Successfully!", "success")
        return redirect(url_for("index"))

    return render_template("edit.html", internee=data, id=id)

# -------------------------
# Delete internee
# -------------------------
@app.route("/delete/<id>")
def delete_internee(id):
    db.collection("aghaz_staff").document(id).delete()
    flash("❌ Internee Deleted Successfully!", "danger")
    return redirect(url_for("index"))

from reportlab.lib.utils import simpleSplit

# -------------------------
# Generate internship completion letter (PDF)
# -------------------------
@app.route("/letter/<id>", methods=["POST"])
def generate_letter(id):
    internee = db.collection("aghaz_staff").document(id).get().to_dict()
    if not internee:
        flash("❌ Internee not found!", "danger")
        return redirect(url_for("index"))

    letters_dir = "letters"
    os.makedirs(letters_dir, exist_ok=True)
    filepath_pdf = os.path.join(
        letters_dir, f"{internee['name'].replace(' ', '_')}_letter.pdf"
    )

    c = canvas.Canvas(filepath_pdf, pagesize=A4)
    width, height = A4
    margin = 50
    y = height - margin

    # Header Image
    header_path = "static/s4.png"
    if os.path.exists(header_path):
        c.drawImage(
            header_path,
            margin - 55,
            y - 100,
            width=width + 20,
            preserveAspectRatio=True,
            mask="auto",
        )
        y -= 120

    # Stamp Image
    stamp_path = "static/stamp1.png"
    if os.path.exists(stamp_path):
        stamp_width = 250
        stamp_height = 250
        c.drawImage(
            stamp_path,
            width - stamp_width - 20,
            230,
            width=stamp_width,
            height=stamp_height,
            preserveAspectRatio=True,
            mask="auto",
        )

    # Issued On (top left)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, f"ISSUE DATE: {now_pk().strftime('%d-%m-%Y')}")
    y -= 40

    # Title (centered)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, y, "To whom it may concern")
    y -= 50

    # ---------------- Gender-based pronouns ----------------
    gender = internee.get("gender", "").lower()
    if gender == "male":
        relation = "son"
        pronoun_subject = "he"
        pronoun_object = "him"
        pronoun_possessive = "his"
    elif gender == "female":
        relation = "daughter"
        pronoun_subject = "she"
        pronoun_object = "her"
        pronoun_possessive = "her"
    else:
        # default neutral (in case gender not set)
        relation = "son/daughter"
        pronoun_subject = "he/she"
        pronoun_object = "him/her"
        pronoun_possessive = "his/her"

    # Body (wrapped with bold name + field)
    max_width = width - (2 * margin)

    segments = [
        ("normal", "This is to certify that "),
        ("bold", internee['name']),
        ("normal", f", {relation} of {internee['father']}, worked as a "),
        ("bold", internee['field']),
        (
            "normal",
            f" Intern at Aghaz Limited from {internee['start']} to {internee['end']}. "
            f"During the internship, {pronoun_subject} demonstrated good skills with a self-motivated attitude "
            f"to learn new things. We wish {pronoun_object} all the best for {pronoun_possessive} future endeavors."
        ),
    ]

    x, current_y = margin, y
    line_height = 18
    font_size = 12

    for style, text in segments:
        if style == "bold":
            c.setFont("Helvetica-Bold", font_size)
        else:
            c.setFont("Helvetica", font_size)

        words = text.split(" ")
        for word in words:
            word_width = c.stringWidth(word + " ", c._fontname, font_size)
            if x + word_width > width - margin:  # wrap to next line
                current_y -= line_height
                x = margin
            c.drawString(x, current_y, word)
            x += word_width

    y = current_y - 40  # move down after paragraph

    # Warm Regards (left)
    c.setFont("Helvetica", 12)
    c.drawString(margin, y, "Warm Regards,")

    # Footer Image
    footer_path = "static/s3.png"
    if os.path.exists(footer_path):
        c.drawImage(
            footer_path,
            -20,
            -80,
            width=width + 20,
            preserveAspectRatio=True,
            mask="auto",
        )

    c.save()
    return send_file(filepath_pdf, as_attachment=True)



# -------------------------
# Letter by Name (Public)
# -------------------------
@app.route("/letter_by_name", methods=["GET", "POST"])
def letter_by_name():
    if request.method == "POST":
        name = request.form.get("cnic", "").strip()
        if not name:
            flash("❌ Please provide a CNIC!", "danger")
            return redirect(url_for("letter_by_name"))

        docs = db.collection("aghaz_staff").where("cnic", "==", name).stream()
        internee = None
        for doc in docs:
            internee = doc.to_dict()
            break

        if not internee:
            flash(f"❌ No Staff found with CNIC '{name}'", "danger")
            return redirect(url_for("letter_by_name"))

        # ✅ Check internship end date
        try:
            end_date = datetime.strptime(internee["end"], "%Y-%m-%d").date()
            today = now_pk().date()
            if today < end_date:
                flash(f"⚠️ Letter cannot be generated before internship end date ({end_date})", "warning")
                return redirect(url_for("letter_by_name"))
        except Exception:
            flash("❌ Invalid end date format in record", "danger")
            return redirect(url_for("letter_by_name"))

        letters_dir = "letters"
        os.makedirs(letters_dir, exist_ok=True)
        filepath_pdf = os.path.join(
            letters_dir, f"{internee['name'].replace(' ', '_')}_letter.pdf"
        )

        c = canvas.Canvas(filepath_pdf, pagesize=A4)
        width, height = A4
        margin = 50
        y = height - margin

        # ---------------- Header Image ----------------
        header_path = "static/s4.png"
        if os.path.exists(header_path):
            c.drawImage(
                header_path,
                margin - 55,
                y - 100,
                width=width + 20,
                preserveAspectRatio=True,
                mask="auto",
            )
            y -= 120

        # ---------------- Stamp Image ----------------
        stamp_path = "static/stamp1.png"
        if os.path.exists(stamp_path):
            stamp_width = 250
            stamp_height = 250
            c.drawImage(
                stamp_path,
                width - stamp_width - 20,
                230,
                width=stamp_width,
                height=stamp_height,
                preserveAspectRatio=True,
                mask="auto",
            )

        # ---------------- Issued Date ----------------
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, y, f"ISSUE DATE: {now_pk().strftime('%d-%m-%Y')}")
        y -= 40

        # ---------------- Title ----------------
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(width / 2, y, "To whom it may concern")
        y -= 50

        # ---------------- Gender-based pronouns ----------------
        gender = internee.get("gender", "").lower()
        if gender == "male":
            relation = "son"
            pronoun_subject = "he"
            pronoun_object = "him"
            pronoun_possessive = "his"
        elif gender == "female":
            relation = "daughter"
            pronoun_subject = "she"
            pronoun_object = "her"
            pronoun_possessive = "her"
        else:
            relation = "son/daughter"
            pronoun_subject = "he/she"
            pronoun_object = "him/her"
            pronoun_possessive = "his/her"

        # ---------------- Body with Bold Segments ----------------
        max_width = width - (2 * margin)
        segments = [
            ("normal", "This is to certify that "),
            ("bold", internee["name"]),
            ("normal", f", {relation} of {internee['father']}, worked as a "),
            ("bold", internee["field"]),
            (
                "normal",
                f" Intern at Aghaz Limited from {internee['start']} to {internee['end']}. "
                f"During the internship, {pronoun_subject} demonstrated good skills with a self-motivated attitude "
                f"to learn new things. We wish {pronoun_object} all the best for {pronoun_possessive} future endeavors.",
            ),
        ]

        x, current_y = margin, y
        line_height = 18
        font_size = 12

        for style, text in segments:
            if style == "bold":
                c.setFont("Helvetica-Bold", font_size)
            else:
                c.setFont("Helvetica", font_size)

            words = text.split(" ")
            for word in words:
                word_width = c.stringWidth(word + " ", c._fontname, font_size)
                if x + word_width > width - margin:  # wrap to next line
                    current_y -= line_height
                    x = margin
                c.drawString(x, current_y, word)
                x += word_width

        y = current_y - 40  # move down after paragraph

        # ---------------- Warm Regards ----------------
        c.setFont("Helvetica", 12)
        c.drawString(margin, y, "Warm Regards,")
        y -= 36  # gap

        # ---------------- Footer Image ----------------
        footer_path = "static/s3.png"
        if os.path.exists(footer_path):
            c.drawImage(
                footer_path,
                -20,
                -80,
                width=width + 20,
                preserveAspectRatio=True,
                mask="auto",
            )

        c.save()
        return send_file(filepath_pdf, as_attachment=True)

    return render_template("letter_by_name.html")



# -------------------------
# Employee Dashboard
# -------------------------
@app.route("/employee")
def employee_dashboard():
    staff_id = session.get("staff_id")
    cnic = session.get("cnic")
    staff = db.collection("aghaz_staff").document(staff_id).get().to_dict() or {}
    today = now_pk().strftime("%Y-%m-%d")

    # Attendance (single equality filter → no composite index needed)
    all_att = [d.to_dict() for d in db.collection("attendance").where("cnic", "==", cnic).stream()]
    today_att = next((a for a in all_att if a.get("date") == today), None)
    history = sorted(all_att, key=lambda x: x.get("date", ""), reverse=True)

    # Leave requests
    leaves = [d.to_dict() for d in db.collection("leave_requests").where("cnic", "==", cnic).stream()]
    leaves.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)

    settings = get_company_settings()

    return render_template(
        "employee_dashboard.html",
        staff=staff, today_att=today_att, history=history,
        leaves=leaves, settings=settings, today=today,
    )

# -------------------------
# Mark Attendance (geofenced)
# -------------------------
@app.route("/employee/attendance", methods=["POST"])
def mark_attendance():
    cnic = session.get("cnic")
    name = session.get("user")
    staff_id = session.get("staff_id")
    today = now_pk().strftime("%Y-%m-%d")

    settings = get_company_settings()
    if not settings or "lat" not in settings:
        flash("⚠️ Company location is not set yet. Please contact the admin.", "warning")
        return redirect(url_for("employee_dashboard"))

    # Prevent double check-in for the same day
    already = any(
        d.to_dict().get("date") == today
        for d in db.collection("attendance").where("cnic", "==", cnic).stream()
    )
    if already:
        flash("⚠️ Attendance already marked for today.", "warning")
        return redirect(url_for("employee_dashboard"))

    try:
        lat = float(request.form["lat"])
        lng = float(request.form["lng"])
    except (KeyError, ValueError):
        flash("❌ Could not read your location. Enable GPS/location access and try again.", "danger")
        return redirect(url_for("employee_dashboard"))

    radius = float(settings.get("radius", 100))
    distance = haversine_distance(settings["lat"], settings["lng"], lat, lng)
    if distance > radius:
        flash(
            f"❌ You are {int(distance)}m from the office (allowed {int(radius)}m). "
            "Attendance not marked.",
            "danger",
        )
        return redirect(url_for("employee_dashboard"))

    db.collection("attendance").add({
        "cnic": cnic,
        "name": name,
        "staff_id": staff_id,
        "date": today,
        "time": now_pk().strftime("%H:%M:%S"),
        "lat": lat,
        "lng": lng,
        "distance_m": round(distance, 1),
        "status": "Present",
    })
    flash(f"✅ Attendance marked! ({int(distance)}m from office)", "success")
    return redirect(url_for("employee_dashboard"))

# -------------------------
# Submit Leave Request
# -------------------------
@app.route("/employee/leave", methods=["POST"])
def submit_leave():
    db.collection("leave_requests").add({
        "cnic": session.get("cnic"),
        "name": session.get("user"),
        "staff_id": session.get("staff_id"),
        "type": request.form.get("type"),
        "reason": request.form.get("reason"),
        "start_date": request.form.get("start_date"),
        "end_date": request.form.get("end_date"),
        "status": "Pending",
        "submitted_at": now_pk().strftime("%Y-%m-%d %H:%M:%S"),
    })
    flash("✅ Leave request submitted!", "success")
    return redirect(url_for("employee_dashboard"))

# -------------------------
# Admin — View Attendance
# -------------------------
@app.route("/admin/attendance")
def admin_attendance():
    today = now_pk().strftime("%Y-%m-%d")
    # Default to today on first load; an explicit empty ?date= means "all dates"
    date_arg = request.args.get("date")
    date_filter = date_arg.strip() if date_arg is not None else today
    name_filter = request.args.get("name", "").strip()
    records = [d.to_dict() for d in db.collection("attendance").stream()]
    if date_filter:
        records = [r for r in records if r.get("date") == date_filter]
    if name_filter:
        records = [r for r in records if name_filter.lower() in (r.get("name", "") or "").lower()]
    records.sort(key=lambda x: (x.get("date", ""), x.get("time", "")), reverse=True)
    return render_template(
        "admin_attendance.html", records=records,
        date_filter=date_filter, name_filter=name_filter, today=today,
    )

# -------------------------
# Admin — Leave Requests
# -------------------------
@app.route("/admin/leaves")
def admin_leaves():
    today = now_pk().strftime("%Y-%m-%d")
    # Default to requests submitted today; explicit empty ?date= means "all dates"
    date_arg = request.args.get("date")
    date_filter = date_arg.strip() if date_arg is not None else today
    status_filter = request.args.get("status", "").strip()
    type_filter = request.args.get("type", "").strip()
    name_filter = request.args.get("name", "").strip()
    records = []
    for d in db.collection("leave_requests").stream():
        r = d.to_dict()
        r["id"] = d.id
        records.append(r)
    if date_filter:
        records = [r for r in records if (r.get("submitted_at", "")[:10] == date_filter)]
    if status_filter:
        records = [r for r in records if r.get("status") == status_filter]
    if type_filter:
        records = [r for r in records if r.get("type") == type_filter]
    if name_filter:
        records = [r for r in records if name_filter.lower() in (r.get("name", "") or "").lower()]
    records.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
    return render_template(
        "admin_leaves.html", records=records,
        date_filter=date_filter, status_filter=status_filter,
        type_filter=type_filter, name_filter=name_filter, today=today,
    )

@app.route("/admin/leaves/<id>/<action>")
def update_leave(id, action):
    status = "Approved" if action == "approve" else "Rejected"
    db.collection("leave_requests").document(id).update({"status": status})
    flash(f"✅ Leave request {status}.", "success")
    return redirect(url_for("admin_leaves"))

# -------------------------
# Admin — Company Location Settings (geofence)
# -------------------------
@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    if request.method == "POST":
        try:
            data = {
                "lat": float(request.form["lat"]),
                "lng": float(request.form["lng"]),
                "radius": float(request.form["radius"]),
            }
        except (KeyError, ValueError):
            flash("❌ Invalid location values. Please enter valid numbers.", "danger")
            return redirect(url_for("admin_settings"))
        db.collection("settings").document("company").set(data)
        flash("✅ Company location saved!", "success")
        return redirect(url_for("admin_settings"))

    return render_template("admin_settings.html", settings=get_company_settings())

# -------------------------
# Run Server
# -------------------------
from waitress import serve
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    serve(app, host="0.0.0.0", port=port)
