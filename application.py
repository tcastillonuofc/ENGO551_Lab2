import os
import requests
import re

from flask import Flask, render_template, request, session, flash, redirect, url_for, jsonify, abort
from flask_session import Session
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash

def normalize_text(s):
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s

def get_google_books_data(book):
    """
    book should have: book.isbn

    Returns dict or None:
    {
        "title": ...,
        "author": ...,
        "publishedDate": ...,
        "ISBN_10": ...,
        "ISBN_13": ...,
        "reviewCount": ...,
        "averageRating": ...,
        "description": ...
    }
    """
    if book is None:
        return None

    try:
        res = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": f"isbn:{book.isbn}"},
            timeout=5
        )

        print("Google Books status:", res.status_code)

        if res.status_code != 200:
            print("Google Books body:", res.text)
            return None

        data = res.json()
        print("Google Books JSON response:")
        print(data)

        items = data.get("items", [])
        if not items:
            return None

        volume_info = items[0].get("volumeInfo", {})
        identifiers = volume_info.get("industryIdentifiers", [])

        isbn_10 = None
        isbn_13 = None

        for ident in identifiers:
            if ident.get("type") == "ISBN_10":
                isbn_10 = ident.get("identifier")
            elif ident.get("type") == "ISBN_13":
                isbn_13 = ident.get("identifier")

        authors = volume_info.get("authors", [])
        first_author = authors[0] if authors else None

        return {
            "title": volume_info.get("title"),
            "author": first_author,
            "publishedDate": volume_info.get("publishedDate"),
            "ISBN_10": isbn_10,
            "ISBN_13": isbn_13,
            "reviewCount": volume_info.get("ratingsCount"),
            "averageRating": volume_info.get("averageRating"),
            "description": volume_info.get("description")
        }

    except requests.RequestException as e:
        print("Google Books request failed:", e)
        return None

def summarize_with_gemini_under_50_words(book_title, description_text):
    if not description_text:
        return None

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Missing GEMINI_API_KEY")
        return None

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"Summarize this text using less than 50 words: {description_text}"
                    }
                ]
            }
        ]
    }

    try:
        resp = requests.post(
            url,
            params={"key": api_key},  # same as ?key=... in Postman
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=15
        )

        print("Gemini status:", resp.status_code)
        print("Gemini body:", resp.text)

        if resp.status_code != 200:
            return None

        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    except requests.RequestException as e:
        print("Gemini request failed:", e)
        return None

def get_google_books_api_data(isbn):
    """
    Returns a dict with Google Books metadata for the given ISBN,
    or None if no Google Books result is found.
    """
    try:
        res = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": f"isbn:{isbn}"},
            timeout=5
        )

        print("Google Books status:", res.status_code)

        if res.status_code != 200:
            print("Google Books body:", res.text)
            return None

        data = res.json()
        print("Google Books JSON response:")
        print(data)

        items = data.get("items", [])
        if not items:
            return None

        volume_info = items[0].get("volumeInfo", {})
        identifiers = volume_info.get("industryIdentifiers", [])

        isbn_10 = None
        isbn_13 = None

        for ident in identifiers:
            ident_type = ident.get("type")
            ident_value = ident.get("identifier")

            if ident_type == "ISBN_10":
                isbn_10 = ident_value
            elif ident_type == "ISBN_13":
                isbn_13 = ident_value

        authors = volume_info.get("authors", [])
        author = authors[0] if authors else None

        return {
            "title": volume_info.get("title"),
            "author": author,
            "publishedDate": volume_info.get("publishedDate"),
            "ISBN_10": isbn_10,
            "ISBN_13": isbn_13,
            "reviewCount": volume_info.get("ratingsCount"),
            "averageRating": volume_info.get("averageRating"),
            "description": volume_info.get("description")
        }

    except requests.RequestException as e:
        print("Google Books request failed:", e)
        return None

app = Flask(__name__)  # This is the variable that is the source of the flask app

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

@app.route("/", methods=["GET"])
def index():
    return render_template("login.html")


@app.route("/home")
def home():
    if "username" not in session:
        return redirect("/")
    return render_template("home.html", username=session["username"])


