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


init_db()


# =========================================================
# LOGIN REQUIRED
# =========================================================

def login_required(view):

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        if "user_id" not in session:
            flash("Please login to continue.", "warning")
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

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Please complete all fields.", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("register"))

        conn = get_db()

        existing_user = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing_user:
            conn.close()
            flash("An account with this email already exists.", "danger")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        conn.execute("""
            INSERT INTO users
            (name, email, password, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            name,
            email,
            hashed_password,
            datetime.utcnow().isoformat()
        ))

        conn.commit()
        conn.close()

        flash(
            "Account created successfully. You can now login.",
            "success"
        )

        return redirect(url_for("login"))

    return """
    <!DOCTYPE html>
    <html>
    <head>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <title>Join NijaWebbies</title>

        <style>

            body {
                font-family: Arial;
                background: #f5f7fa;
                padding: 30px;
            }

            .box {
                max-width: 450px;
                margin: auto;
                background: white;
                padding: 30px;
                border-radius: 15px;
                box-shadow: 0 5px 20px rgba(0,0,0,.08);
            }

            input {
                width: 100%;
                padding: 13px;
                margin: 8px 0 15px;
                box-sizing: border-box;
            }

            button {
                width: 100%;
                padding: 14px;
                background: #0b7a3b;
                color: white;
                border: 0;
                border-radius: 6px;
                font-size: 16px;
            }

            a {
                color: #0b7a3b;
            }

        </style>

    </head>

    <body>

    <div class="box">

        <h1>🇳🇬 Join NijaWebbies</h1>

        <p>Create your free account.</p>

        <form method="POST">

            <label>Name</label>

            <input
                type="text"
                name="name"
                placeholder="Your name"
                required
            >

            <label>Email</label>

            <input
                type="email"
                name="email"
                placeholder="you@example.com"
                required
            >

            <label>Password</label>

            <input
                type="password"
                name="password"
                placeholder="At least 6 characters"
                required
            >

            <button type="submit">
                Create Free Account
            </button>

        </form>

        <p>
            Already have an account?
            <a href="/login">Login</a>
        </p>

        <p>
            <a href="/">← Back home</a>
        </p>

    </div>

    </body>
    </html>
    """


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()

        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["user_name"] = user["name"]

            return redirect(url_for("workspace"))

        flash("Invalid email or password.", "danger")

    return """
    <!DOCTYPE html>
    <html>
    <head>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <title>Login - NijaWebbies</title>

        <style>

            body {
                font-family: Arial;
                background: #f5f7fa;
                padding: 30px;
            }

            .box {
                max-width: 450px;
                margin: auto;
                background: white;
                padding: 30px;
                border-radius: 15px;
                box-shadow: 0 5px 20px rgba(0,0,0,.08);
            }

            input {
                width: 100%;
                padding: 13px;
                margin: 8px 0 15px;
                box-sizing: border-box;
            }

            button {
                width: 100%;
                padding: 14px;
                background: #0b7a3b;
                color: white;
                border: 0;
                border-radius: 6px;
                font-size: 16px;
            }

            a {
                color: #0b7a3b;
            }

        </style>

    </head>

    <body>

    <div class="box">

        <h1>🔐 Login</h1>

        <form method="POST">

            <label>Email</label>

            <input
                type="email"
                name="email"
                required
            >

            <label>Password</label>

            <input
                type="password"
                name="password"
                required
            >

            <button type="submit">
                Login
            </button>

        </form>

        <p>
            Don't have an account?
            <a href="/register">Join free</a>
        </p>

        <p>
            <a href="/">← Back home</a>
        </p>

    </div>

    </body>
    </html>
    """


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# =========================================================
# WORKSPACE
# =========================================================

@app.route("/workspace")
@login_required
def workspace():

    conn = get_db()

    posts = conn.execute("""
        SELECT *
        FROM posts
        WHERE user_id = ?
        ORDER BY id DESC
    """, (
        session["user_id"],
    )).fetchall()

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

        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()

        if not title or not content:

            flash(
                "Title and content are required.",
                "danger"
            )

            return redirect(url_for("create_post"))

        conn = get_db()

        conn.execute("""
            INSERT INTO posts
            (user_id, title, content, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            session["user_id"],
            title,
            content,
            datetime.utcnow().isoformat()
        ))

        conn.commit()
        conn.close()

        flash(
            "Your post has been published!",
            "success"
        )

        return redirect(url_for("workspace"))

    return """
    <!DOCTYPE html>
    <html>
    <head>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <title>Create Post - NijaWebbies</title>

        <style>

            body {
                font-family: Arial;
                background: #f5f7fa;
                padding: 20px;
            }

            .box {
                max-width: 800px;
                margin: auto;
                background: white;
                padding: 30px;
                border-radius: 15px;
            }

            input,
            textarea {
                width: 100%;
                padding: 14px;
                margin: 8px 0 20px;
                box-sizing: border-box;
            }

            textarea {
                min-height: 300px;
            }

            button {
                padding: 14px 25px;
                background: #0b7a3b;
                color: white;
                border: 0;
                border-radius: 6px;
            }

            a {
                color: #0b7a3b;
            }

        </style>

    </head>

    <body>

    <div class="box">

        <h1>✍️ Create a Post</h1>

        <form method="POST">

            <label>Title</label>

            <input
                type="text"
                name="title"
                placeholder="Your post title"
                required
            >

            <label>Content</label>

            <textarea
                name="content"
                placeholder="Write your article here..."
                required
            ></textarea>

            <button type="submit">
                Publish Post
            </button>

        </form>

        <p>
            <a href="/workspace">
                ← Back to Workspace
            </a>
        </p>

    </div>

    </body>
    </html>
    """


