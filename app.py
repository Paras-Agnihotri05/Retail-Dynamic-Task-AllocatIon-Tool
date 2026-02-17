from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
import os
from flask import Flask, render_template, request, redirect, url_for
import smtplib
from email.mime.text import MIMEText
from datetime import date, timedelta
from email.utils import make_msgid
import mimetypes
from email.mime.image import MIMEImage
from email import encoders
from PIL import Image

manager_1_stores = ["Bondi", "Manly", "Cronulla"]
manager_2_stores = ["Townhall", "Wynyard", "Airport"]
manager_1 = "sophie.windenberger"
manager_2 = "kinjal.mehta"
app = Flask(__name__)
MAX_WORK = 50
MAX_WIDTH = 1280            # Resize large images to this width
MAX_ATTACH_SIZE = 2 * 1024 * 1024  # 2 MB max per attachment

# Define tasks
TASKS = [
    {"id": 1, "task": "All Delivery done?", "priority": "High", "team": "Opening & Closing", "to-do": "Complete all delivery"},
    {"id": 2, "task": "Is the store 100% Clean?", "priority": "High", "team": "Opening", "to-do": "Clean all the store floor + facing"},
    {"id": 3, "task": "Are all the fire exits completely free?", "priority": "High", "team": "Mid Day", "to-do": "Make sure both fire exits are clear and accessible"},
    {"id": 4, "task": "Are all price labels visible?", "priority": "High", "team": "Closing", "to-do": "Put out all price labels"},
    {"id": 5, "task": "Have you processed all Click and Collects?", "priority": "Medium", "team": "Mid Day", "to-do": "Manage all Click & Collects"},
    {"id": 6, "task": "Have you processed all returns?", "priority": "Medium", "team": "Closing", "to-do": "Process all returns"},
    {"id": 7, "task": "Has all the Flow been accepted?", "priority": "High", "team": "Opening", "to-do": "Accept all flow"},
    {"id": 8, "task": "Has the stock control been done?", "priority": "Medium", "team": "Closing", "to-do": "Perform stock control"},
    {"id": 9, "task": "Is the store freshness above 9.5?", "priority": "Medium", "team": "Closing", "to-do": "Freshness Inventory"}
]

# Priority order for sorting
PRIORITY_ORDER = [
    "Has all the Flow been accepted?",
    "All Delivery done?",
    "Is the store 100% Clean?",
    "Are all the fire exits completely free?",
    "Are all price labels visible?",
    "Have you processed all returns?",
    "Has the stock control been done?",
    "Is the store freshness above 9.5?",
    "Have you processed all Click and Collects?"
]

# Priority ranking
PRIORITY_RANK = {"High": 0, "Medium": 1}

# Weight calculation
def calculate_task_weight(task, form):
    if task["id"] == 1:  # Delivery
        boxes = int(form.get("delivery_boxes", 0))
        boxes_received = request.form.get("boxes_received", "0")

        return boxes * 5
    elif task["id"] == 2:  # Store clean
        perc = float(form.get("clean_percentage", 100))
        return max(0, 100 - perc) * 3
    elif task["id"] == 3:  # Fire exits
        not_clear = int(form.get("fire_exits", 0))
        return not_clear * 7.5
    elif task["id"] == 4:  # Labels
        perc = float(form.get("label_percentage", 100))
        return max(0, 100 - perc) * 1
    elif task["id"] == 6:  # Returns
        return 1
    elif task["id"] == 7:  # Flow
        return 1
    elif task["id"] == 8:  # Stock control
        count = int(form.get("stock_count", 0))
        return count * 1
    elif task["id"] == 9:  # Freshness
        freshness = float(form.get("freshness", 9.5))
        return max(0, 10 - freshness) * 10
    elif task["id"] == 5:  # Click & Collects
        return 1
    else:
        return 0

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

MAX_WORK = 50

# Your TASKS, PRIORITY_ORDER, PRIORITY_RANK, calculate_task_weight stay the same

