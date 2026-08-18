from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime

app = Flask(__name__)

# =========================================================
# APP CONFIGURATION
# =========================================================

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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

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

    conn.commit()
    conn.close()


# Create database when application starts
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

        # Validate fields
        if not name or not email or not password:

            flash(
                "Please complete all fields.",
                "danger"
            )

            return redirect(
                url_for("register")
            )

        # Validate password
        if len(password) < 6:

            flash(
                "Password must be at least 6 characters.",
                "danger"
            )

            return redirect(
                url_for("register")
            )

        conn = get_db()

        # Check existing account
        existing_user = conn.execute(
            """
            SELECT id
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        if existing_user:

            conn.close()

            flash(
                "An account with this email already exists. Please login.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        # Hash password
        hashed_password = generate_password_hash(
            password
        )

        # Create account
        conn.execute(
            """
            INSERT INTO users
            (
                name,
                email,
                password,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                name,
                email,
                hashed_password,
                datetime.utcnow().isoformat()
            )
        )

        conn.commit()
        conn.close()

        flash(
            "Account created successfully. You can now login.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "register.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        # Check empty fields
        if not email or not password:

            flash(
                "Please enter your email and password.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        conn = get_db()

        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        conn.close()

        # Account doesn't exist
        if user is None:

            flash(
                "No account was found with that email.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        # Password is incorrect
        if not check_password_hash(
            user["password"],
            password
        ):

            flash(
                "Incorrect password. Please try again.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        # Successful login
        session.clear()

        session["user_id"] = user["id"]

        session["user_name"] = user["name"]

        return redirect(
            url_for("workspace")
        )

    return render_template(
        "login.html"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(
        url_for("home")
    )


# =========================================================
# WORKSPACE
# =========================================================

@app.route("/workspace")
@login_required
def workspace():

    conn = get_db()

    posts = conn.execute(
        """
        SELECT *
        FROM posts
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "workspace.html",
        posts=posts,
        user_name=session.get("user_name")
    )


# =========================================================
# CREATE POST
# =========================================================

@app.route("/create-post", methods=["GET", "POST"])
@login_required
def create_post():

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        content = request.form.get(
            "content",
            ""
        ).strip()

        # Validate post
        if not title or not content:

            flash(
                "Title and content are required.",
                "danger"
            )

            return redirect(
                url_for("create_post")
            )

        conn = get_db()

        conn.execute(
            """
            INSERT INTO posts
            (
                user_id,
                title,
                content,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                session["user_id"],
                title,
                content,
                datetime.utcnow().isoformat()
            )
        )

        conn.commit()
        conn.close()

        flash(
            "Your post has been published!",
            "success"
        )

        return redirect(
            url_for("workspace")
        )

    return render_template(
        "create_post.html"
    )


# =========================================================
# PUBLIC BLOG
# =========================================================

@app.route("/blog")
def blog():

    conn = get_db()

    posts = conn.execute(
        """
        SELECT
            posts.*,
            users.name
        FROM posts
        JOIN users
            ON posts.user_id = users.id
        ORDER BY posts.id DESC
        """
    ).fetchall()

    conn.close()

    return render_template(
        "blog.html",
        posts=posts
    )


# =========================================================
# VIEW SINGLE POST
# =========================================================

@app.route("/post/<int:post_id>")
def view_post(post_id):

    conn = get_db()

    post = conn.execute(
        """
        SELECT
            posts.*,
            users.name
        FROM posts
        JOIN users
            ON posts.user_id = users.id
        WHERE posts.id = ?
        """,
        (post_id,)
    ).fetchone()

    conn.close()

    if not post:

        return "Post not found", 404

    return render_template(
        "post.html",
        post=post
    )


# =========================================================
# SEARCH
# =========================================================

@app.route("/search")
def search():

    query = request.args.get(
        "q",
        ""
    ).strip()

    conn = get_db()

    if query:

        posts = conn.execute(
            """
            SELECT
                posts.*,
                users.name
            FROM posts
            JOIN users
                ON posts.user_id = users.id
            WHERE posts.title LIKE ?
               OR posts.content LIKE ?
            ORDER BY posts.id DESC
            """,
            (
                f"%{query}%",
                f"%{query}%"
            )
        ).fetchall()

    else:

        posts = []

    conn.close()

    return render_template(
        "search.html",
        posts=posts,
        query=query
    )


# =========================================================
# FREE TOOLS
# =========================================================

@app.route("/tools")
def tools():

    return render_template(
        "tools.html"
    )


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=False
    )