# =========================================================
# EDIT POST
# =========================================================

@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@login_required
def edit_post(post_id):

    conn = get_db()

    post = conn.execute("""
        SELECT *
        FROM posts
        WHERE id = ?
          AND user_id = ?
    """, (
        post_id,
        session["user_id"]
    )).fetchone()

    if not post:
        conn.close()
        return "Post not found or you do not have permission.", 404

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()

        if not title or not content:

            conn.close()

            flash(
                "Title and content are required.",
                "danger"
            )

            return redirect(
                url_for(
                    "edit_post",
                    post_id=post_id
                )
            )

        conn.execute("""
            UPDATE posts
            SET title = ?, content = ?
            WHERE id = ?
              AND user_id = ?
        """, (
            title,
            content,
            post_id,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        flash(
            "Your post has been updated.",
            "success"
        )

        return redirect(url_for("workspace"))

    conn.close()

    return f"""
    <!DOCTYPE html>
    <html>
    <head>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <title>Edit Post - NijaWebbies</title>

        <style>

            body {{
                font-family: Arial;
                background: #f5f7fa;
                padding: 20px;
            }}

            .box {{
                max-width: 800px;
                margin: auto;
                background: white;
                padding: 30px;
                border-radius: 15px;
            }}

            input,
            textarea {{
                width: 100%;
                padding: 14px;
                margin: 8px 0 20px;
                box-sizing: border-box;
            }}

            textarea {{
                min-height: 300px;
            }}

            button {{
                padding: 14px 25px;
                background: #0b7a3b;
                color: white;
                border: 0;
                border-radius: 6px;
            }}

            a {{
                color: #0b7a3b;
            }}

        </style>

    </head>

    <body>

    <div class="box">

        <h1>✏️ Edit Post</h1>

        <form method="POST">

            <label>Title</label>

            <input
                type="text"
                name="title"
                value="{post["title"]}"
                required
            >

            <label>Content</label>

            <textarea
                name="content"
                required
            >{post["content"]}</textarea>

            <button type="submit">
                Save Changes
            </button>

        </form>

        <p>
            <a href="/workspace">
                ← Back to Workspace
            </a>
        </p>

    </div>

    </body>
    </html>
    """


# =========================================================
# DELETE POST
# =========================================================

@app.route("/delete-post/<int:post_id>", methods=["POST"])
@login_required
def delete_post(post_id):

    conn = get_db()

    post = conn.execute("""
        SELECT id
        FROM posts
        WHERE id = ?
          AND user_id = ?
    """, (
        post_id,
        session["user_id"]
    )).fetchone()

    if not post:

        conn.close()

        flash(
            "Post not found or you do not have permission.",
            "danger"
        )

        return redirect(url_for("workspace"))

    conn.execute("""
        DELETE FROM posts
        WHERE id = ?
          AND user_id = ?
    """, (
        post_id,
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    flash(
        "Post deleted successfully.",
        "success"
    )

    return redirect(url_for("workspace"))


# =========================================================
# PUBLIC BLOG
# =========================================================

@app.route("/blog")
def blog():

    conn = get_db()

    posts = conn.execute("""
        SELECT posts.*, users.name
        FROM posts
        JOIN users
        ON posts.user_id = users.id
        ORDER BY posts.id DESC
    """).fetchall()

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

    post = conn.execute("""
        SELECT posts.*, users.name
        FROM posts
        JOIN users
        ON posts.user_id = users.id
        WHERE posts.id = ?
    """, (
        post_id,
    )).fetchone()

    conn.close()

    if not post:
        return "Post not found", 404

    return f"""
    <!DOCTYPE html>
    <html>

    <head>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <title>{post["title"]} - NijaWebbies</title>

        <style>

            body {{
                font-family: Arial;
                background: #f5f7fa;
                padding: 20px;
            }}

            article {{
                max-width: 800px;
                margin: auto;
                background: white;
                padding: 30px;
                border-radius: 15px;
            }}

            .content {{
                margin-top: 25px;
                line-height: 1.8;
                white-space: pre-wrap;
            }}

            a {{
                color: #0b7a3b;
            }}

        </style>

    </head>

    <body>

    <article>

        <h1>{post["title"]}</h1>

        <p>
            By <strong>{post["name"]}</strong>
        </p>

        <div class="content">
            {post["content"]}
        </div>

        <br>

        <a href="/blog">
            ← Back to Blog
        </a>

    </article>

    </body>

    </html>
    """


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

        posts = conn.execute("""
            SELECT posts.*, users.name
            FROM posts
            JOIN users
            ON posts.user_id = users.id
            WHERE posts.title LIKE ?
               OR posts.content LIKE ?
            ORDER BY posts.id DESC
        """, (
            f"%{query}%",
            f"%{query}%"
        )).fetchall()

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

    return """
    <!DOCTYPE html>

    <html>

    <head>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <title>NijaWebbies Free Tools</title>

        <style>

            body {
                font-family: Arial;
                background: #f5f7fa;
                padding: 25px;
            }

            .box {
                max-width: 900px;
                margin: auto;
            }

            .tool {
                background: white;
                padding: 25px;
                margin: 15px 0;
                border-radius: 12px;
            }

            a {
                color: #0b7a3b;
            }

        </style>

    </head>

    <body>

    <div class="box">

        <h1>🛠️ NijaWebbies Free Tools</h1>

        <p>
            Useful tools will be added here as NijaWebbies grows.
        </p>

        <div class="tool">

            <h3>✍️ Writing Tools</h3>

            <p>
                Writing and text tools coming soon.
            </p>

        </div>

        <div class="tool">

            <h3>📊 Business Tools</h3>

            <p>
                Business productivity tools coming soon.
            </p>

        </div>

        <div class="tool">

            <h3>🎨 Creator Tools</h3>

            <p>
                Creator tools coming soon.
            </p>

        </div>

        <div class="tool">

            <h3>🔧 Productivity Tools</h3>

            <p>
                Productivity tools coming soon.
            </p>

        </div>

        <a href="/">
            ← Back home
        </a>

    </div>

    </body>

    </html>
    """


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
