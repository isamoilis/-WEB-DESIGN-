from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# secret key for sessions
app.secret_key = "customertracker123"


def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()

        if user is None:
            error = "Wrong username or password"
        elif user["is_active"] == 0:
            error = "This account has been disabled"
        elif not check_password_hash(user["password_hash"], password):
            error = "Wrong username or password"
        else:
            # login ok, save user in session
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] == "employee":
        return employee_dashboard_page()
    elif session["role"] == "manager":
        return manager_dashboard_page()
    elif session["role"] == "admin":
        return admin_dashboard_page()
    else:
        return "Unknown role, something went wrong"


# employee pages
def employee_dashboard_page():
    employee_id = session["user_id"]
    conn = get_db_connection()

    # customers added by this employee
    customers = conn.execute(
        """SELECT customers.*,
                  (SELECT MAX(contact_date) FROM contacts WHERE contacts.customer_id = customers.id) AS last_contact
           FROM customers
           WHERE created_by = ? AND is_disabled = 0
           ORDER BY customers.id DESC""",
        (employee_id,)
    ).fetchall()

    customers_added = conn.execute(
        "SELECT COUNT(*) FROM customers WHERE created_by = ?", (employee_id,)
    ).fetchone()[0]

    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()

    contacts_week = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE employee_id = ? AND contact_date >= ?",
        (employee_id, seven_days_ago)
    ).fetchone()[0]

    contacts_month = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE employee_id = ? AND contact_date >= ?",
        (employee_id, thirty_days_ago)
    ).fetchone()[0]

    conn.close()

    return render_template(
        "employee_dashboard.html",
        customers=customers,
        customers_added=customers_added,
        contacts_week=contacts_week,
        contacts_month=contacts_month
    )


# manager pages
def manager_dashboard_page():
    conn = get_db_connection()

    # days back for the "no contact" table, from a dropdown on the page
    days = request.args.get("days", "30")
    days = int(days)
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()

    total_customers = conn.execute(
        "SELECT COUNT(*) FROM customers WHERE is_disabled = 0"
    ).fetchone()[0]

    active_leads = conn.execute(
        "SELECT COUNT(*) FROM customers WHERE is_disabled = 0 AND category = 'Leads'"
    ).fetchone()[0]

    # customers with no contact yet, or last contact before the cutoff
    no_contact_customers = conn.execute(
        """SELECT customers.*,
                  (SELECT MAX(contact_date) FROM contacts WHERE contacts.customer_id = customers.id) AS last_contact,
                  (SELECT full_name FROM users WHERE users.id = customers.created_by) AS employee_name
           FROM customers
           WHERE is_disabled = 0
             AND (
                 last_contact IS NULL
                 OR last_contact < ?
             )""",
        (cutoff_date,)
    ).fetchall()

    # customers where nobody ever responded
    never_responded = conn.execute(
        """SELECT customer_id FROM contacts
           GROUP BY customer_id
           HAVING SUM(no_response) = COUNT(*)"""
    ).fetchall()

    contacts_per_employee = conn.execute(
        """SELECT users.full_name, COUNT(contacts.id) AS total
           FROM contacts
           JOIN users ON contacts.employee_id = users.id
           WHERE contacts.contact_date >= ?
           GROUP BY contacts.employee_id
           ORDER BY total DESC""",
        (thirty_days_ago,)
    ).fetchall()

    # biggest number, used for the bar chart (avoid dividing by zero)
    max_contacts = 1
    for row in contacts_per_employee:
        if row["total"] > max_contacts:
            max_contacts = row["total"]

    customers_by_category = conn.execute(
        """SELECT category, COUNT(*) AS total
           FROM customers
           WHERE is_disabled = 0
           GROUP BY category"""
    ).fetchall()

    conn.close()

    return render_template(
        "manager_dashboard.html",
        total_customers=total_customers,
        active_leads=active_leads,
        no_contact_customers=no_contact_customers,
        never_responded_count=len(never_responded),
        contacts_per_employee=contacts_per_employee,
        max_contacts=max_contacts,
        customers_by_category=customers_by_category,
        selected_days=days
    )


# admin pages
def admin_dashboard_page():
    conn = get_db_connection()
    users = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return render_template("admin_dashboard.html", users=users)


