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

            # =================================================
            # USERS
            # =================================================

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
            """)

            # =================================================
            # POSTS
            # =================================================

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

            # =================================================
            # CREATOR PROJECTS
            # =================================================

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

            cursor.execute("""
                ALTER TABLE creator_projects
                ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'Idea'
            """)

            # =================================================
            # BUSINESS PROFILES
            # =================================================

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS business_profiles (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    business_name TEXT NOT NULL,
                    description TEXT,
                    category TEXT,
                    phone TEXT,
                    whatsapp TEXT,
                    location TEXT,
                    website TEXT,
                    created_at TIMESTAMP NOT NULL,

                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                ALTER TABLE business_profiles
                ADD COLUMN IF NOT EXISTS whatsapp TEXT
            """)

            # =================================================
            # COMMUNITIES
            # =================================================

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

            # =================================================
            # COMMUNITY MEMBERS
            # =================================================

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

            # =================================================
            # COMMUNITY DISCUSSIONS
            # =================================================

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS community_posts (
                    id SERIAL PRIMARY KEY,
                    community_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,

                    FOREIGN KEY (community_id)
                    REFERENCES communities(id)
                    ON DELETE CASCADE,

                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
                )
            """)

            # =================================================
            # COMMUNITY COMMENTS / REPLIES
            # =================================================

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS community_comments (
                    id SERIAL PRIMARY KEY,
                    community_post_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,

                    FOREIGN KEY (community_post_id)
                    REFERENCES community_posts(id)
                    ON DELETE CASCADE,

                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
                )
            """)

            # =================================================
            # ADD REPLY SUPPORT TO EXISTING COMMENTS
            # =================================================
            # Existing comments automatically remain top-level
            # comments because their parent_comment_id will be NULL.

            cursor.execute("""
                ALTER TABLE community_comments
                ADD COLUMN IF NOT EXISTS parent_comment_id INTEGER
                REFERENCES community_comments(id)
                ON DELETE CASCADE
            """)

            # =================================================
            # COMMUNITY INDEXES
            # =================================================

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_community_posts_community
                ON community_posts(community_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_community_posts_user
                ON community_posts(user_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_community_members_community
                ON community_members(community_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_community_members_user
                ON community_members(user_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_community_comments_post
                ON community_comments(community_post_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_community_comments_user
                ON community_comments(user_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_community_comments_parent
                ON community_comments(parent_comment_id)
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


def make_whatsapp_link(number):

    if not number:
        return None

    digits = "".join(
        character
        for character in str(number)
        if character.isdigit()
    )

    if not digits:
        return None

    if digits.startswith("0"):
        digits = "234" + digits[1:]

    elif not digits.startswith("234"):
        digits = "234" + digits

    return f"https://wa.me/{digits}"


def make_phone_link(number):

    if not number:
        return None

    clean_phone = "".join(
        character
        for character in str(number)
        if character.isdigit() or character == "+"
    )

    if not clean_phone:
        return None

    return f"tel:{clean_phone}"


def make_website_link(website):

    if not website:
        return None

    website = str(website).strip()

    if not website:
        return None

    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    return website


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

            if request.method == "POST":

                next_page = request.referrer or url_for("home")

            else:

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

    return render_template("home.html")


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if session.get("user_id"):
        return redirect(url_for("workspace"))

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

                    return redirect(url_for("login"))

                hashed_password = generate_password_hash(password)

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

            return redirect(url_for("login"))

        except psycopg2.IntegrityError:

            if conn:
                conn.rollback()

            flash(
                "An account with this email already exists. Please login.",
                "warning"
            )

            return redirect(url_for("login"))

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

    return render_template("register.html")


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if session.get("user_id"):
        return redirect(url_for("workspace"))

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

        remember = request.form.get("remember")

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

        return redirect(url_for("workspace"))

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

    return redirect(url_for("home"))


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

        return redirect(url_for("home"))

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

            return redirect(url_for("create_post"))

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

            return redirect(url_for("workspace"))

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

            return redirect(url_for("create_post"))

        finally:
            close_db(conn)

    return render_template("create_post.html")


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
                LIMIT 1
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

                return redirect(url_for("workspace"))

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

        return redirect(url_for("workspace"))

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

        return redirect(url_for("workspace"))

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

            return redirect(url_for("workspace"))

        conn.commit()

        flash(
            "Post deleted successfully.",
            "success"
        )

        return redirect(url_for("workspace"))

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

        return redirect(url_for("workspace"))

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
                LIMIT 1
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

    category = request.args.get(
        "category",
        ""
    ).strip()

    location = request.args.get(
        "location",
        ""
    ).strip()

    conn = None

    posts = []
    businesses = []
    communities = []
    categories = []

    try:

        conn = get_db()

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT DISTINCT category
                FROM business_profiles
                WHERE category IS NOT NULL
                  AND TRIM(category) <> ''
                ORDER BY category ASC
                """
            )

            categories = cursor.fetchall()

            if query:

                search_term = f"%{query}%"

                cursor.execute(
                    """
                    SELECT
                        posts.*,
                        users.name
                    FROM posts
                    JOIN users
                        ON posts.user_id = users.id
                    WHERE
                        posts.title ILIKE %s
                        OR posts.content ILIKE %s
                    ORDER BY posts.id DESC
                    """,
                    (
                        search_term,
                        search_term
                    )
                )

                posts = cursor.fetchall()

            business_query = """
                SELECT
                    id,
                    user_id,
                    business_name,
                    description,
                    category,
                    phone,
                    whatsapp,
                    location,
                    website,
                    created_at
                FROM business_profiles
                WHERE 1=1
            """

            business_params = []

            if query:

                search_term = f"%{query}%"

                business_query += """
                    AND (
                        business_name ILIKE %s
                        OR description ILIKE %s
                        OR category ILIKE %s
                        OR location ILIKE %s
                    )
                """

                business_params.extend([
                    search_term,
                    search_term,
                    search_term,
                    search_term
                ])

            if category:

                business_query += """
                    AND category ILIKE %s
                """

                business_params.append(
                    f"%{category}%"
                )

            if location:

                business_query += """
                    AND location ILIKE %s
                """

                business_params.append(
                    f"%{location}%"
                )

            if query or category or location:

                business_query += """
                    ORDER BY id DESC
                """

                cursor.execute(
                    business_query,
                    business_params
                )

                businesses = cursor.fetchall()

            # =================================================
            # SEARCH COMMUNITIES
            # =================================================

            if query:

                search_term = f"%{query}%"

                cursor.execute(
                    """
                    SELECT
                        c.id,
                        c.owner_id,
                        c.name,
                        c.description,
                        c.category,
                        c.created_at,
                        u.name AS owner_name,
                        (
                            SELECT COUNT(*)
                            FROM community_members cm
                            WHERE cm.community_id = c.id
                        ) AS member_count
                    FROM communities c
                    LEFT JOIN users u
                        ON c.owner_id = u.id
                    WHERE
                        c.name ILIKE %s
                        OR c.description ILIKE %s
                        OR c.category ILIKE %s
                    ORDER BY c.id DESC
                    """,
                    (
                        search_term,
                        search_term,
                        search_term
                    )
                )

                communities = cursor.fetchall()

        for business in businesses:

            business["phone_link"] = make_phone_link(
                business.get("phone")
            )

            business["whatsapp_link"] = make_whatsapp_link(
                business.get("whatsapp")
            )

            business["website_link"] = make_website_link(
                business.get("website")
            )

        total_results = (
            len(posts)
            + len(businesses)
            + len(communities)
        )

        return render_template(
            "search.html",
            posts=posts,
            businesses=businesses,
            communities=communities,
            categories=categories,
            query=query,
            selected_category=category,
            location=location,
            total_results=total_results
        )

    except Exception:

        app.logger.exception(
            "Search error."
        )

        return render_template(
            "search.html",
            posts=[],
            businesses=[],
            communities=[],
            categories=[],
            query=query,
            selected_category=category,
            location=location,
            total_results=0
        )

    finally:
        close_db(conn)


# =========================================================
# CREATOR STUDIO
# =========================================================

ALLOWED_PROJECT_TYPES = [
    "General",
    "🎥 Video",
    "✍️ Blog",
    "📱 Social Media",
    "🎨 Artwork",
    "🎵 Music",
    "🎙️ Podcast",
    "🏪 Business Content",
    "Video",
    "Blog",
    "Social Media",
    "Artwork",
    "Music",
    "Podcast",
    "Business Content"
]

ALLOWED_PROJECT_STATUSES = [
    "Idea",
    "Draft",
    "In Production",
    "Published"
]


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

            if project_type not in ALLOWED_PROJECT_TYPES:
                project_type = "General"

            if status not in ALLOWED_PROJECT_STATUSES:
                status = "Idea"

            if not title:

                flash(
                    "Please enter a project title.",
                    "danger"
                )

                return redirect(url_for("creator_studio"))

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

            return redirect(url_for("creator_studio"))

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

        return redirect(url_for("workspace"))

    finally:
        close_db(conn)


# =========================================================
# VIEW CREATOR PROJECT
# =========================================================

@app.route("/creator-project/<int:project_id>")
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
                "Creator project not found.",
                "danger"
            )

            return redirect(url_for("creator_studio"))

        return render_template(
            "view_creator_project.html",
            project=project,
            user_name=session.get("user_name")
        )

    except Exception as error:

        app.logger.exception(
            "VIEW CREATOR PROJECT FAILED | project_id=%s | user_id=%s | error=%s",
            project_id,
            session.get("user_id"),
            error
        )

        flash(
            "Unable to open this creator project right now.",
            "danger"
        )

        return redirect(url_for("creator_studio"))

    finally:
        close_db(conn)


# =========================================================
# PROJECT URL ALIAS
# =========================================================

@app.route("/project/<int:project_id>")
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

            return redirect(url_for("creator_studio"))

        if request.method == "GET":

            return render_template(
                "edit_creator_project.html",
                project=project,
                user_name=session.get("user_name")
            )

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

        if project_type not in ALLOWED_PROJECT_TYPES:
            project_type = "General"

        if status not in ALLOWED_PROJECT_STATUSES:
            status = "Idea"

        if not title:

            flash(
                "Project title is required.",
                "danger"
            )

            project["title"] = title
            project["description"] = description
            project["project_type"] = project_type
            project["status"] = status

            return render_template(
                "edit_creator_project.html",
                project=project,
                user_name=session.get("user_name")
            )

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

        if updated != 1:

            conn.rollback()

            flash(
                "Unable to update the creator project.",
                "danger"
            )

            return redirect(
                url_for(
                    "edit_creator_project",
                    project_id=project_id
                )
            )

        conn.commit()

        flash(
            "Creator project updated successfully.",
            "success"
        )

        return redirect(
            url_for(
                "view_creator_project",
                project_id=project_id
            )
        )

    except Exception:

        if conn:
            conn.rollback()

        app.logger.exception(
            "Edit Creator Project error | project_id=%s | user_id=%s",
            project_id,
            session.get("user_id")
        )

        flash(
            "Unable to edit creator project right now. Please try again.",
            "danger"
        )

        return redirect(url_for("creator_studio"))

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

            return redirect(url_for("creator_studio"))

        conn.commit()

        flash(
            "Creator project deleted successfully.",
            "success"
        )

        return redirect(url_for("creator_studio"))

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

        return redirect(url_for("creator_studio"))

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

            whatsapp = request.form.get(
                "whatsapp",
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

                return redirect(url_for("business_space"))

            if not category:

                flash(
                    "Please select a business category.",
                    "danger"
                )

                return redirect(url_for("business_space"))

            whatsapp_clean = (
                whatsapp
                .strip()
                .replace(" ", "")
                .replace("-", "")
                .replace("(", "")
                .replace(")", "")
            )

            if whatsapp_clean:

                if whatsapp_clean.startswith("+234"):
                    whatsapp_clean = whatsapp_clean[1:]

                elif whatsapp_clean.startswith("234"):
                    pass

                elif whatsapp_clean.startswith("0"):
                    whatsapp_clean = (
                        "234" +
                        whatsapp_clean[1:]
                    )

                else:
                    whatsapp_clean = (
                        "234" +
                        whatsapp_clean
                    )

                whatsapp = whatsapp_clean

            else:
                whatsapp = ""

            with conn.cursor(
                cursor_factory=RealDictCursor
            ) as cursor:

                cursor.execute(
                    """
                    SELECT id
                    FROM business_profiles
                    WHERE user_id = %s
                    ORDER BY id DESC
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
                            whatsapp = %s,
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
                            whatsapp,
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
                            whatsapp,
                            location,
                            website,
                            created_at
                        )
                        VALUES
                        (
                            %s, %s, %s, %s,
                            %s, %s, %s, %s, %s
                        )
                        """,
                        (
                            session["user_id"],
                            business_name,
                            description,
                            category,
                            phone,
                            whatsapp,
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

            return redirect(url_for("business_space"))

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT *
                FROM business_profiles
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (session["user_id"],)
            )

            business = cursor.fetchone()

        whatsapp_link = make_whatsapp_link(
            business.get("whatsapp")
            if business
            else None
        )

        business_upgrade = {
            "available": True,
            "price": "₦2,000",
            "period": "month",
            "features": [
                "Enhanced business visibility",
                "Better business discovery",
                "Enhanced customer contact options",
                "Business profile website support",
                "Premium business profile features"
            ]
        }

        is_business_premium = False

        return render_template(
            "business_space.html",
            business=business,
            whatsapp_link=whatsapp_link,
            business_upgrade=business_upgrade,
            is_business_premium=is_business_premium,
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

        return redirect(url_for("workspace"))

    finally:
        close_db(conn)


# =========================================================
# PUBLIC BUSINESS DIRECTORY
# =========================================================

@app.route("/businesses")
def businesses():

    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    location = request.args.get("location", "").strip()

    conn = None

    try:

        conn = get_db()

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cur:

            query = """
                SELECT
                    id,
                    business_name,
                    description,
                    category,
                    phone,
                    whatsapp,
                    location,
                    website,
                    created_at
                FROM business_profiles
                WHERE 1=1
            """

            params = []

            if q:

                query += """
                    AND (
                        business_name ILIKE %s
                        OR description ILIKE %s
                        OR category ILIKE %s
                        OR location ILIKE %s
                    )
                """

                search_term = f"%{q}%"

                params.extend([
                    search_term,
                    search_term,
                    search_term,
                    search_term
                ])

            if category:

                query += " AND category ILIKE %s"

                params.append(f"%{category}%")

            if location:

                query += " AND location ILIKE %s"

                params.append(f"%{location}%")

            query += " ORDER BY created_at DESC"

            cur.execute(query, params)

            businesses_list = cur.fetchall()

            cur.execute("""
                SELECT DISTINCT category
                FROM business_profiles
                WHERE category IS NOT NULL
                  AND TRIM(category) <> ''
                ORDER BY category ASC
            """)

            categories = cur.fetchall()

        for business in businesses_list:

            business["phone_link"] = make_phone_link(
                business.get("phone")
            )

            business["whatsapp_link"] = make_whatsapp_link(
                business.get("whatsapp")
            )

            business["website_link"] = make_website_link(
                business.get("website")
            )

        return render_template(
            "businesses.html",
            businesses=businesses_list,
            categories=categories,
            q=q,
            selected_category=category,
            location=location
        )

    except Exception as error:

        app.logger.exception(
            "BUSINESS DIRECTORY ERROR: %s",
            error
        )

        flash(
            "Unable to load business directory.",
            "error"
        )

        return render_template(
            "businesses.html",
            businesses=[],
            categories=[],
            q=q,
            selected_category=category,
            location=location
        )

    finally:
        close_db(conn)


# =========================================================
# PUBLIC BUSINESS PROFILE
# =========================================================

@app.route("/business/<int:business_id>")
def public_business_profile(business_id):

    conn = None

    try:

        conn = get_db()

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    business_name,
                    description,
                    category,
                    phone,
                    whatsapp,
                    location,
                    website,
                    created_at
                FROM business_profiles
                WHERE id = %s
                LIMIT 1
                """,
                (business_id,)
            )

            business = cursor.fetchone()

        if not business:
            return "Business profile not found.", 404

        whatsapp_link = make_whatsapp_link(
            business.get("whatsapp")
        )

        phone_link = make_phone_link(
            business.get("phone")
        )

        business["website"] = make_website_link(
            business.get("website")
        )

        return render_template(
            "public_business_profile.html",
            business=business,
            whatsapp_link=whatsapp_link,
            phone_link=phone_link
        )

    except Exception as error:

        app.logger.exception(
            "PUBLIC BUSINESS PROFILE FAILED | business_id=%s | error=%s",
            business_id,
            error
        )

        return "Unable to load business profile.", 500

    finally:
        close_db(conn)


# =========================================================
# BUSINESS PREMIUM UPGRADE
# =========================================================

@app.route("/upgrade")
@login_required
def upgrade():

    business_upgrade = {
        "price": "₦2,000",
        "period": "month",
        "features": [
            "Enhanced business visibility",
            "Better business discovery",
            "Enhanced customer contact options",
            "Business profile website support",
            "Premium business profile features"
        ]
    }

    return render_template(
        "upgrade.html",
        business_upgrade=business_upgrade,
        user_name=session.get("user_name")
    )


# =========================================================
# COMMUNITIES - PUBLIC DIRECTORY
# =========================================================

@app.route(
    "/communities",
    methods=["GET", "POST"]
)
def communities():

    conn = None

    user_id = session.get("user_id")

    try:

        conn = get_db()

        # =====================================================
        # CREATE COMMUNITY
        # =====================================================

        if request.method == "POST":

            if not user_id:

                flash(
                    "Please login or create an account before creating a community.",
                    "warning"
                )

                return redirect(
                    url_for(
                        "login",
                        next=url_for("communities")
                    )
                )

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

                return redirect(url_for("communities"))

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
                        user_id,
                        name,
                        description,
                        category,
                        datetime.utcnow()
                    )
                )

                result = cursor.fetchone()

                if not result:
                    raise RuntimeError(
                        "Community was not created."
                    )

                community_id = result[0]

                cursor.execute(
                    """
                    INSERT INTO community_members
                    (
                        community_id,
                        user_id,
                        joined_at
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (community_id, user_id)
                    DO NOTHING
                    """,
                    (
                        community_id,
                        user_id,
                        datetime.utcnow()
                    )
                )

            conn.commit()

            flash(
                "Community created successfully.",
                "success"
            )

            return redirect(
                url_for(
                    "community_detail",
                    community_id=community_id
                )
            )

        # =====================================================
        # PUBLIC COMMUNITY DIRECTORY
        # =====================================================

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT
                    c.id,
                    c.owner_id,
                    c.name,
                    c.description,
                    c.category,
                    c.created_at,
                    u.name AS owner_name,
                    (
                        SELECT COUNT(*)
                        FROM community_members cm
                        WHERE cm.community_id = c.id
                    ) AS member_count
                FROM communities AS c
                LEFT JOIN users AS u
                    ON c.owner_id = u.id
                ORDER BY c.id DESC
                """
            )

            all_communities = cursor.fetchall()

            my_communities = []

            if user_id:

                cursor.execute(
                    """
                    SELECT
                        c.id,
                        c.owner_id,
                        c.name,
                        c.description,
                        c.category,
                        c.created_at,
                        u.name AS owner_name,
                        (
                            SELECT COUNT(*)
                            FROM community_members cm2
                            WHERE cm2.community_id = c.id
                        ) AS member_count
                    FROM communities AS c
                    INNER JOIN community_members AS cm
                        ON c.id = cm.community_id
                    LEFT JOIN users AS u
                        ON c.owner_id = u.id
                    WHERE cm.user_id = %s
                    ORDER BY c.id DESC
                    """,
                    (user_id,)
                )

                my_communities = cursor.fetchall()

        joined_community_ids = {
            community["id"]
            for community in my_communities
        }

        return render_template(
            "communities.html",
            communities=all_communities,
            my_communities=my_communities,
            joined_community_ids=joined_community_ids,
            user_name=session.get("user_name"),
            is_logged_in=bool(user_id)
        )

    except Exception as error:

        if conn:
            conn.rollback()

        app.logger.exception(
            "COMMUNITIES PAGE FAILED | user_id=%s | error=%s",
            user_id,
            error
        )

        return (
            """
            <!DOCTYPE html>
            <html lang="en">

            <head>
                <meta charset="UTF-8">
                <meta name="viewport"
                      content="width=device-width, initial-scale=1.0">

                <title>
                    Communities Error | NijaWebbies
                </title>

                <style>
                    body {
                        font-family: Arial, sans-serif;
                        background: #f5f7fb;
                        margin: 0;
                        padding: 30px 20px;
                        color: #111827;
                    }

                    .box {
                        max-width: 700px;
                        margin: 50px auto;
                        background: white;
                        padding: 30px;
                        border-radius: 16px;
                        box-shadow: 0 10px 30px rgba(0,0,0,.08);
                    }

                    h1 {
                        color: #b91c1c;
                    }

                    .error {
                        background: #fef2f2;
                        border: 1px solid #fecaca;
                        padding: 15px;
                        border-radius: 10px;
                        word-break: break-word;
                    }

                    a {
                        display: inline-block;
                        margin-top: 20px;
                        background: #16a34a;
                        color: white;
                        text-decoration: none;
                        padding: 12px 18px;
                        border-radius: 8px;
                    }
                </style>
            </head>

            <body>

                <div class="box">

                    <h1>
                        Communities could not load
                    </h1>

                    <p>
                        NijaWebbies reached the Communities
                        route, but an error occurred.
                    </p>

                    <div class="error">
            """
            + str(error)
            + """
                    </div>

                    <a href="/">
                        ← Back to NijaWebbies
                    </a>

                    <a href="/workspace"
                       style="margin-left:8px;background:#2563eb;">
                        Workspace
                    </a>

                </div>

            </body>

            </html>
            """,
            500
        )

    finally:
        close_db(conn)


# =========================================================
# COMMUNITY DETAILS - PUBLIC
# =========================================================

@app.route("/community/<int:community_id>")
def community_detail(community_id):

    conn = None

    user_id = session.get("user_id")

    try:

        conn = get_db()

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            # =================================================
            # COMMUNITY
            # =================================================

            cursor.execute(
                """
                SELECT
                    c.id,
                    c.owner_id,
                    c.name,
                    c.description,
                    c.category,
                    c.created_at,
                    u.name AS owner_name
                FROM communities AS c
                LEFT JOIN users AS u
                    ON c.owner_id = u.id
                WHERE c.id = %s
                LIMIT 1
                """,
                (community_id,)
            )

            community = cursor.fetchone()

            if not community:

                flash(
                    "Community not found.",
                    "danger"
                )

                return redirect(url_for("communities"))

            # =================================================
            # MEMBER COUNT
            # =================================================

            cursor.execute(
                """
                SELECT COUNT(*) AS member_count
                FROM community_members
                WHERE community_id = %s
                """,
                (community_id,)
            )

            member_result = cursor.fetchone()

            member_count = int(
                member_result["member_count"]
                if member_result
                else 0
            )

            # =================================================
            # CURRENT USER MEMBERSHIP
            # =================================================

            membership = None
            is_member = False

            if user_id:

                cursor.execute(
                    """
                    SELECT
                        id,
                        joined_at
                    FROM community_members
                    WHERE community_id = %s
                      AND user_id = %s
                    LIMIT 1
                    """,
                    (
                        community_id,
                        user_id
                    )
                )

                membership = cursor.fetchone()

                is_member = membership is not None

            # =================================================
            # MEMBERS
            # =================================================

            cursor.execute(
                """
                SELECT
                    u.id,
                    u.name,
                    cm.joined_at
                FROM community_members AS cm
                INNER JOIN users AS u
                    ON cm.user_id = u.id
                WHERE cm.community_id = %s
                ORDER BY cm.joined_at ASC
                """,
                (community_id,)
            )

            members = cursor.fetchall()

            # =================================================
            # COMMUNITY DISCUSSIONS
            # =================================================

            cursor.execute(
                """
                SELECT
                    cp.id,
                    cp.community_id,
                    cp.user_id,
                    cp.content,
                    cp.created_at,
                    u.name AS author_name
                FROM community_posts AS cp
                INNER JOIN users AS u
                    ON cp.user_id = u.id
                WHERE cp.community_id = %s
                ORDER BY cp.id DESC
                """,
                (community_id,)
            )

            discussions = cursor.fetchall()

            # =================================================
            # COMMUNITY COMMENTS AND REPLIES
            # =================================================

            cursor.execute(
                """
                SELECT
                    cc.id,
                    cc.community_post_id,
                    cc.user_id,
                    cc.content,
                    cc.created_at,
                    cc.parent_comment_id,
                    u.name AS author_name
                FROM community_comments AS cc
                INNER JOIN users AS u
                    ON cc.user_id = u.id
                INNER JOIN community_posts AS cp
                    ON cc.community_post_id = cp.id
                WHERE cp.community_id = %s
                ORDER BY cc.id ASC
                """,
                (community_id,)
            )

            comments = cursor.fetchall()

        # =====================================================
        # GROUP TOP-LEVEL COMMENTS BY DISCUSSION
        # =====================================================

        comments_by_post = {}

        # =====================================================
        # GROUP REPLIES BY PARENT COMMENT
        # =====================================================

        replies_by_comment = {}

        for comment in comments:

            if comment["parent_comment_id"] is None:

                comments_by_post.setdefault(
                    comment["community_post_id"],
                    []
                ).append(comment)

            else:

                replies_by_comment.setdefault(
                    comment["parent_comment_id"],
                    []
                ).append(comment)

        return render_template(
            "community_detail.html",
            community=community,
            member_count=member_count,
            is_member=is_member,
            membership=membership,
            members=members,
            discussions=discussions,
            comments_by_post=comments_by_post,
            replies_by_comment=replies_by_comment,
            current_user_id=user_id,
            user_name=session.get("user_name"),
            is_logged_in=bool(user_id)
        )

    except Exception as error:

        if conn:
            conn.rollback()

        app.logger.exception(
            "COMMUNITY DETAIL FAILED | community_id=%s | user_id=%s | error=%s",
            community_id,
            user_id,
            error
        )

        return (
            """
            <!DOCTYPE html>
            <html lang="en">

            <head>

                <meta charset="UTF-8">

                <meta name="viewport"
                      content="width=device-width, initial-scale=1.0">

                <title>
                    Community Error | NijaWebbies
                </title>

                <style>

                    body {
                        font-family: Arial, sans-serif;
                        background: #f5f7fb;
                        margin: 0;
                        padding: 30px 20px;
                        color: #111827;
                    }

                    .box {
                        max-width: 700px;
                        margin: 50px auto;
                        background: white;
                        padding: 30px;
                        border-radius: 16px;
                        box-shadow: 0 10px 30px rgba(0,0,0,.08);
                    }

                    h1 {
                        color: #b91c1c;
                    }

                    .error {
                        background: #fef2f2;
                        border: 1px solid #fecaca;
                        padding: 15px;
                        border-radius: 10px;
                        word-break: break-word;
                    }

                    a {
                        display: inline-block;
                        margin-top: 20px;
                        background: #16a34a;
                        color: white;
                        text-decoration: none;
                        padding: 12px 18px;
                        border-radius: 8px;
                    }

                </style>

            </head>

            <body>

                <div class="box">

                    <h1>
                        Community could not load
                    </h1>

                    <p>
                        NijaWebbies found the community route,
                        but an error occurred while loading it.
                    </p>

                    <div class="error">
            """
            + str(error)
            + """
                    </div>

                    <a href="/communities">
                        ← Back to Communities
                    </a>

                    <a href="/workspace"
                       style="margin-left:8px;background:#2563eb;">
                        Workspace
                    </a>

                </div>

            </body>

            </html>
            """,
            500
        )

    finally:
        close_db(conn)


# =========================================================
# CREATE COMMUNITY DISCUSSION
# =========================================================

@app.route(
    "/community/<int:community_id>/post",
    methods=["POST"]
)
@login_required
def create_community_post(community_id):

    conn = None

    user_id = session.get("user_id")

    try:

        content = request.form.get(
            "content",
            ""
        ).strip()

        if not content:

            flash(
                "Please write something before posting.",
                "danger"
            )

            return redirect(
                url_for(
                    "community_detail",
                    community_id=community_id
                )
            )

        if len(content) > 5000:

            flash(
                "Community discussion cannot exceed 5,000 characters.",
                "danger"
            )

            return redirect(
                url_for(
                    "community_detail",
                    community_id=community_id
                )
            )

        conn = get_db()

        with conn.cursor() as cursor:

            # =================================================
            # CHECK COMMUNITY
            # =================================================

            cursor.execute(
                """
                SELECT
                    id,
                    owner_id
                FROM communities
                WHERE id = %s
                LIMIT 1
                """,
                (community_id,)
            )

            community = cursor.fetchone()

            if not community:

                flash(
                    "Community not found.",
                    "danger"
                )

                return redirect(url_for("communities"))

            # =================================================
            # CHECK MEMBERSHIP
            # =================================================

            cursor.execute(
                """
                SELECT id
                FROM community_members
                WHERE community_id = %s
                  AND user_id = %s
                LIMIT 1
                """,
                (
                    community_id,
                    user_id
                )
            )

            membership = cursor.fetchone()

            if not membership:

                flash(
                    "You must join this community before starting a discussion.",
                    "warning"
                )

                return redirect(
                    url_for(
                        "community_detail",
                        community_id=community_id
                    )
                )

            # =================================================
            # CREATE DISCUSSION
            # =================================================

            cursor.execute(
                """
                INSERT INTO community_posts
                (
                    community_id,
                    user_id,
                    content,
                    created_at
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    community_id,
                    user_id,
                    content,
                    datetime.utcnow()
                )
            )

        conn.commit()

        flash(
            "Your discussion has been posted.",
            "success"
        )

        return redirect(
            url_for(
                "community_detail",
                community_id=community_id
            )
        )

    except Exception as error:

        if conn:
            conn.rollback()

        app.logger.exception(
            "CREATE COMMUNITY POST FAILED | community_id=%s | user_id=%s | error=%s",
            community_id,
            user_id,
            error
        )

        flash(
            "Unable to publish your discussion right now.",
            "danger"
        )

        return redirect(
            url_for(
                "community_detail",
                community_id=community_id
            )
        )

    finally:
        close_db(conn)


# =========================================================
# DELETE COMMUNITY DISCUSSION
# =========================================================

@app.route(
    "/community-post/<int:post_id>/delete",
    methods=["POST"]
)
@login_required
def delete_community_post(post_id):

    conn = None

    user_id = session.get("user_id")

    try:

        conn = get_db()

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT
                    cp.id,
                    cp.community_id,
                    cp.user_id,
                    c.owner_id
                FROM community_posts AS cp
                INNER JOIN communities AS c
                    ON cp.community_id = c.id
                WHERE cp.id = %s
                LIMIT 1
                """,
                (post_id,)
            )

            post = cursor.fetchone()

            if not post:

                flash(
                    "Discussion not found.",
                    "danger"
                )

                return redirect(url_for("communities"))

            community_id = post["community_id"]

            if (
                post["user_id"] != user_id
                and post["owner_id"] != user_id
            ):

                flash(
                    "You do not have permission to delete this discussion.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "community_detail",
                        community_id=community_id
                    )
                )

            cursor.execute(
                """
                DELETE FROM community_posts
                WHERE id = %s
                """,
                (post_id,)
            )

        conn.commit()

        flash(
            "Discussion deleted successfully.",
            "success"
        )

        return redirect(
            url_for(
                "community_detail",
                community_id=community_id
            )
        )

    except Exception as error:

        if conn:
            conn.rollback()

        app.logger.exception(
            "DELETE COMMUNITY POST FAILED | post_id=%s | user_id=%s | error=%s",
            post_id,
            user_id,
            error
        )

        flash(
            "Unable to delete the discussion.",
            "danger"
        )

        return redirect(url_for("communities"))

    finally:
        close_db(conn)


# =========================================================
# CREATE COMMUNITY COMMENT
# =========================================================

@app.route(
    "/community-post/<int:post_id>/comment",
    methods=["POST"]
)
@login_required
def create_community_comment(post_id):

    conn = None

    user_id = session.get("user_id")
    community_id = None

    try:

        conn = get_db()

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            # =================================================
            # FIND DISCUSSION
            # =================================================

            cursor.execute(
                """
                SELECT
                    cp.id,
                    cp.community_id
                FROM community_posts AS cp
                WHERE cp.id = %s
                LIMIT 1
                """,
                (post_id,)
            )

            post = cursor.fetchone()

            if not post:

                flash(
                    "Discussion not found.",
                    "danger"
                )

                return redirect(
                    url_for("communities")
                )

            community_id = post["community_id"]

            # =================================================
            # GET COMMENT
            # =================================================

            content = request.form.get(
                "content",
                ""
            ).strip()

            if not content:

                flash(
                    "Please write a comment before posting.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "community_detail",
                        community_id=community_id
                    )
                )

            if len(content) > 2000:

                flash(
                    "Comment cannot exceed 2,000 characters.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "community_detail",
                        community_id=community_id
                    )
                )

            # =================================================
            # CHECK MEMBERSHIP
            # =================================================

            cursor.execute(
                """
                SELECT id
                FROM community_members
                WHERE community_id = %s
                  AND user_id = %s
                LIMIT 1
                """,
                (
                    community_id,
                    user_id
                )
            )

            membership = cursor.fetchone()

            if not membership:

                flash(
                    "You must join this community before commenting.",
                    "warning"
                )

                return redirect(
                    url_for(
                        "community_detail",
                        community_id=community_id
                    )
                )

            # =================================================
            # CREATE TOP-LEVEL COMMENT
            # =================================================

            cursor.execute(
                """
                INSERT INTO community_comments
                (
                    community_post_id,
                    user_id,
                    content,
                    created_at,
                    parent_comment_id
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    post_id,
                    user_id,
                    content,
                    datetime.utcnow(),
                    None
                )
            )

        conn.commit()

        flash(
            "Your comment has been posted.",
            "success"
        )

        return redirect(
            url_for(
                "community_detail",
                community_id=community_id
            )
        )

    except Exception as error:

        if conn:
            conn.rollback()

        app.logger.exception(
            "CREATE COMMUNITY COMMENT FAILED | post_id=%s | user_id=%s | error=%s",
            post_id,
            user_id,
            error
        )

        flash(
            "Unable to post your comment right now.",
            "danger"
        )

        if community_id:

            return redirect(
                url_for(
                    "community_detail",
                    community_id=community_id
                )
            )

        return redirect(
            url_for("communities")
        )

    finally:
        close_db(conn)


