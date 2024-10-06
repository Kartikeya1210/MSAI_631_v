from application import app
from flask import render_template

@app.route("/")
def index():
    return render_template("index.html", navindex=True)

@app.route("/catalog")
def catalog():
    return render_template("catalog.html", navcatalog=True)

@app.route("/reviews")
def reviews():
    return render_template("reviews.html", navreviews=True)

@app.route("/recommend")
def recommend():
    return render_template("recommend.html", navrecommend=True)

@app.route("/login")
def login():
    return render_template("login.html", navlogin=True)