@app.route("/authenticate", methods=["POST"])
def authenticate():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    action = request.form.get("action")

    if not username or not password:
        flash("Please enter your username and password.")
        return redirect("/")

    if action == "login":
        query = db.execute(
            text("SELECT * FROM accounts WHERE username = :username"),
            {"username": username}
        ).fetchone()

        # query is None if username not found
        # query.password contains the HASH (even though the column is named 'password')
        if query is None or not check_password_hash(query[2], password):
            flash("Invalid username or password.")
            return redirect("/")

        session["user_id"] = query[0]
        session["username"] = query[1].capitalize()
        return redirect(url_for("home"))

    elif action == "register":
        query = db.execute(text("""
            SELECT * FROM accounts WHERE username = :username
        """), {"username": username}).fetchone()

        if query is not None:
            flash("Username already exists.")
            return redirect("/")

        password_hash = generate_password_hash(password)
        db.execute(text("""
            INSERT INTO accounts (username, password)
            VALUES (:username, :password_hash)
        """), {"username": username, "password_hash": password_hash})
        db.commit()
        flash("Successfully registered.")
        return redirect("/")

    flash("Unknown action.")
    return redirect("/")


@app.route("/search", methods=["POST"])
def search():
    search = request.form.get("user_search", "")
    action = request.form.get("action")

    if action == "logout":
        session.clear()
        return render_template("login.html")

    if action == "search":
        if not search:
            flash("Please enter a search.")
            return redirect("/home")

        results = db.execute(text("""
            SELECT isbn, title, author, year
            FROM books
            WHERE isbn ILIKE '%' || :search || '%'
               OR title ILIKE '%' || :search || '%'
               OR author ILIKE '%' || :search || '%'
            ORDER BY year DESC
        """), {"search": search}).fetchall()

        return render_template(
            "results.html",
            results=results,
            search=search,
            username=session["username"]
        )

    flash("Unknown action.")
    return redirect("/home")


@app.route("/view_book", methods=["POST"])
def view_book():
    if "user_id" not in session:
        return redirect("/")

    isbn = request.form.get("isbn", "").strip()
    action = request.form.get("action")

    if action == "home":
        return redirect("/home")

    if action == "info":
        book = db.execute(
            text("""
                SELECT isbn, title, author, year
                FROM books
                WHERE isbn = :isbn
            """),
            {"isbn": isbn}
        ).fetchone()

        if book is None:
            flash("Book not found.")
            return redirect("/home")

        google_data = get_google_books_data(book)

        google_rating = None
        google_description = None

        if google_data:
            google_rating = {
                "average_rating": google_data.get("averageRating"),
                "ratings_count": google_data.get("reviewCount")
            }
            google_description = google_data.get("description")

        gemini_summary = summarize_with_gemini_under_50_words(book.title, google_description)

        fallback_description = None
        if not gemini_summary and google_description:
            fallback_description = " ".join(google_description.split())[:220] + "..."

        rating_row = db.execute(
            text("""
                 SELECT rating, comment
                 FROM ratings
                 WHERE userid = :userid
                   AND isbn = :isbn
                 """),
            {"userid": session["user_id"], "isbn": isbn}
        ).fetchone()

        user_rating = rating_row[0] if rating_row is not None else None
        user_comment = rating_row[1] if rating_row is not None else None

        other_ratings = db.execute(
            text("""
                 SELECT a.username, r.rating, r.comment
                 FROM ratings r
                 JOIN accounts a ON r.userid = a.id
                 WHERE r.isbn = :isbn
                   AND r.userid != :userid
                 ORDER BY r.rating DESC, a.username ASC
                 """),
            {"isbn": isbn, "userid": session["user_id"]}
        ).fetchall()

        return render_template(
            "viewbook.html",
            book=book,
            username=session.get("username"),
            user_rating=user_rating,
            user_comment=user_comment,
            other_ratings=other_ratings,
            gemini_summary=gemini_summary,
            fallback_description=fallback_description,
            google_rating=google_rating
        )

    flash("Unknown action.")
    return redirect("/home")