@app.route("/user/new", methods=["GET", "POST"])
def new_user():
    if "user_id" not in session or session["role"] != "admin":
        return redirect(url_for("login"))

    error = None

    if request.method == "POST":
        username = request.form["username"]
        full_name = request.form["full_name"]
        role = request.form["role"]
        password = request.form["password"]

        conn = get_db_connection()

        # check if username exists already
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()

        if existing:
            error = "That username is already taken"
            conn.close()
            return render_template("user_form.html", user=None, error=error)

        password_hash = generate_password_hash(password)

        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            (username, password_hash, full_name, role)
        )
        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template("user_form.html", user=None, error=error)


@app.route("/user/<int:user_id>/edit", methods=["GET", "POST"])
def edit_user(user_id):
    if "user_id" not in session or session["role"] != "admin":
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":
        full_name = request.form["full_name"]
        role = request.form["role"]
        new_password = request.form["password"]

        if new_password:
            password_hash = generate_password_hash(new_password)
            conn.execute(
                "UPDATE users SET full_name = ?, role = ?, password_hash = ? WHERE id = ?",
                (full_name, role, password_hash, user_id)
            )
        else:
            conn.execute(
                "UPDATE users SET full_name = ?, role = ? WHERE id = ?",
                (full_name, role, user_id)
            )

        conn.commit()
        conn.close()
        return redirect(url_for("dashboard"))

    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return render_template("user_form.html", user=user, error=None)


@app.route("/user/<int:user_id>/toggle_active", methods=["POST"])
def toggle_user_active(user_id):
    if "user_id" not in session or session["role"] != "admin":
        return redirect(url_for("login"))

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    # flip active status
    if user["is_active"] == 1:
        new_status = 0
    else:
        new_status = 1
    conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, user_id))
    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


@app.route("/customer/new", methods=["GET", "POST"])
def new_customer():
    if "user_id" not in session or session["role"] != "employee":
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        category = request.form["category"]

        conn = get_db_connection()
        conn.execute(
            """INSERT INTO customers (name, email, phone, category, created_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, email, phone, category, session["user_id"], datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template("customer_form.html", customer=None)


@app.route("/customer/<int:customer_id>/edit", methods=["GET", "POST"])
def edit_customer(customer_id):
    if "user_id" not in session or session["role"] != "employee":
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        category = request.form["category"]

        conn.execute(
            """UPDATE customers SET name = ?, email = ?, phone = ?, category = ?
               WHERE id = ?""",
            (name, email, phone, category, customer_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("dashboard"))

    customer = conn.execute(
        "SELECT * FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()
    conn.close()

    return render_template("customer_form.html", customer=customer)


@app.route("/customer/<int:customer_id>/disable", methods=["POST"])
def disable_customer(customer_id):
    if "user_id" not in session or session["role"] != "employee":
        return redirect(url_for("login"))

    # just disable, don't actually delete it
    conn = get_db_connection()
    conn.execute("UPDATE customers SET is_disabled = 1 WHERE id = ?", (customer_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


@app.route("/customer/<int:customer_id>")
def customer_detail(customer_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    customer = conn.execute(
        "SELECT * FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()

    # contact history, newest first
    contacts = conn.execute(
        """SELECT contacts.*, users.full_name AS employee_name
           FROM contacts
           JOIN users ON contacts.employee_id = users.id
           WHERE contacts.customer_id = ?
           ORDER BY contacts.contact_date DESC""",
        (customer_id,)
    ).fetchall()

    conn.close()

    return render_template("customer_detail.html", customer=customer, contacts=contacts)


@app.route("/customer/<int:customer_id>/add_contact", methods=["POST"])
def add_contact(customer_id):
    if "user_id" not in session or session["role"] != "employee":
        return redirect(url_for("login"))

    comment = request.form["comment"]
    if request.form.get("no_response"):
        no_response = 1
    else:
        no_response = 0

    conn = get_db_connection()
    conn.execute(
        """INSERT INTO contacts (customer_id, employee_id, contact_date, comment, no_response)
           VALUES (?, ?, ?, ?, ?)""",
        (customer_id, session["user_id"], datetime.now().isoformat(), comment, no_response)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("customer_detail", customer_id=customer_id))


if __name__ == "__main__":
    app.run(debug=True)
