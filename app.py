from flask import Flask, render_template, request

app = Flask(__name__)

app.config["SECRET_KEY"] = "change-this-later"


# =========================
# HOME
# =========================

@app.route("/")
def home():
    return render_template("home.html")


# =========================
# SEARCH
# =========================

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()

    if query:
        return f"""
        <h1>NijaWebbies Search</h1>
        <p>You searched for: <strong>{query}</strong></p>
        <p>Our search engine is being built.</p>
        <a href="/">← Back to NijaWebbies</a>
        """

    return """
    <h1>NijaWebbies Search</h1>
    <p>Enter something to search.</p>
    <a href="/">← Back to NijaWebbies</a>
    """


# =========================
# LOGIN
# =========================

@app.route("/login")
def login():
    return """
    <h1>NijaWebbies Login</h1>
    <p>Login system coming next.</p>
    <a href="/">← Back to NijaWebbies</a>
    """


# =========================
# REGISTRATION
# =========================

@app.route("/register")
def register():
    return """
    <h1>Join NijaWebbies</h1>
    <p>Create your free NijaWebbies account.</p>
    <p>Registration system coming next.</p>
    <a href="/">← Back to NijaWebbies</a>
    """


# =========================
# FREE TOOLS
# =========================

@app.route("/tools")
def tools():
    return """
    <h1>NijaWebbies Free Tools</h1>

    <p>Our free online tools are being built.</p>

    <ul>
        <li>Text Tools</li>
        <li>Writing Tools</li>
        <li>Business Tools</li>
        <li>Creator Tools</li>
        <li>Image Tools</li>
        <li>Productivity Tools</li>
    </ul>

    <a href="/">← Back to NijaWebbies</a>
    """


# =========================
# RUN APPLICATION
# =========================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