# =========================================================
# CREATE COMMUNITY COMMENT REPLY
# =========================================================

@app.route(
    "/community-comment/<int:comment_id>/reply",
    methods=["POST"]
)
@login_required
def create_community_comment_reply(comment_id):

    conn = None

    user_id = session.get("user_id")
    community_id = None

    try:

        conn = get_db()

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            # =================================================
            # FIND PARENT COMMENT
            # =================================================

            cursor.execute(
                """
                SELECT
                    cc.id,
                    cc.community_post_id,
                    cc.parent_comment_id,
                    cp.community_id,
                    c.owner_id
                FROM community_comments AS cc
                INNER JOIN community_posts AS cp
                    ON cc.community_post_id = cp.id
                INNER JOIN communities AS c
                    ON cp.community_id = c.id
                WHERE cc.id = %s
                LIMIT 1
                """,
                (comment_id,)
            )

            parent_comment = cursor.fetchone()

            if not parent_comment:

                flash(
                    "Comment not found.",
                    "danger"
                )

                return redirect(
                    url_for("communities")
                )

            community_id = parent_comment["community_id"]

            # =================================================
            # ONLY TOP-LEVEL COMMENTS CAN RECEIVE REPLIES
            # =================================================

            if parent_comment["parent_comment_id"] is not None:

                flash(
                    "Replies can only be made to a main comment.",
                    "warning"
                )

                return redirect(
                    url_for(
                        "community_detail",
                        community_id=community_id
                    )
                )

            # =================================================
            # GET REPLY
            # =================================================

            content = request.form.get(
                "content",
                ""
            ).strip()

            if not content:

                flash(
                    "Please write a reply before posting.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "community_detail",
                        community_id=community_id
                    )
                )

            if len(content) > 2000:

                flash(
                    "Reply cannot exceed 2,000 characters.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "community_detail",
                        community_id=community_id
                    )
                )

            # =================================================
            # CHECK MEMBERSHIP
            # =================================================

            cursor.execute(
                """
                SELECT id
                FROM community_members
                WHERE community_id = %s
                  AND user_id = %s
                LIMIT 1
                """,
                (
                    community_id,
                    user_id
                )
            )

            membership = cursor.fetchone()

            if not membership:

                flash(
                    "You must join this community before replying.",
                    "warning"
                )

                return redirect(
                    url_for(
                        "community_detail",
                        community_id=community_id
                    )
                )

            # =================================================
            # CREATE REPLY
            # =================================================

            cursor.execute(
                """
                INSERT INTO community_comments
                (
                    community_post_id,
                    user_id,
                    content,
                    created_at,
                    parent_comment_id
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    parent_comment["community_post_id"],
                    user_id,
                    content,
                    datetime.utcnow(),
                    comment_id
                )
            )

        conn.commit()

        flash(
            "Your reply has been posted.",
            "success"
        )

        return redirect(
            url_for(
                "community_detail",
                community_id=community_id
            )
        )

    except Exception as error:

        if conn:
            conn.rollback()

        app.logger.exception(
            "CREATE COMMUNITY REPLY FAILED | comment_id=%s | user_id=%s | error=%s",
            comment_id,
            user_id,
            error
        )

        flash(
            "Unable to post your reply right now.",
            "danger"
        )

        if community_id:

            return redirect(
                url_for(
                    "community_detail",
                    community_id=community_id
                )
            )

        return redirect(
            url_for("communities")
        )

    finally:
        close_db(conn)


# =========================================================
# DELETE COMMUNITY COMMENT
# =========================================================

@app.route(
    "/community-comment/<int:comment_id>/delete",
    methods=["POST"]
)
@login_required
def delete_community_comment(comment_id):

    conn = None

    user_id = session.get("user_id")
    community_id = None

    try:

        conn = get_db()

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            # =================================================
            # FIND COMMENT AND COMMUNITY
            # =================================================

            cursor.execute(
                """
                SELECT
                    cc.id,
                    cc.community_post_id,
                    cc.user_id,
                    cc.parent_comment_id,
                    cp.community_id,
                    c.owner_id
                FROM community_comments AS cc
                INNER JOIN community_posts AS cp
                    ON cc.community_post_id = cp.id
                INNER JOIN communities AS c
                    ON cp.community_id = c.id
                WHERE cc.id = %s
                LIMIT 1
                """,
                (comment_id,)
            )

            comment = cursor.fetchone()

            if not comment:

                flash(
                    "Comment not found.",
                    "danger"
                )

                return redirect(
                    url_for("communities")
                )

            community_id = comment["community_id"]

            # =================================================
            # CHECK PERMISSION
            # =================================================

            if (
                comment["user_id"] != user_id
                and comment["owner_id"] != user_id
            ):

                flash(
                    "You do not have permission to delete this comment.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "community_detail",
                        community_id=community_id
                    )
                )

            # =================================================
            # DELETE COMMENT
            # =================================================
            # If this is a parent comment, PostgreSQL will also
            # delete its replies because parent_comment_id uses
            # ON DELETE CASCADE.

            cursor.execute(
                """
                DELETE FROM community_comments
                WHERE id = %s
                """,
                (comment_id,)
            )

        conn.commit()

        flash(
            "Comment deleted successfully.",
            "success"
        )

        return redirect(
            url_for(
                "community_detail",
                community_id=community_id
            )
        )

    except Exception as error:

        if conn:
            conn.rollback()

        app.logger.exception(
            "DELETE COMMUNITY COMMENT FAILED | comment_id=%s | user_id=%s | error=%s",
            comment_id,
            user_id,
            error
        )

        flash(
            "Unable to delete the comment.",
            "danger"
        )

        if community_id:

            return redirect(
                url_for(
                    "community_detail",
                    community_id=community_id
                )
            )

        return redirect(
            url_for("communities")
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

        user_id = session.get("user_id")

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT id
                FROM communities
                WHERE id = %s
                LIMIT 1
                """,
                (community_id,)
            )

            community = cursor.fetchone()

            if not community:

                flash(
                    "Community not found.",
                    "danger"
                )

                return redirect(url_for("communities"))

            cursor.execute(
                """
                INSERT INTO community_members
                (
                    community_id,
                    user_id,
                    joined_at
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (community_id, user_id)
                DO NOTHING
                """,
                (
                    community_id,
                    user_id,
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
            url_for(
                "community_detail",
                community_id=community_id
            )
        )

    except Exception as error:

        if conn:
            conn.rollback()

        app.logger.exception(
            "JOIN COMMUNITY FAILED | community_id=%s | user_id=%s | error=%s",
            community_id,
            session.get("user_id"),
            error
        )

        flash(
            "Unable to join the community right now.",
            "danger"
        )

        return redirect(url_for("communities"))

    finally:
        close_db(conn)


# =========================================================
# LEAVE COMMUNITY
# =========================================================

@app.route(
    "/leave-community/<int:community_id>",
    methods=["POST"]
)
@login_required
def leave_community(community_id):

    conn = None

    user_id = session.get("user_id")

    try:

        conn = get_db()

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    owner_id
                FROM communities
                WHERE id = %s
                LIMIT 1
                """,
                (community_id,)
            )

            community = cursor.fetchone()

            if not community:

                flash(
                    "Community not found.",
                    "danger"
                )

                return redirect(url_for("communities"))

            # Owner cannot leave their own community.
            if community["owner_id"] == user_id:

                flash(
                    "The community owner cannot leave the community.",
                    "warning"
                )

                return redirect(
                    url_for(
                        "community_detail",
                        community_id=community_id
                    )
                )

            cursor.execute(
                """
                DELETE FROM community_members
                WHERE community_id = %s
                  AND user_id = %s
                """,
                (
                    community_id,
                    user_id
                )
            )

            removed = cursor.rowcount

        conn.commit()

        if removed:

            flash(
                "You have left the community.",
                "success"
            )

        else:

            flash(
                "You are not a member of this community.",
                "warning"
            )

        return redirect(
            url_for(
                "community_detail",
                community_id=community_id
            )
        )

    except Exception as error:

        if conn:
            conn.rollback()

        app.logger.exception(
            "LEAVE COMMUNITY FAILED | community_id=%s | user_id=%s | error=%s",
            community_id,
            user_id,
            error
        )

        flash(
            "Unable to leave the community right now.",
            "danger"
        )

        return redirect(
            url_for(
                "community_detail",
                community_id=community_id
            )
        )

    finally:
        close_db(conn)


# =========================================================
# FREE ONLINE TOOLS
# =========================================================

@app.route("/tools")
def tools():

    return render_template("tools.html")


# =========================================================
# 404 ERROR
# =========================================================

@app.errorhandler(404)
def page_not_found(error):

    return """
<!DOCTYPE html>
<html>

<head>

    <meta name="viewport"
          content="width=device-width, initial-scale=1">

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
# 500 ERROR
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

    <meta name="viewport"
          content="width=device-width, initial-scale=1">

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