@app.route("/rate_book", methods=["POST"])
def rate_book():
    if "user_id" not in session:
        flash("Please log in to submit a rating.")
        return redirect("/")

    userid = session["user_id"]
    isbn = request.form.get("isbn", "").strip()
    rating = request.form.get("rating")
    comment = request.form.get("comment", "").strip()

    if len(comment) > 500:
        flash("Comment must be 500 characters or less.")
        return redirect("/home")

    if not isbn:
        flash("Missing book ISBN.")
        return redirect("/home")

    if not rating:
        flash("Please select a star rating before submitting.")
        return redirect("/home")

    try:
        rating = int(rating)
    except ValueError:
        flash("Invalid rating value.")
        return redirect("/home")

    if rating < 1 or rating > 5:
        flash("Rating must be between 1 and 5.")
        return redirect("/home")

    db.execute(text("""
        INSERT INTO ratings (userid, isbn, rating, comment)
        VALUES (:userid, :isbn, :rating, :comment)
        ON CONFLICT (userid, isbn)
        DO UPDATE SET
            rating = EXCLUDED.rating,
            comment = EXCLUDED.comment
    """), {
        "userid": userid,
        "isbn": isbn,
        "rating": rating,
        "comment": comment if comment else None
    })
    db.commit()

    other_ratings = db.execute(
        text("""
             SELECT a.username, r.rating, r.comment
             FROM ratings r
             JOIN accounts a ON r.userid = a.id
             WHERE r.isbn = :isbn
               AND r.userid != :userid
             ORDER BY r.rating DESC, a.username ASC
             """),
        {"isbn": isbn, "userid": userid}
    ).fetchall()

    book = db.execute(
        text("""
            SELECT isbn, title, author, year
            FROM books
            WHERE isbn = :isbn
        """),
        {"isbn": isbn}
    ).fetchone()

    if book is None:
        flash("Book not found.")
        return redirect("/home")

    google_data = get_google_books_data(book)

    google_rating = None
    google_description = None

    if google_data:
        google_rating = {
            "average_rating": google_data.get("averageRating"),
            "ratings_count": google_data.get("reviewCount")
        }
        google_description = google_data.get("description")

    gemini_summary = summarize_with_gemini_under_50_words(book.title, google_description)

    fallback_description = None
    if not gemini_summary and google_description:
        fallback_description = " ".join(google_description.split())[:220] + "..."

    return render_template(
        "viewbook.html",
        book=book,
        username=session.get("username"),
        user_rating=rating,
        user_comment=comment if comment else None,
        other_ratings=other_ratings,
        gemini_summary=gemini_summary,
        fallback_description=fallback_description,
        google_rating=google_rating
    )

@app.route("/api/<isbn>", methods=["GET"])
def book_api(isbn):
    # First requirement: ISBN must exist in YOUR database
    book = db.execute(
        text("""
            SELECT isbn, title, author, year
            FROM books
            WHERE isbn = :isbn
        """),
        {"isbn": isbn}
    ).fetchone()

    if book is None:
        abort(404)

    google_data = get_google_books_api_data(isbn)

    # Default values from your local DB where appropriate
    title = book.title if hasattr(book, "title") else book[1]
    author = book.author if hasattr(book, "author") else book[2]

    published_date = None
    isbn_10 = None
    isbn_13 = None
    review_count = None
    average_rating = None
    description = None
    summarized_description = None

    if google_data:
        title = google_data.get("title") or title
        author = google_data.get("author") or author
        published_date = google_data.get("publishedDate")
        isbn_10 = google_data.get("ISBN_10")
        isbn_13 = google_data.get("ISBN_13")
        review_count = google_data.get("reviewCount")
        average_rating = google_data.get("averageRating")
        description = google_data.get("description")

        if description:
            summarized_description = summarize_with_gemini_under_50_words(title, description)

    return jsonify({
        "title": title,
        "author": author,
        "publishedDate": published_date,
        "ISBN_10": isbn_10,
        "ISBN_13": isbn_13,
        "reviewCount": review_count,
        "averageRating": average_rating,
        "summarizedDescription": summarized_description
    })