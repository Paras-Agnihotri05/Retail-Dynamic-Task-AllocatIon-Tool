from email.mime.multipart import MIMEMultipart
import os
from flask import Flask, render_template, request, redirect, url_for
import smtplib
from email.mime.text import MIMEText
from datetime import date, timedelta
from email.utils import make_msgid
import mimetypes
from email.mime.image import MIMEImage

app = Flask(__name__)
MAX_WORK = 50

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
        completed = request.form.getlist("tasks")
        store = request.form.get('store')
        # --- Determine pending tasks ---
        pending = []
        boxes = int(request.form.get("delivery_boxes") or 0)
        clean_pct = float(request.form.get("clean_percentage") or 100)
        label_pct = float(request.form.get("label_percentage") or 100)
        stock_count = int(request.form.get("stock_count") or 0)
        freshness = float(request.form.get("freshness") or 10)
        fire_exits = int(request.form.get("fire_exits") or 0)

        completed = request.form.getlist("tasks")
        # --- Enforce boxes logic ---
        # If default 0 and checkbox not ticked, tick it
        if boxes == 0 and "1" not in completed:
            completed.append("1")
        # If boxes > 0, ensure checkbox is not ticked
        elif boxes > 0 and "1" in completed:
            completed.remove("1")

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

        # --- Sort pending tasks ---
        pending.sort(key=lambda t: (PRIORITY_RANK[t["priority"]], PRIORITY_ORDER.index(t["task"])))

        # --- Assign workload ---
        team_workload = {"Opening": 0, "Closing": 0}
        team_exceeded = {"Opening": False, "Closing": False}
        assigned = []
        overload = []

        team_workload = {"Opening": 0, "Closing": 0}
        assigned = []
        overload = []

        for t in pending:
            weight = calculate_task_weight(t, request.form)

            # First, try to allocate to Opening
            if team_workload["Opening"] + weight <= MAX_WORK:
                assigned.append((t, "Opening", weight))
                team_workload["Opening"] += weight
            else:
                # Allocate remaining weight to Opening (max till MAX_WORK)
                remaining_opening = max(0, MAX_WORK - team_workload["Opening"])
                if remaining_opening > 0:
                    assigned.append((t, "Opening", remaining_opening))
                    team_workload["Opening"] += remaining_opening

                # Allocate rest to Closing before moving to next task
                remaining_weight = weight - remaining_opening
                if remaining_weight > 0:
                    if team_workload["Closing"] + remaining_weight <= MAX_WORK:
                        assigned.append((t, "Closing", remaining_weight))
                        team_workload["Closing"] += remaining_weight
                    else:
                        # Closing also exceeds MAX_WORK → overload
                        remaining_for_closing = max(0, MAX_WORK - team_workload["Closing"])
                        if remaining_for_closing > 0:
                            assigned.append((t, "Closing", remaining_for_closing))
                            team_workload["Closing"] += remaining_for_closing
                        # Any leftover goes to overload
                        leftover = remaining_weight - remaining_for_closing
                        if leftover > 0:
                            overload.append((t, leftover))

        # --- Build email body ---
        body = f"Store Summary plus priority for {store} {date.today() + timedelta(days=1)}:\n\n"
        body += f"Opening Team: {opening_member}\nClosing Team: {closing_member}\n\n"

        if assigned:
            body += "Assigned Tasks:\n"
            for i, (t, team, weight) in enumerate(assigned, 1):
                extra_info = ""
                if t["id"] == 1 and boxes:
                    extra_info = f" (Boxes pending: {boxes})"
                elif t["id"] == 2 and clean_pct < 100:
                    extra_info = f" (Cleaned: {clean_pct}%)"
                elif t["id"] == 4 and label_pct < 100:
                    extra_info = f" (Label coverage: {label_pct}%)"
                elif t["id"] == 8 and stock_count:
                    extra_info = f" (Stock Control: {stock_count})"
                elif t["id"] == 9 and freshness < 10:
                    extra_info = f" (Freshness: {freshness})"
                
                body += f"{i}. [{t['priority']}] {t['to-do']} → {team} Team (Weight: {weight}){extra_info}\n"


        if overload:
            body += "\n⚠️ Overload Tasks (Manager attention needed):\n"
            for t, team in overload:
                body += f"- [{t['priority']}] {t['to-do']}\n"

        if not assigned and not overload:
            body = f"✅ All tasks completed for {date.today()}!"

        # --- Collect checklist images ---
        checklist_images = []
        for field in ["proud_area", "need_work_area", "back_area"]:
            file = request.files.get(field)
            if file and file.filename:
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
                file.save(filepath)
                checklist_images.append((field, filepath))

        # --- Send daily tasks email ---
        send_email(
            subject=f"Daily Store Operations – Pending Tasks {store}",
            body_text=body,
            # later we will change the recievers to f"{store}.team@decathlon.net
            receivers=["paras.agnihotri05@gmail.com"],
            images=checklist_images
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

            # Collect empty spots images
            empty_spots_images = []
            for file in request.files.getlist("empty_spots_images"):
                if file and file.filename:
                    filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
                    file.save(filepath)
                    empty_spots_images.append((file.filename, filepath))

            send_email(
                subject=f"Empty Spots Report {store}",
                body_text=supply_body,
                receivers=["paras.agnihotri1109@gmail.com"],
                images=empty_spots_images
            )


        return redirect(url_for("done"))

    return render_template("checklist.html", tasks=TASKS)


def send_email(subject, body_text, receivers, images=None):
    import os, mimetypes, smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.image import MIMEImage
    from email.utils import make_msgid

    sender_email = "paras.agnihotri@decathlon.com"

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = ", ".join(receivers)

    alt = MIMEMultipart("alternative")
    msg.attach(alt)

    alt.attach(MIMEText(body_text, "plain"))

    # Start HTML
    html_body = "<br>".join(body_text.split("\n"))

    if images:
        field_titles = {
            "proud_area": "Area(s) we are proud of",
            "need_work_area": "Area(s) that need work",
            "back_area": "Back Area"
        }
        for field, filepath in images:
            if not os.path.exists(filepath):
                print("File not found:", filepath)
                continue
            with open(filepath, "rb") as f:
                img_data = f.read()
            mime_type, _ = mimetypes.guess_type(filepath)
            if not mime_type or not mime_type.startswith("image"):
                continue
            subtype = mime_type.split("/")[1]
            img = MIMEImage(img_data, _subtype=subtype)
            cid = make_msgid(domain="decathlon.com")[1:-1]
            img.add_header("Content-ID", f"<{cid}>")
            img.add_header("Content-Disposition", "inline", filename=os.path.basename(filepath))
            msg.attach(img)

            title = field_titles.get(field, field.replace("_", " ").title())
            html_body += f'<br><b>{title}:</b><br>'
            html_body += f'<img src="cid:{cid}" style="max-width:600px;">'


    alt.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, "eifq ldmh oasc szjf")
        server.send_message(msg)
        print("Email sent successfully to:", receivers)



@app.route("/done")
def done():
    return render_template("done.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)

    