@app.route("/", methods=["GET", "POST"])
def checklist():
    if request.method == "POST":
        opening_member = request.form.get("opening_member", "N/A")
        closing_member = request.form.get("closing_member", "N/A")
        store = request.form.get('store')
        
        # --- Determine completed & pending tasks ---
        completed = request.form.getlist("tasks")
        boxes = int(request.form.get("delivery_boxes") or 0)
        boxes_received = int(request.form.get("boxes_received") or 0)   # NEW FIELD
        clean_pct = float(request.form.get("clean_percentage") or 100)
        label_pct = float(request.form.get("label_percentage") or 100)
        stock_count = int(request.form.get("stock_count") or 0)
        freshness = float(request.form.get("freshness") or 10)
        fire_exits = int(request.form.get("fire_exits") or 0)

        # Boxes logic
        if boxes == 0 and "1" not in completed:
            completed.append("1")
        elif boxes > 0 and "1" in completed:
            completed.remove("1")

        pending = []
        for t in TASKS:
            task_done = str(t["id"]) in completed
            if t["id"] == 1 and boxes > 0:
                task_done = False
            elif t["id"] == 2 and clean_pct < 100:
                task_done = False
            elif t["id"] == 3 and fire_exits > 0:
                task_done = False
            elif t["id"] == 4 and label_pct < 100:
                task_done = False
            elif t["id"] == 8 and stock_count > 0:
                task_done = False
            elif t["id"] == 9 and freshness < 9.5:
                task_done = False
            elif t["id"] in [5, 6, 7] and not task_done:
                task_done = False

            if not task_done:
                pending.append(t)

        # Sort pending tasks
        pending.sort(key=lambda t: (PRIORITY_RANK[t["priority"]], PRIORITY_ORDER.index(t["task"])))

        # --- Assign workload ---
        team_workload = {"Opening": 0, "Closing": 0}
        assigned, overload = [], []

        for t in pending:
            weight = calculate_task_weight(t, request.form)
            remaining = weight
            for team in ["Opening", "Closing"]:
                can_assign = min(MAX_WORK - team_workload[team], remaining)
                if can_assign > 0:
                    assigned.append((t, team, can_assign))
                    team_workload[team] += can_assign
                    remaining -= can_assign
                if remaining <= 0:
                    break
            if remaining > 0:
                overload.append((t, remaining))

        # --- Build email body ---
        body_lines = [
            f"Store Summary plus priority for {store} {date.today() + timedelta(days=1)}:",
            f"Opening Team: {opening_member}",
            f"Closing Team: {closing_member}",
            ""
        ]

        if assigned:
            body_lines.append("Assigned Tasks:")
            for i, (t, team, weight) in enumerate(assigned, 1):
                extra_info = ""
                if t["id"] == 1 and boxes:
                    extra_info = f" (Boxes pending: {boxes}, Boxes received: {boxes_received})"  # UPDATED
                elif t["id"] == 2 and clean_pct < 100:
                    extra_info = f" (Cleaned: {clean_pct}%)"
                elif t["id"] == 4 and label_pct < 100:
                    extra_info = f" (Label coverage: {label_pct}%)"
                elif t["id"] == 8 and stock_count:
                    extra_info = f" (Stock Control: {stock_count})"
                elif t["id"] == 9 and freshness < 10:
                    extra_info = f" (Freshness: {freshness})"

                body_lines.append(f"{i}. [{t['priority']}] {t['to-do']} → {team} Team {extra_info}")

        if overload:
            body_lines.append("\n⚠️ Overload Tasks (Manager attention needed):")
            for t, remaining in overload:
                body_lines.append(f"- [{t['priority']}] {t['to-do']} (Extra Weight: {remaining})")

        if not assigned and not overload:
            body_lines = [f"✅ All tasks completed for {date.today()}!"]

        body_text = "\n".join(body_lines)

        # --- Collect checklist images ---
        checklist_images = {"proud_area": [], "need_work_area": [], "back_area": []}
        for field in checklist_images.keys():
            for file in request.files.getlist(field):
                if file and file.filename:
                    filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
                    file.save(filepath)
                    checklist_images[field].append(filepath)

        # --- Determine Manager ---
        if (store in manager_1_stores):
             manager = manager_1
        elif store in manager_2_stores:
            manager = manager_2

        # --- Send daily tasks email ---
        send_email(
            subject=f"Daily Store Operations – Pending Tasks {store}",
            body_text=body_text,
            receivers=[f""],
            images_dict=checklist_images
        )

        # --- Empty spots report ---
        if request.form.get("empty_spots") == "yes":
            metres = request.form.get("metres")
            family = request.form.get("family")
            additional_info = request.form.get("additional_information")
            supply_body = (
                f"Empty Spots Report for {date.today()}:\n"
                f"- Metres affected: {metres}\n"
                f"- Major Family: {family}\n"
                f"- Additional information/suggestions from team mate: {additional_info}\n"
            )

            empty_spots_images = []
            for file in request.files.getlist("empty_spots_images"):
                if file and file.filename:
                    filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
                    file.save(filepath)
                    empty_spots_images.append(filepath)

            send_email(
                subject=f"Empty Spots Report {store}",
                body_text=supply_body,
                receivers=[f""],
                images_dict={"empty_spots": empty_spots_images}
            )

        return redirect(url_for("done"))

    return render_template("checklist.html", tasks=TASKS)


