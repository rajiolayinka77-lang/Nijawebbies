from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
from urllib.parse import urlparse


# =========================================================
# APP
# =========================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "nijawebbies-development-secret-change-this"
)

# Remember Me = 30 days
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# Session security
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Render runs over HTTPS.
# Do not depend only on the RENDER environment variable.
app.config["SESSION_COOKIE_SECURE"] = bool(
    os.environ.get("RENDER_EXTERNAL_URL")
    or os.environ.get("RENDER")
)


# =========================================================
# DATABASE
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Keep the database in the application directory.
DATABASE = os.path.join(BASE_DIR, "nijawebbies.db")


def get_db():
    """
    Create a SQLite database connection.
    """

    conn = sqlite3.connect(
        DATABASE,
        timeout=30,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    # Better SQLite behavior.
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")

    return conn


def close_db(conn):
    """
    Safely close a database connection.
    """

    if conn:
        try:
            conn.close()
        except Exception:
            pass


def init_db():
    """
    Create all required database tables.
    """

    conn = None

    try:

        conn = get_db()

        # =================================================
        # USERS
        # =================================================

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # =================================================
        # POSTS
        # =================================================

        conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,

                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        # =================================================
        # CREATOR PROJECTS
        # =================================================

        conn.execute("""
            CREATE TABLE IF NOT EXISTS creator_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                project_type TEXT,
                status TEXT DEFAULT 'Idea',
                created_at TEXT NOT NULL,

                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        # Upgrade older Creator Studio databases.
        creator_columns = conn.execute(
            "PRAGMA table_info(creator_projects)"
        ).fetchall()

        creator_column_names = [
            column["name"]
            for column in creator_columns
        ]

        if "status" not in creator_column_names:

            conn.execute("""
                ALTER TABLE creator_projects
                ADD COLUMN status TEXT DEFAULT 'Idea'
            """)

        # =================================================
        # BUSINESS PROFILES
        # =================================================

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

                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        # =================================================
        # COMMUNITIES
        # =================================================

        conn.execute("""
            CREATE TABLE IF NOT EXISTS communities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                category TEXT,
                created_at TEXT NOT NULL,

                FOREIGN KEY (owner_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        # =================================================
        # COMMUNITY MEMBERS
        # =================================================

        conn.execute("""
            CREATE TABLE IF NOT EXISTS community_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                community_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,

                UNIQUE(community_id, user_id),

                FOREIGN KEY (community_id)
                    REFERENCES communities(id)
                    ON DELETE CASCADE,

                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        conn.commit()

        app.logger.info("Database initialized successfully.")

    except Exception:

        if conn:
            conn.rollback()

        app.logger.exception(
            "Database initialization failed."
        )

        raise

    finally:

        close_db(conn)


# Initialize database.
init_db()


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def is_safe_url(target):
    """
    Prevent unsafe external redirects.
    """

    if not target:
        return False

    try:

        parsed = urlparse(target)

        return (
            parsed.scheme == ""
            and parsed.netloc == ""
            and target.startswith("/")
            and not target.startswith("//")
        )

    except Exception:

        return False


# =========================================================
# LOGIN REQUIRED
# =========================================================

def login_required(view):

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        if not session.get("user_id"):

            flash(
                "Please login to continue.",
                "warning"
            )

            next_page = request.full_path

            if next_page.endswith("?"):
                next_page = next_page[:-1]

            return redirect(
                url_for(
                    "login",
                    next=next_page
                )
            )

        return view(*args, **kwargs)

    return wrapped_view


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template(
        "home.html"
    )


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if session.get("user_id"):

        return redirect(
            url_for("workspace")
        )

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

        # -----------------------------------------------
        # VALIDATION
        # -----------------------------------------------

        if not name or not email or not password:

            flash(
                "Please complete all fields.",
                "danger"
            )

            return render_template(
                "register.html",
                name=name,
                email=email
            )

        if len(password) < 6:

            flash(
                "Password must be at least 6 characters.",
                "danger"
            )

            return render_template(
                "register.html",
                name=name,
                email=email
            )

        if "@" not in email or "." not in email:

            flash(
                "Please enter a valid email address.",
                "danger"
            )

            return render_template(
                "register.html",
                name=name,
                email=email
            )

        conn = None

        try:

            conn = get_db()

            # Check existing account.
            existing_user = conn.execute(
                """
                SELECT id
                FROM users
                WHERE LOWER(email) = ?
                """,
                (email,)
            ).fetchone()

            if existing_user:

                flash(
                    "An account with this email already exists. Please login.",
                    "warning"
                )

                return redirect(
                    url_for("login")
                )

            # Hash password.
            hashed_password = generate_password_hash(
                password
            )

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

            flash(
                "Account created successfully. Please login.",
                "success"
            )

            return redirect(
                url_for("login")
            )

        except sqlite3.IntegrityError:

            if conn:
                conn.rollback()

            flash(
                "An account with this email already exists. Please login.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        except Exception:

            if conn:
                conn.rollback()

            app.logger.exception(
                "Registration error."
            )

            flash(
                "We could not create your account right now. Please try again.",
                "danger"
            )

            return render_template(
                "register.html",
                name=name,
                email=email
            )

        finally:

            close_db(conn)

    return render_template(
        "register.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    # Already logged in.
    if session.get("user_id"):

        return redirect(
            url_for("workspace")
        )

    # Keep the destination from the query string.
    next_page = request.args.get(
        "next",
        ""
    )

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        remember = request.form.get(
            "remember"
        )

        # If next wasn't in request.args, get it from form.
        if not next_page:

            next_page = request.form.get(
                "next",
                ""
            )

        # -----------------------------------------------
        # VALIDATION
        # -----------------------------------------------

        if not email or not password:

            flash(
                "Please enter your email and password.",
                "danger"
            )

            return render_template(
                "login.html",
                email=email,
                next=next_page
            )

        conn = None
        user = None

        try:

            conn = get_db()

            user = conn.execute(
                """
                SELECT
                    id,
                    name,
                    email,
                    password
                FROM users
                WHERE LOWER(email) = ?
                LIMIT 1
                """,
                (email,)
            ).fetchone()

        except Exception:

            app.logger.exception(
                "Login database error."
            )

            flash(
                "Unable to access your account right now. Please try again.",
                "danger"
            )

            return render_template(
                "login.html",
                email=email,
                next=next_page
            )

        finally:

            close_db(conn)

        # -----------------------------------------------
        # PASSWORD CHECK
        # -----------------------------------------------

        password_valid = False

        if user:

            try:

                password_valid = check_password_hash(
                    user["password"],
                    password
                )

            except Exception:

                app.logger.exception(
                    "Password verification error."
                )

                password_valid = False

        if not user or not password_valid:

            flash(
                "Invalid email or password.",
                "danger"
            )

            return render_template(
                "login.html",
                email=email,
                next=next_page
            )

        # -----------------------------------------------
        # CREATE SESSION
        # -----------------------------------------------

        session.clear()

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        session["user_email"] = user["email"]

        # -----------------------------------------------
        # REMEMBER ME
        # -----------------------------------------------

        if remember:

            session.permanent = True

        else:

            session.permanent = False

        # -----------------------------------------------
        # REDIRECT
        # -----------------------------------------------

        if is_safe_url(next_page):

            return redirect(next_page)

        return redirect(
            url_for("workspace")
        )

    return render_template(
        "login.html",
        email="",
        next=next_page
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

    conn = None

    try:

        conn = get_db()

        user_id = session["user_id"]

        posts = conn.execute(
            """
            SELECT *
            FROM posts
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

        creator_projects = conn.execute(
            """
            SELECT *
            FROM creator_projects
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

        business = conn.execute(
            """
            SELECT *
            FROM business_profiles
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,)
        ).fetchone()

        communities = conn.execute(
            """
            SELECT communities.*
            FROM communities
            JOIN community_members
                ON communities.id =
                   community_members.community_id
            WHERE community_members.user_id = ?
            ORDER BY communities.id DESC
            """,
            (user_id,)
        ).fetchall()

        return render_template(
            "workspace.html",
            posts=posts,
            creator_projects=creator_projects,
            business=business,
            communities=communities,
            user_name=session.get("user_name")
        )

    except Exception:

        app.logger.exception(
            "Workspace error."
        )

        flash(
            "Unable to load your workspace right now.",
            "danger"
        )

        return redirect(
            url_for("home")
        )

    finally:

        close_db(conn)


# =========================================================
# CREATE POST
# =========================================================

@app.route(
    "/create-post",
    methods=["GET", "POST"]
)
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

        if not title or not content:

            flash(
                "Title and content are required.",
                "danger"
            )

            return redirect(
                url_for("create_post")
            )

        conn = None

        try:

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

            flash(
                "Your post has been published!",
                "success"
            )

            return redirect(
                url_for("workspace")
            )

        except Exception:

            if conn:
                conn.rollback()

            app.logger.exception(
                "Create post error."
            )

            flash(
                "Unable to publish your post.",
                "danger"
            )

            return redirect(
                url_for("create_post")
            )

        finally:

            close_db(conn)

    return render_template(
        "create_post.html"
    )


# =========================================================
# EDIT POST
# =========================================================

@app.route(
    "/edit-post/<int:post_id>",
    methods=["GET", "POST"]
)
@login_required
def edit_post(post_id):

    conn = None

    try:

        conn = get_db()

        post = conn.execute(
            """
            SELECT *
            FROM posts
            WHERE id = ?
            AND user_id = ?
            """,
            (
                post_id,
                session["user_id"]
            )
        ).fetchone()

        if not post:

            flash(
                "Post not found or you do not have permission.",
                "danger"
            )

            return redirect(
                url_for("workspace")
            )

        if request.method == "POST":

            title = request.form.get(
                "title",
                ""
            ).strip()

            content = request.form.get(
                "content",
                ""
            ).strip()

            if not title or not content:

                flash(
                    "Title and content are required.",
                    "danger"
                )

                return render_template(
                    "edit_post.html",
                    post=post
                )

            conn.execute(
                """
                UPDATE posts
                SET
                    title = ?,
                    content = ?
                WHERE id = ?
                AND user_id = ?
                """,
                (
                    title,
                    content,
                    post_id,
                    session["user_id"]
                )
            )

            conn.commit()

            flash(
                "Your post has been updated.",
                "success"
            )

            return redirect(
                url_for("workspace")
            )

        return render_template(
            "edit_post.html",
            post=post
        )

    except Exception:

        if conn:
            conn.rollback()

        app.logger.exception(
            "Edit post error."
        )

        flash(
            "Unable to edit the post.",
            "danger"
        )

        return redirect(
            url_for("workspace")
        )

    finally:

        close_db(conn)


# =========================================================
# DELETE POST
# =========================================================

@app.route(
    "/delete-post/<int:post_id>",
    methods=["POST"]
)
@login_required
def delete_post(post_id):

    conn = None

    try:

        conn = get_db()

        post = conn.execute(
            """
            SELECT id
            FROM posts
            WHERE id = ?
            AND user_id = ?
            """,
            (
                post_id,
                session["user_id"]
            )
        ).fetchone()

        if not post:

            flash(
                "Post not found or you do not have permission.",
                "danger"
            )

            return redirect(
                url_for("workspace")
            )

        conn.execute(
            """
            DELETE FROM posts
            WHERE id = ?
            AND user_id = ?
            """,
            (
                post_id,
                session["user_id"]
            )
        )

        conn.commit()

        flash(
            "Post deleted successfully.",
            "success"
        )

        return redirect(
            url_for("workspace")
        )

    except Exception:

        if conn:
            conn.rollback()

        app.logger.exception(
            "Delete post error."
        )

        flash(
            "Unable to delete the post.",
            "danger"
        )

        return redirect(
            url_for("workspace")
        )

    finally:

        close_db(conn)


# =========================================================
# PUBLIC BLOG
# =========================================================

@app.route("/blog")
def blog():

    conn = None

    try:

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

        return render_template(
            "blog.html",
            posts=posts
        )

    except Exception:

        app.logger.exception(
            "Blog error."
        )

        return render_template(
            "blog.html",
            posts=[]
        )

    finally:

        close_db(conn)


# =========================================================
# VIEW SINGLE POST
# =========================================================

@app.route("/post/<int:post_id>")
def view_post(post_id):

    conn = None

    try:

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

        if not post:

            return "Post not found", 404

        return render_template(
            "view_post.html",
            post=post
        )

    except Exception:

        app.logger.exception(
            "View post error."
        )

        return "Unable to load post.", 500

    finally:

        close_db(conn)


# =========================================================
# SEARCH
# =========================================================

@app.route("/search")
def search():

    query = request.args.get(
        "q",
        ""
    ).strip()

    conn = None

    try:

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

        return render_template(
            "search.html",
            posts=posts,
            query=query
        )

    except Exception:

        app.logger.exception(
            "Search error."
        )

        return render_template(
            "search.html",
            posts=[],
            query=query
        )

    finally:

        close_db(conn)


# =========================================================
# CREATOR STUDIO
# =========================================================

@app.route(
    "/creator-studio",
    methods=["GET", "POST"]
)
@login_required
def creator_studio():

    conn = None

    try:

        conn = get_db()

        if request.method == "POST":

            title = request.form.get(
                "title",
                ""
            ).strip()

            description = request.form.get(
                "description",
                ""
            ).strip()

            project_type = request.form.get(
                "project_type",
                "General"
            ).strip()

            status = request.form.get(
                "status",
                "Idea"
            ).strip()

            allowed_statuses = [
                "Idea",
                "Draft",
                "In Production",
                "Published"
            ]

            if status not in allowed_statuses:
                status = "Idea"

            if not title:

                flash(
                    "Please enter a project title.",
                    "danger"
                )

                return redirect(
                    url_for("creator_studio")
                )

            conn.execute(
                """
                INSERT INTO creator_projects
                (
                    user_id,
                    title,
                    description,
                    project_type,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    title,
                    description,
                    project_type,
                    status,
                    datetime.utcnow().isoformat()
                )
            )

            conn.commit()

            flash(
                "Creator project added successfully.",
                "success"
            )

            return redirect(
                url_for("creator_studio")
            )

        projects = conn.execute(
            """
            SELECT *
            FROM creator_projects
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (session["user_id"],)
        ).fetchall()

        return render_template(
            "creator_studio.html",
            projects=projects,
            user_name=session.get("user_name")
        )

    except Exception:

        if conn:
            conn.rollback()

        app.logger.exception(
            "Creator Studio error."
        )

        flash(
            "Unable to load Creator Studio.",
            "danger"
        )

        return redirect(
            url_for("workspace")
        )

    finally:

        close_db(conn)


# =========================================================
# EDIT CREATOR PROJECT
# =========================================================

@app.route(
    "/edit-creator-project/<int:project_id>",
    methods=["GET", "POST"]
)
@login_required
def edit_creator_project(project_id):

    conn = None

    try:

        conn = get_db()

        project = conn.execute(
            """
            SELECT *
            FROM creator_projects
            WHERE id = ?
            AND user_id = ?
            """,
            (
                project_id,
                session["user_id"]
            )
        ).fetchone()

        if not project:

            flash(
                "Creator project not found.",
                "danger"
            )

            return redirect(
                url_for("creator_studio")
            )

        if request.method == "POST":

            title = request.form.get(
                "title",
                ""
            ).strip()

            description = request.form.get(
                "description",
                ""
            ).strip()

            project_type = request.form.get(
                "project_type",
                "General"
            ).strip()

            status = request.form.get(
                "status",
                "Idea"
            ).strip()

            allowed_statuses = [
                "Idea",
                "Draft",
                "In Production",
                "Published"
            ]

            if status not in allowed_statuses:
                status = "Idea"

            if not title:

                flash(
                    "Project title is required.",
                    "danger"
                )

                return render_template(
                    "edit_creator_project.html",
                    project=project,
                    user_name=session.get("user_name")
                )

            conn.execute(
                """
                UPDATE creator_projects
                SET
                    title = ?,
                    description = ?,
                    project_type = ?,
                    status = ?
                WHERE id = ?
                AND user_id = ?
                """,
                (
                    title,
                    description,
                    project_type,
                    status,
                    project_id,
                    session["user_id"]
                )
            )

            conn.commit()

            flash(
                "Creator project updated successfully.",
                "success"
            )

            return redirect(
                url_for("creator_studio")
            )

        return render_template(
            "edit_creator_project.html",
            project=project,
            user_name=session.get("user_name")
        )

    except Exception:

        if conn:
            conn.rollback()

        app.logger.exception(
            "Edit Creator Project error."
        )

        flash(
            "Unable to edit creator project.",
            "danger"
        )

        return redirect(
            url_for("creator_studio")
        )

    finally:

        close_db(conn)


# =========================================================
# DELETE CREATOR PROJECT
# =========================================================

@app.route(
    "/delete-creator-project/<int:project_id>",
    methods=["POST"]
)
@login_required
def delete_creator_project(project_id):

    conn = None

    try:

        conn = get_db()

        project = conn.execute(
            """
            SELECT id
            FROM creator_projects
            WHERE id = ?
            AND user_id = ?
            """,
            (
                project_id,
                session["user_id"]
            )
        ).fetchone()

        if not project:

            flash(
                "Creator project not found.",
                "danger"
            )

            return redirect(
                url_for("creator_studio")
            )

        conn.execute(
            """
            DELETE FROM creator_projects
            WHERE id = ?
            AND user_id = ?
            """,
            (
                project_id,
                session["user_id"]
            )
        )

        conn.commit()

        flash(
            "Creator project deleted.",
            "success"
        )

        return redirect(
            url_for("creator_studio")
        )

    except Exception:

        if conn:
            conn.rollback()

        app.logger.exception(
            "Delete Creator Project error."
        )

        flash(
            "Unable to delete creator project.",
            "danger"
        )

        return redirect(
            url_for("creator_studio")
        )

    finally:

        close_db(conn)


# =========================================================
# BUSINESS SPACE
# =========================================================

@app.route(
    "/business-space",
    methods=["GET", "POST"]
)
@login_required
def business_space():

    conn = None

    try:

        conn = get_db()

        if request.method == "POST":

            business_name = request.form.get(
                "business_name",
                ""
            ).strip()

            description = request.form.get(
                "description",
                ""
            ).strip()

            category = request.form.get(
                "category",
                ""
            ).strip()

            phone = request.form.get(
                "phone",
                ""
            ).strip()

            location = request.form.get(
                "location",
                ""
            ).strip()

            website = request.form.get(
                "website",
                ""
            ).strip()

            if not business_name:

                flash(
                    "Business name is required.",
                    "danger"
                )

                return redirect(
                    url_for("business_space")
                )

            existing = conn.execute(
                """
                SELECT id
                FROM business_profiles
                WHERE user_id = ?
                LIMIT 1
                """,
                (session["user_id"],)
            ).fetchone()

            if existing:

                conn.execute(
                    """
                    UPDATE business_profiles
                    SET
                        business_name = ?,
                        description = ?,
                        category = ?,
                        phone = ?,
                        location = ?,
                        website = ?
                    WHERE id = ?
                    AND user_id = ?
                    """,
                    (
                        business_name,
                        description,
                        category,
                        phone,
                        location,
                        website,
                        existing["id"],
                        session["user_id"]
                    )
                )

            else:

                conn.execute(
                    """
                    INSERT INTO business_profiles
                    (
                        user_id,
                        business_name,
                        description,
                        category,
                        phone,
                        location,
                        website,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session["user_id"],
                        business_name,
                        description,
                        category,
                        phone,
                        location,
                        website,
                        datetime.utcnow().isoformat()
                    )
                )

            conn.commit()

            flash(
                "Business profile saved successfully.",
                "success"
            )

            return redirect(
                url_for("business_space")
            )

        business = conn.execute(
            """
            SELECT *
            FROM business_profiles
            WHERE user_id = ?
            LIMIT 1
            """,
            (session["user_id"],)
        ).fetchone()

        return render_template(
            "business_space.html",
            business=business,
            user_name=session.get("user_name")
        )

    except Exception:

        if conn:
            conn.rollback()

        app.logger.exception(
            "Business Space error."
        )

        flash(
            "Unable to load Business Space.",
            "danger"
        )

        return redirect(
            url_for("workspace")
        )

    finally:

        close_db(conn)


# =========================================================
# COMMUNITIES
# =========================================================

@app.route(
    "/communities",
    methods=["GET", "POST"]
)
@login_required
def communities():

    conn = None

    try:

        conn = get_db()

        if request.method == "POST":

            name = request.form.get(
                "name",
                ""
            ).strip()

            description = request.form.get(
                "description",
                ""
            ).strip()

            category = request.form.get(
                "category",
                ""
            ).strip()

            if not name:

                flash(
                    "Community name is required.",
                    "danger"
                )

                return redirect(
                    url_for("communities")
                )

            cursor = conn.execute(
                """
                INSERT INTO communities
                (
                    owner_id,
                    name,
                    description,
                    category,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    name,
                    description,
                    category,
                    datetime.utcnow().isoformat()
                )
            )

            community_id = cursor.lastrowid

            # Automatically make creator a member.
            conn.execute(
                """
                INSERT INTO community_members
                (
                    community_id,
                    user_id,
                    joined_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    community_id,
                    session["user_id"],
                    datetime.utcnow().isoformat()
                )
            )

            conn.commit()

            flash(
                "Community created successfully.",
                "success"
            )

            return redirect(
                url_for("communities")
            )

        all_communities = conn.execute(
            """
            SELECT
                communities.*,
                users.name AS owner_name
            FROM communities
            JOIN users
                ON communities.owner_id = users.id
            ORDER BY communities.id DESC
            """
        ).fetchall()

        my_communities = conn.execute(
            """
            SELECT communities.*
            FROM communities
            JOIN community_members
                ON communities.id =
                   community_members.community_id
            WHERE community_members.user_id = ?
            ORDER BY communities.id DESC
            """,
            (session["user_id"],)
        ).fetchall()

        return render_template(
            "communities.html",
            communities=all_communities,
            my_communities=my_communities,
            user_name=session.get("user_name")
        )

    except Exception:

        if conn:
            conn.rollback()

        app.logger.exception(
            "Communities error."
        )

        flash(
            "Unable to load Communities.",
            "danger"
        )

        return redirect(
            url_for("workspace")
        )

    finally:

        close_db(conn)


# =========================================================
# JOIN COMMUNITY
# =========================================================

@app.route(
    "/join-community/<int:community_id>",
    methods=["POST"]
)
@login_required
def join_community(community_id):

    conn = None

    try:

        conn = get_db()

        community = conn.execute(
            """
            SELECT id
            FROM communities
            WHERE id = ?
            """,
            (community_id,)
        ).fetchone()

        if not community:

            flash(
                "Community not found.",
                "danger"
            )

            return redirect(
                url_for("communities")
            )

        try:

            conn.execute(
                """
                INSERT INTO community_members
                (
                    community_id,
                    user_id,
                    joined_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    community_id,
                    session["user_id"],
                    datetime.utcnow().isoformat()
                )
            )

            conn.commit()

            flash(
                "You joined the community.",
                "success"
            )

        except sqlite3.IntegrityError:

            conn.rollback()

            flash(
                "You are already a member of this community.",
                "warning"
            )

        return redirect(
            url_for("communities")
        )

    except Exception:

        if conn:
            conn.rollback()

        app.logger.exception(
            "Join community error."
        )

        flash(
            "Unable to join the community.",
            "danger"
        )

        return redirect(
            url_for("communities")
        )

    finally:

        close_db(conn)


# =========================================================
# FREE ONLINE TOOLS
# =========================================================

@app.route("/tools")
def tools():

    return render_template(
        "tools.html"
    )


# =========================================================
# 404
# =========================================================

@app.errorhandler(404)
def page_not_found(error):

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport"
              content="width=device-width, initial-scale=1">
        <title>Page Not Found - NijaWebbies</title>
    </head>

    <body style="
        font-family:Arial,sans-serif;
        text-align:center;
        padding:50px 20px;
        background:#f5f7fb;
        color:#111827;
    ">

        <h1 style="font-size:60px;margin-bottom:10px;">
            404
        </h1>

        <h2>Page not found</h2>

        <p style="color:#6b7280;">
            The page you are looking for does not exist.
        </p>

        <br>

        <a href="/" style="
            color:#2563eb;
            text-decoration:none;
            font-weight:bold;
        ">
            ← Back to NijaWebbies
        </a>

    </body>
    </html>
    """, 404


# =========================================================
# 500
# =========================================================

@app.errorhandler(500)
def internal_server_error(error):

    # The real error will appear in Render logs.
    app.logger.exception(
        "NijaWebbies Internal Server Error"
    )

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport"
              content="width=device-width, initial-scale=1">
        <title>NijaWebbies - Error</title>
    </head>

    <body style="
        font-family:Arial,sans-serif;
        text-align:center;
        padding:50px 20px;
        background:#f5f7fb;
        color:#111827;
    ">

        <h1>Something went wrong</h1>

        <p style="color:#6b7280;">
            NijaWebbies encountered an unexpected error.
        </p>

        <p style="color:#6b7280;">
            Please try again.
        </p>

        <br>

        <a href="/" style="
            color:#2563eb;
            text-decoration:none;
            font-weight:bold;
        ">
            ← Back to NijaWebbies
        </a>

    </body>
    </html>
    """, 500


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
