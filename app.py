from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
import psycopg2
from psycopg2.extras import RealDictCursor
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

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.config["SESSION_COOKIE_SECURE"] = bool(
    os.environ.get("RENDER_EXTERNAL_URL")
    or os.environ.get("RENDER")
)


# =========================================================
# DATABASE
# =========================================================

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable is not configured."
        )

    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10
    )


def close_db(conn):

    if conn:
        try:
            conn.close()
        except Exception:
            pass


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():

    conn = None

    try:

        conn = get_db()

        with conn.cursor() as cursor:

            # -------------------------------------------------
            # USERS
            # -------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
            """)

            # -------------------------------------------------
            # POSTS
            # -------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,

                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
                )
            """)

            # -------------------------------------------------
            # CREATOR PROJECTS
            # -------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS creator_projects (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    project_type TEXT,
                    status TEXT DEFAULT 'Idea',
                    created_at TIMESTAMP NOT NULL,

                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
                )
            """)

            # -------------------------------------------------
            # SAFETY MIGRATION
            # -------------------------------------------------

            cursor.execute("""
                ALTER TABLE creator_projects
                ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'Idea'
            """)

            # -------------------------------------------------
            # BUSINESS PROFILES
            # -------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS business_profiles (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    business_name TEXT NOT NULL,
                    description TEXT,
                    category TEXT,
                    phone TEXT,
                    location TEXT,
                    website TEXT,
                    created_at TIMESTAMP NOT NULL,

                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
                )
            """)

            # -------------------------------------------------
            # COMMUNITIES
            # -------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS communities (
                    id SERIAL PRIMARY KEY,
                    owner_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    category TEXT,
                    created_at TIMESTAMP NOT NULL,

                    FOREIGN KEY (owner_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
                )
            """)

            # -------------------------------------------------
            # COMMUNITY MEMBERS
            # -------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS community_members (
                    id SERIAL PRIMARY KEY,
                    community_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    joined_at TIMESTAMP NOT NULL,

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

        app.logger.info(
            "PostgreSQL database initialized successfully."
        )

    except Exception:

        if conn:
            conn.rollback()

        app.logger.exception(
            "PostgreSQL initialization failed."
        )

        raise

    finally:

        close_db(conn)


# =========================================================
# START DATABASE
# =========================================================

try:

    init_db()

except Exception:

    app.logger.exception(
        "Database startup failed."
    )


# =========================================================
# HELPERS
# =========================================================

def is_safe_url(target):

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

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT id
                    FROM users
                    WHERE LOWER(email) = LOWER(%s)
                    LIMIT 1
                    """,
                    (email,)
                )

                existing_user = cursor.fetchone()

                if existing_user:

                    flash(
                        "An account with this email already exists. Please login.",
                        "warning"
                    )

                    return redirect(
                        url_for("login")
                    )

                hashed_password = generate_password_hash(
                    password
                )

                cursor.execute(
                    """
                    INSERT INTO users
                    (
                        name,
                        email,
                        password,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        name,
                        email,
                        hashed_password,
                        datetime.utcnow()
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

        except psycopg2.IntegrityError:

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

    if session.get("user_id"):

        return redirect(
            url_for("workspace")
        )

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

        if not next_page:

            next_page = request.form.get(
                "next",
                ""
            )

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

            with conn.cursor(
                cursor_factory=RealDictCursor
            ) as cursor:

                cursor.execute(
                    """
                    SELECT
                        id,
                        name,
                        email,
                        password
                    FROM users
                    WHERE LOWER(email) = LOWER(%s)
                    LIMIT 1
                    """,
                    (email,)
                )

                user = cursor.fetchone()

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

        session.clear()

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        session["user_email"] = user["email"]

        session.permanent = bool(remember)

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

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            # POSTS
            cursor.execute(
                """
                SELECT *
                FROM posts
                WHERE user_id = %s
                ORDER BY id DESC
                """,
                (user_id,)
            )

            posts = cursor.fetchall()

            # CREATOR PROJECTS
            cursor.execute(
                """
                SELECT *
                FROM creator_projects
                WHERE user_id = %s
                ORDER BY id DESC
                """,
                (user_id,)
            )

            creator_projects = cursor.fetchall()

            # BUSINESS
            cursor.execute(
                """
                SELECT *
                FROM business_profiles
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id,)
            )

            business = cursor.fetchone()

            # COMMUNITIES
            cursor.execute(
                """
                SELECT communities.*
                FROM communities
                JOIN community_members
                    ON communities.id =
                       community_members.community_id
                WHERE community_members.user_id = %s
                ORDER BY communities.id DESC
                """,
                (user_id,)
            )

            communities = cursor.fetchall()

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

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    INSERT INTO posts
                    (
                        user_id,
                        title,
                        content,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        session["user_id"],
                        title,
                        content,
                        datetime.utcnow()
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

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT *
                FROM posts
                WHERE id = %s
                AND user_id = %s
                """,
                (
                    post_id,
                    session["user_id"]
                )
            )

            post = cursor.fetchone()

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

                cursor.execute(
                    """
                    UPDATE posts
                    SET
                        title = %s,
                        content = %s
                    WHERE id = %s
                    AND user_id = %s
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

        with conn.cursor() as cursor:

            cursor.execute(
                """
                DELETE FROM posts
                WHERE id = %s
                AND user_id = %s
                """,
                (
                    post_id,
                    session["user_id"]
                )
            )

            deleted = cursor.rowcount

        if deleted == 0:

            conn.rollback()

            flash(
                "Post not found or you do not have permission.",
                "danger"
            )

            return redirect(
                url_for("workspace")
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

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT
                    posts.*,
                    users.name
                FROM posts
                JOIN users
                    ON posts.user_id = users.id
                ORDER BY posts.id DESC
                """
            )

            posts = cursor.fetchall()

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

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT
                    posts.*,
                    users.name
                FROM posts
                JOIN users
                    ON posts.user_id = users.id
                WHERE posts.id = %s
                """,
                (post_id,)
            )

            post = cursor.fetchone()

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

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            if query:

                cursor.execute(
                    """
                    SELECT
                        posts.*,
                        users.name
                    FROM posts
                    JOIN users
                        ON posts.user_id = users.id
                    WHERE posts.title ILIKE %s
                       OR posts.content ILIKE %s
                    ORDER BY posts.id DESC
                    """,
                    (
                        f"%{query}%",
                        f"%{query}%"
                    )
                )

                posts = cursor.fetchall()

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

        # -------------------------------------------------
        # CREATE PROJECT
        # -------------------------------------------------

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

            allowed_types = [
                "General",
                "🎥 Video",
                "✍️ Blog",
                "📱 Social Media",
                "🎨 Artwork",
                "🎵 Music",
                "🎙️ Podcast",
                "🏪 Business Content",

                # Older project values
                "Video",
                "Blog",
                "Social Media",
                "Artwork",
                "Music",
                "Podcast",
                "Business Content"
            ]

            allowed_statuses = [
                "Idea",
                "Draft",
                "In Production",
                "Published"
            ]

            if project_type not in allowed_types:

                project_type = "General"

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

            with conn.cursor() as cursor:

                cursor.execute(
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
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session["user_id"],
                        title,
                        description,
                        project_type,
                        status,
                        datetime.utcnow()
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

        # -------------------------------------------------
        # LOAD PROJECTS
        # -------------------------------------------------

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT *
                FROM creator_projects
                WHERE user_id = %s
                ORDER BY id DESC
                """,
                (session["user_id"],)
            )

            projects = cursor.fetchall()

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
# VIEW CREATOR PROJECT
# =========================================================

@app.route(
    "/creator-project/<int:project_id>"
)
@login_required
def view_creator_project(project_id):

    conn = None

    try:

        conn = get_db()

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT
                    creator_projects.*,
                    users.name AS owner_name
                FROM creator_projects
                JOIN users
                    ON creator_projects.user_id = users.id
                WHERE creator_projects.id = %s
                AND creator_projects.user_id = %s
                LIMIT 1
                """,
                (
                    project_id,
                    session["user_id"]
                )
            )

            project = cursor.fetchone()

        if not project:

            flash(
                "Creator project not found or you do not have permission to view it.",
                "danger"
            )

            return redirect(
                url_for("creator_studio")
            )

        return render_template(
            "view_creator_project.html",
            project=project,
            user_name=session.get("user_name")
        )

    except Exception:

        app.logger.exception(
            "View Creator Project error."
        )

        flash(
            "Unable to open this creator project right now.",
            "danger"
        )

        return redirect(
            url_for("creator_studio")
        )

    finally:

        close_db(conn)


# =========================================================
# PROJECT URL ALIAS
# =========================================================

@app.route(
    "/project/<int:project_id>"
)
@login_required
def view_project(project_id):

    return redirect(
        url_for(
            "view_creator_project",
            project_id=project_id
        )
    )


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

        # -------------------------------------------------
        # FIND PROJECT
        # -------------------------------------------------

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT *
                FROM creator_projects
                WHERE id = %s
                AND user_id = %s
                LIMIT 1
                """,
                (
                    project_id,
                    session["user_id"]
                )
            )

            project = cursor.fetchone()

        if not project:

            flash(
                "Creator project not found or you do not have permission to edit it.",
                "danger"
            )

            return redirect(
                url_for("creator_studio")
            )

        # -------------------------------------------------
        # GET = SHOW EDIT FORM
        # -------------------------------------------------

        if request.method == "GET":

            return render_template(
                "edit_creator_project.html",
                project=project,
                user_name=session.get("user_name")
            )

        # -------------------------------------------------
        # POST = SAVE EDIT
        # -------------------------------------------------

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

        allowed_types = [
            "General",
            "🎥 Video",
            "✍️ Blog",
            "📱 Social Media",
            "🎨 Artwork",
            "🎵 Music",
            "🎙️ Podcast",
            "🏪 Business Content",

            # Older values
            "Video",
            "Blog",
            "Social Media",
            "Artwork",
            "Music",
            "Podcast",
            "Business Content"
        ]

        allowed_statuses = [
            "Idea",
            "Draft",
            "In Production",
            "Published"
        ]

        if project_type not in allowed_types:

            project_type = "General"

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

        # -------------------------------------------------
        # UPDATE DATABASE
        # -------------------------------------------------

        with conn.cursor() as cursor:

            cursor.execute(
                """
                UPDATE creator_projects
                SET
                    title = %s,
                    description = %s,
                    project_type = %s,
                    status = %s
                WHERE id = %s
                AND user_id = %s
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

            updated = cursor.rowcount

        if updated == 0:

            conn.rollback()

            flash(
                "No changes were saved.",
                "danger"
            )

            return redirect(
                url_for("creator_studio")
            )

        conn.commit()

        flash(
            "Creator project updated successfully.",
            "success"
        )

        return redirect(
            url_for("creator_studio")
        )

    except Exception:

        if conn:
            conn.rollback()

        app.logger.exception(
            "Edit Creator Project error."
        )

        flash(
            "Unable to edit creator project right now. Please try again.",
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

        with conn.cursor() as cursor:

            cursor.execute(
                """
                DELETE FROM creator_projects
                WHERE id = %s
                AND user_id = %s
                """,
                (
                    project_id,
                    session["user_id"]
                )
            )

            deleted = cursor.rowcount

        if deleted == 0:

            conn.rollback()

            flash(
                "Creator project not found or you do not have permission to delete it.",
                "danger"
            )

            return redirect(
                url_for("creator_studio")
            )

        conn.commit()

        flash(
            "Creator project deleted successfully.",
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

            with conn.cursor(
                cursor_factory=RealDictCursor
            ) as cursor:

                cursor.execute(
                    """
                    SELECT id
                    FROM business_profiles
                    WHERE user_id = %s
                    LIMIT 1
                    """,
                    (session["user_id"],)
                )

                existing = cursor.fetchone()

                if existing:

                    cursor.execute(
                        """
                        UPDATE business_profiles
                        SET
                            business_name = %s,
                            description = %s,
                            category = %s,
                            phone = %s,
                            location = %s,
                            website = %s
                        WHERE id = %s
                        AND user_id = %s
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

                    cursor.execute(
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
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            session["user_id"],
                            business_name,
                            description,
                            category,
                            phone,
                            location,
                            website,
                            datetime.utcnow()
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

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT *
                FROM business_profiles
                WHERE user_id = %s
                LIMIT 1
                """,
                (session["user_id"],)
            )

            business = cursor.fetchone()

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

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    INSERT INTO communities
                    (
                        owner_id,
                        name,
                        description,
                        category,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        session["user_id"],
                        name,
                        description,
                        category,
                        datetime.utcnow()
                    )
                )

                community_id = cursor.fetchone()[0]

                cursor.execute(
                    """
                    INSERT INTO community_members
                    (
                        community_id,
                        user_id,
                        joined_at
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        community_id,
                        session["user_id"],
                        datetime.utcnow()
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

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT
                    communities.*,
                    users.name AS owner_name
                FROM communities
                JOIN users
                    ON communities.owner_id = users.id
                ORDER BY communities.id DESC
                """
            )

            all_communities = cursor.fetchall()

            cursor.execute(
                """
                SELECT communities.*
                FROM communities
                JOIN community_members
                    ON communities.id =
                       community_members.community_id
                WHERE community_members.user_id = %s
                ORDER BY communities.id DESC
                """,
                (session["user_id"],)
            )

            my_communities = cursor.fetchall()

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

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT id
                FROM communities
                WHERE id = %s
                """,
                (community_id,)
            )

            community = cursor.fetchone()

            if not community:

                flash(
                    "Community not found.",
                    "danger"
                )

                return redirect(
                    url_for("communities")
                )

            cursor.execute(
                """
                INSERT INTO community_members
                (
                    community_id,
                    user_id,
                    joined_at
                )
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    community_id,
                    session["user_id"],
                    datetime.utcnow()
                )
            )

            added = cursor.rowcount

        conn.commit()

        if added:

            flash(
                "You joined the community.",
                "success"
            )

        else:

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

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1"
        >

        <title>
            Page Not Found - NijaWebbies
        </title>

    </head>

    <body style="
        font-family:Arial,sans-serif;
        text-align:center;
        padding:50px 20px;
        background:#f5f7fb;
        color:#111827;
    ">

        <h1 style="
            font-size:60px;
            margin-bottom:10px;
        ">
            404
        </h1>

        <h2>
            Page not found
        </h2>

        <p style="
            color:#6b7280;
        ">
            The page you are looking for does not exist.
        </p>

        <br>

        <a
            href="/"
            style="
                color:#2563eb;
                text-decoration:none;
                font-weight:bold;
            "
        >
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

    app.logger.error(
        "NijaWebbies Internal Server Error: %s",
        error
    )

    return """
    <!DOCTYPE html>
    <html>

    <head>

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1"
        >

        <title>
            NijaWebbies - Error
        </title>

    </head>

    <body style="
        font-family:Arial,sans-serif;
        text-align:center;
        padding:50px 20px;
        background:#f5f7fb;
        color:#111827;
    ">

        <h1>
            Something went wrong
        </h1>

        <p style="
            color:#6b7280;
        ">
            NijaWebbies encountered an unexpected error.
        </p>

        <p style="
            color:#6b7280;
        ">
            Please try again.
        </p>

        <br>

        <a
            href="/"
            style="
                color:#2563eb;
                text-decoration:none;
                font-weight:bold;
            "
        >
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
