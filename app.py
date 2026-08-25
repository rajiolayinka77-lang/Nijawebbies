from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "nijawebbies-development-secret"
)

DATABASE = "nijawebbies.db"


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    # USERS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # BLOG POSTS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # CREATOR PROJECTS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS creator_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            project_type TEXT,
            status TEXT DEFAULT 'Idea',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # -----------------------------------------------------
    # SAFE DATABASE UPGRADE
    # Adds status to older databases that don't have it.
    # -----------------------------------------------------

    creator_columns = conn.execute(
        "PRAGMA table_info(creator_projects)"
    ).fetchall()

    column_names = [
        column["name"]
        for column in creator_columns
    ]

    if "status" not in column_names:
        conn.execute("""
            ALTER TABLE creator_projects
            ADD COLUMN status TEXT DEFAULT 'Idea'
        """)

    # BUSINESS PROFILES
    conn.execute("""
        CREATE TABLE IF NOT EXISTS business_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            business_name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            phone TEXT,
            location TEXT,
            website TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # COMMUNITIES
    conn.execute("""
        CREATE TABLE IF NOT EXISTS communities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (owner_id) REFERENCES users(id)
        )
    """)

    # COMMUNITY MEMBERS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS community_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            community_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TEXT NOT NULL,
            UNIQUE(community_id, user_id),
            FOREIGN KEY (community_id) REFERENCES communities(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# LOGIN REQUIRED
# =========================================================

def login_required(view):

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        if "user_id" not in session:
            flash(
                "Please login to continue.",
                "warning"
            )
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped_view


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return render_template("home.html")


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if not name or not email or not password:

            flash(
                "Please complete all fields.",
                "danger"
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 6:

            flash(
                "Password must be at least 6 characters.",
                "danger"
            )

            return redirect(
                url_for("register")
            )

        conn = get_db()

        existing_user = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing_user:

            conn.close()

            flash(
                "An account with this email already exists.",
                "danger"
            )

            return redirect(
                url_for("register")
            )

        hashed_password = generate_password_hash(
            password
        )

        conn.execute("""
            INSERT INTO users
            (name, email, password, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            name,
            email,
            hashed_password,
            datetime.utcnow
