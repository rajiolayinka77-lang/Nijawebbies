from flask import Flask, render_template

app = Flask(__name__)

app.config["SECRET_KEY"] = "change-this-later"

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/search")
def search():
    return "NijaWebbies Search is coming soon."


@app.route("/login")
def login():
    return "Login coming soon."


@app.route("/register")
def register():
    return "Registration coming soon."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
