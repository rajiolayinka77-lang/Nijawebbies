from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta

app = Flask(__name__)

# =========================================================
# APP CONFIGURATION
# =========================================================

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "nijawebbies-development-secret-change-this"
)

# Keep login sessions for 30 days when "Remember me" is used
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# Safer cookie settings for production
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Render uses HTTPS
if os.environ.get("RENDER"):
    app.config["SESSION_COOKIE_SECURE"] = True

DATABASE = "nijawebbies.db"


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row

    # Helps SQLite handle concurrent requests better
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")

    return conn


def init_db():

    conn = get_db()

    # =====================================================
    # USERS
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # =====================================================
    # BLOG POSTS
    # =====================================================

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

    # =====================================================
    # CREATOR PROJECTS
    # =====================================================

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

    # =====================================================
    # SAFE DATABASE UPGRADE
    # =====================================================

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

    # =====================================================
    # BUSINESS PROFILES
    # =====================================================

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

    # =====================================================
    # COMMUNITIES
    # =====================================================

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

    # =====================================================
    # COMMUNITY MEMBERS
    # =====================================================

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


# Initialize database
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

            return redirect(
                url_for(
                    "login",
                    next=request.path
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

        # ---------------------------------------------
        # VALIDATION
        # ---------------------------------------------

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

        # ---------------------------------------------
        # CHECK EXISTING ACCOUNT
        # ---------------------------------------------

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

        # ---------------------------------------------
        # HASH PASSWORD
        # ---------------------------------------------

        hashed_password = generate_password_hash(
            password
        )

        try:

            conn.execute("""
                INSERT INTO users
                (
                    name,
                    email,
                    password,
                    created_at
                )
                VALUES (?, ?, ?, ?)
            """, (
                name,
                email,
                hashed_password,
                datetime.utcnow().isoformat()
            ))

            conn.commit()

        except sqlite3.IntegrityError:

            conn.rollback()
            conn.close()

            flash(
                "An account with this email already exists.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        conn.close()

        flash(
            "Account created successfully. Please login.",
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

    # If already logged in, go straight to workspace
    if request.method == "GET":

        if "user_id" in session:

            return redirect(
                url_for("workspace")
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

        # ---------------------------------------------
        # BASIC VALIDATION
        # ---------------------------------------------

        if not email or not password:

            flash(
                "Please enter your email and password.",
                "danger"
            )

            return render_template(
                "login.html",
                email=email
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

        # ---------------------------------------------
        # CHECK PASSWORD
        # ---------------------------------------------

        password_valid = False

        if user:

            try:

                password_valid = check_password_hash(
                    user["password"],
                    password
                )

            except Exception:

                password_valid = False

        if user and password_valid:

            # Remove old session information
            session.clear()

            # Save user information
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]

            # -----------------------------------------
            # REMEMBER LOGIN
            # -----------------------------------------

            if remember:

                session.permanent = True

            else:

                session.permanent = False

            # -----------------------------------------
            # OPTIONAL REDIRECT
            # -----------------------------------------

            next_page = request.args.get(
                "next"
            )

            if next_page and next_page.startswith("/"):

                return redirect(next_page)

            return redirect(
                url_for("workspace")
            )

        # ---------------------------------------------
        # INVALID LOGIN
        # ---------------------------------------------

        flash(
            "Invalid email or password. Please check your details and try again.",
            "danger"
        )

        return render_template(
            "login.html",
            email=email
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

    posts = conn.execute("""
        SELECT *
        FROM posts
        WHERE user_id = ?
        ORDER BY id DESC
    """, (
        session["user_id"],
    )).fetchall()

    creator_projects = conn.execute("""
        SELECT *
        FROM creator_projects
        WHERE user_id = ?
        ORDER BY id DESC
    """, (
        session["user_id"],
    )).fetchall()

    business = conn.execute("""
        SELECT *
        FROM business_profiles
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (
        session["user_id"],
    )).fetchone()

    communities = conn.execute("""
        SELECT communities.*
        FROM communities
        JOIN community_members
        ON communities.id = community_members.community_id
        WHERE community_members.user_id = ?
        ORDER BY communities.id DESC
    """, (
        session["user_id"],
    )).fetchall()

    conn.close()

    return render_template(
        "workspace.html",
        posts=posts,
        creator_projects=creator_projects,
        business=business,
        communities=communities,
        user_name=session.get("user_name"),
        user_email=session.get("user_email")
    )


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

        conn = get_db()

        conn.execute("""
            INSERT INTO posts
            (
                user_id,
                title,
                content,
                created_at
            )
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

        return redirect(
            url_for("workspace")
        )

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

        return (
            "Post not found or you do not have permission.",
            404
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
            SET
                title = ?,
                content = ?
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

        return redirect(
            url_for("workspace")
        )

    conn.close()

    return render_template(
        "edit_post.html",
        post=post
    )


# =========================================================
# DELETE POST
# =========================================================

@app.route(
    "/delete-post/<int:post_id>",
    methods=["POST"]
)
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

        return redirect(
            url_for("workspace")
        )

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

    return redirect(
        url_for("workspace")
    )


# =========================================================
# PUBLIC BLOG
# =========================================================

@app.route("/blog")
def blog():

    conn = get_db()

    posts = conn.execute("""
        SELECT
            posts.*,
            users.name
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
        SELECT
            posts.*,
            users.name
        FROM posts
        JOIN users
        ON posts.user_id = users.id
        WHERE posts.id = ?
    """, (
        post_id,
    )).fetchone()

    conn.close()

    if not post:

        return (
            "Post not found",
            404
        )

    return render_template(
        "view_post.html",
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

        posts = conn.execute("""
            SELECT
                posts.*,
                users.name
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
# CREATOR STUDIO
# =========================================================

@app.route(
    "/creator-studio",
    methods=["GET", "POST"]
)
@login_required
def creator_studio():

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

            conn.close()

            flash(
                "Please enter a project title.",
                "danger"
            )

            return redirect(
                url_for("creator_studio")
            )

        conn.execute("""
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
        """, (
            session["user_id"],
            title,
            description,
            project_type,
            status,
            datetime.utcnow().isoformat()
        ))

        conn.commit()
        conn.close()

        flash(
            "Creator project added successfully.",
            "success"
        )

        return redirect(
            url_for("creator_studio")
        )

    projects = conn.execute("""
        SELECT *
        FROM creator_projects
        WHERE user_id = ?
        ORDER BY id DESC
    """, (
        session["user_id"],
    )).fetchall()

    conn.close()

    return render_template(
        "creator_studio.html",
        projects=projects,
        user_name=session.get("user_name")
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

    conn = get_db()

    project = conn.execute("""
        SELECT *
        FROM creator_projects
        WHERE id = ?
        AND user_id = ?
    """, (
        project_id,
        session["user_id"]
    )).fetchone()

    if not project:

        conn.close()

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

            conn.close()

            flash(
                "Project title is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "edit_creator_project",
                    project_id=project_id
                )
            )

        conn.execute("""
            UPDATE creator_projects
            SET
                title = ?,
                description = ?,
                project_type = ?,
                status = ?
            WHERE id = ?
            AND user_id = ?
        """, (
            title,
            description,
            project_type,
            status,
            project_id,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        flash(
            "Creator project updated successfully.",
            "success"
        )

        return redirect(
            url_for("creator_studio")
        )

    conn.close()

    return render_template(
        "edit_creator_project.html",
        project=project,
        user_name=session.get("user_name")
    )


# =========================================================
# DELETE CREATOR PROJECT
# =========================================================

@app.route(
    "/delete-creator-project/<int:project_id>",
    methods=["POST"]
)
@login_required
def delete_creator_project(project_id):

    conn = get_db()

    project = conn.execute("""
        SELECT id
        FROM creator_projects
        WHERE id = ?
        AND user_id = ?
    """, (
        project_id,
        session["user_id"]
    )).fetchone()

    if not project:

        conn.close()

        flash(
            "Creator project not found.",
            "danger"
        )

        return redirect(
            url_for("creator_studio")
        )

    conn.execute("""
        DELETE FROM creator_projects
        WHERE id = ?
        AND user_id = ?
    """, (
        project_id,
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    flash(
        "Creator project deleted.",
        "success"
    )

    return redirect(
        url_for("creator_studio")
    )


# =========================================================
# BUSINESS SPACE
# =========================================================

@app.route(
    "/business-space",
    methods=["GET", "POST"]
)
@login_required
def business_space():

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

            conn.close()

            flash(
                "Business name is required.",
                "danger"
            )

            return redirect(
                url_for("business_space")
            )

        existing = conn.execute("""
            SELECT id
            FROM business_profiles
            WHERE user_id = ?
            LIMIT 1
        """, (
            session["user_id"],
        )).fetchone()

        if existing:

            conn.execute("""
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
            """, (
                business_name,
                description,
                category,
                phone,
                location,
                website,
                existing["id"],
                session["user_id"]
            ))

        else:

            conn.execute("""
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
            """, (
                session["user_id"],
                business_name,
                description,
                category,
                phone,
                location,
                website,
                datetime.utcnow().isoformat()
            ))

        conn.commit()
        conn.close()

        flash(
            "Business profile saved successfully.",
            "success"
        )

        return redirect(
            url_for("business_space")
        )

    business = conn.execute("""
        SELECT *
        FROM business_profiles
        WHERE user_id = ?
        LIMIT 1
    """, (
        session["user_id"],
    )).fetchone()

    conn.close()

    return render_template(
        "business_space.html",
        business=business,
        user_name=session.get("user_name")
    )


# =========================================================
# COMMUNITIES
# =========================================================

@app.route(
    "/communities",
    methods=["GET", "POST"]
)
@login_required
def communities():

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

            conn.close()

            flash(
                "Community name is required.",
                "danger"
            )

            return redirect(
                url_for("communities")
            )

        cursor = conn.execute("""
            INSERT INTO communities
            (
                owner_id,
                name,
                description,
                category,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            name,
            description,
            category,
            datetime.utcnow().isoformat()
        ))

        community_id = cursor.lastrowid

        conn.execute("""
            INSERT INTO community_members
            (
                community_id,
                user_id,
                joined_at
            )
            VALUES (?, ?, ?)
        """, (
            community_id,
            session["user_id"],
            datetime.utcnow().isoformat()
        ))

        conn.commit()
        conn.close()

        flash(
            "Community created successfully.",
            "success"
        )

        return redirect(
            url_for("communities")
        )

    all_communities = conn.execute("""
        SELECT
            communities.*,
            users.name AS owner_name
        FROM communities
        JOIN users
        ON communities.owner_id = users.id
        ORDER BY communities.id DESC
    """).fetchall()

    my_communities = conn.execute("""
        SELECT communities.*
        FROM communities
        JOIN community_members
        ON communities.id = community_members.community_id
        WHERE community_members.user_id = ?
        ORDER BY communities.id DESC
    """, (
        session["user_id"],
    )).fetchall()

    conn.close()

    return render_template(
        "communities.html",
        communities=all_communities,
        my_communities=my_communities,
        user_name=session.get("user_name")
    )


# =========================================================
# JOIN COMMUNITY
# =========================================================

@app.route(
    "/join-community/<int:community_id>",
    methods=["POST"]
)
@login_required
def join_community(community_id):

    conn = get_db()

    community = conn.execute("""
        SELECT id
        FROM communities
        WHERE id = ?
    """, (
        community_id,
    )).fetchone()

    if not community:

        conn.close()

        flash(
            "Community not found.",
            "danger"
        )

        return redirect(
            url_for("communities")
        )

    try:

        conn.execute("""
            INSERT INTO community_members
            (
                community_id,
                user_id,
                joined_at
            )
            VALUES (?, ?, ?)
        """, (
            community_id,
            session["user_id"],
            datetime.utcnow().isoformat()
        ))

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

    finally:

        conn.close()

    return redirect(
        url_for("communities")
    )


# =========================================================
# FREE ONLINE TOOLS
# =========================================================

@app.route("/tools")
def tools():

    return render_template(
        "tools.html"
    )


# =========================================================
# ERROR HANDLERS
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
        font-family:Arial;
        text-align:center;
        padding:50px;
        background:#f5f7fb;
    ">

        <h1>404</h1>

        <h2>Page not found</h2>

        <p>
            The page you are looking for does not exist.
        </p>

        <a href="/">
            ← Back to NijaWebbies
        </a>

    </body>
    </html>
    """, 404


@app.errorhandler(500)
def internal_server_error(error):

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport"
              content="width=device-width, initial-scale=1">
        <title>NijaWebbies - Error</title>
    </head>

    <body style="
        font-family:Arial;
        text-align:center;
        padding:50px;
        background:#f5f7fb;
    ">

        <h1>Something went wrong</h1>

        <p>
            NijaWebbies encountered an unexpected error.
        </p>

        <p>
            Please try again.
        </p>

        <a href="/workspace">
            ← Back to Workspace
        </a>

    </body>
    </html>
    """, 500


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