def send_email(subject, body_text, receivers, images_dict):
    sender_email = ""
    password = ''

    msg = MIMEMultipart("related")
    msg["From"] = sender_email
    msg["To"] = ", ".join(receivers)
    msg["Subject"] = subject

    # Alternative part for plain + HTML
    alternative = MIMEMultipart("alternative")
    msg.attach(alternative)
    alternative.attach(MIMEText(body_text, "plain"))

    # Start HTML body
    html_body = "<div style='font-family: Arial, sans-serif; font-size:14px;'>"
    for line in body_text.splitlines():
        html_body += f"<p>{line}</p>"

    # Collect all image CIDs to attach only once
    img_cids = {}

    for section, filepaths in images_dict.items():
        if not filepaths:
            continue
        section_title = {
            "proud_area": "Area(s) we are proud of:",
            "need_work_area": "Area(s) that need work:",
            "back_area": "Back Area:",
            "empty_spots": "Empty Spots Images:"
        }.get(section, section)
        html_body += f"<h3>{section_title}</h3>"

        for filepath in filepaths:
            filepath = compress_image(filepath)
            cid = make_msgid(domain="example.com")[1:-1]
            img_cids[filepath] = cid
            html_body += f'<img src="cid:{cid}" style="max-width:600px;"><br>'

    html_body += "</div>"
    alternative.attach(MIMEText(html_body, "html"))

    # Attach images once
    for filepath, cid in img_cids.items():
        try:
            with open(filepath, "rb") as f:
                img = MIMEImage(f.read())
                img.add_header("Content-ID", f"<{cid}>")
                img.add_header("Content-Disposition", "inline", filename=os.path.basename(filepath))
                msg.attach(img)
        except Exception as e:
            print("Failed to attach image", filepath, e)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receivers, msg.as_string())
        print("Email sent successfully!")
    except Exception as e:
        print("Email send failed:", e)


def compress_image(filepath):
    """Resize + compress image, overwrite the file if smaller."""
    try:
        img = Image.open(filepath)
        img_format = img.format

        # Resize if too wide
        if img.width > MAX_WIDTH:
            ratio = MAX_WIDTH / float(img.width)
            new_height = int(float(img.height) * ratio)
            img = img.resize((MAX_WIDTH, new_height), Image.Resampling.LANCZOS)

        # Always save compressed JPEG/PNG
        compressed_path = filepath
        if img_format.upper() == "JPEG":
            img.save(compressed_path, "JPEG", optimize=True, quality=70)
        else:
            img.save(compressed_path, optimize=True)

        return compressed_path
    except Exception as e:
        print("Compression failed for", filepath, ":", e)
        return filepath

@app.route("/done")
def done():
    return render_template("done.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)), debug=True)

    
