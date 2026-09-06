# creates the database and tables, run once to set up (or reset)

import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# drop old tables in case we run this again
cursor.execute("DROP TABLE IF EXISTS contacts")
cursor.execute("DROP TABLE IF EXISTS customers")
cursor.execute("DROP TABLE IF EXISTS users")

cursor.execute("""
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
)
""")

cursor.execute("""
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    category TEXT NOT NULL DEFAULT 'Leads',
    is_disabled INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (created_by) REFERENCES users (id)
)
""")

cursor.execute("""
CREATE TABLE contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    employee_id INTEGER NOT NULL,
    contact_date TEXT NOT NULL,
    comment TEXT,
    no_response INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (customer_id) REFERENCES customers (id),
    FOREIGN KEY (employee_id) REFERENCES users (id)
)
""")

# test users, password is "1234" for all
test_password = generate_password_hash("1234")

cursor.execute(
    "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
    ("john", test_password, "John Samoilis", "employee")
)

cursor.execute(
    "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
    ("david", test_password, "David Michael", "manager")
)

cursor.execute(
    "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
    ("ian", test_password, "Ian Statham", "admin")
)

conn.commit()
conn.close()

print("Database created! You can now run app.py")
print("Test accounts (password is 1234 for all):")
print(" - username: john   (employee)")
print(" - username: david  (manager)")
print(" - username: ian    (admin)")
