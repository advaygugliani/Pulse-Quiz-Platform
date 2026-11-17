import csv
import time
import statistics
from flask import Flask, render_template, request

app = Flask(__name__)

TIME_LIMIT_MINUTES = 10
GRACE_SECONDS = 10

USERS_FILE = "users.csv"
QUESTIONS_FILE = "questions.csv"
ATTEMPTS_FILE = "attempts.csv"

USER_FIELDS = ["username", "password", "role"]
QUESTION_FIELDS = ["id", "text", "a", "b", "c", "d", "answer"]
ATTEMPT_FIELDS = ["username", "start_time", "score", "seconds", "status"]


def read_rows(filename):
    try:
        with open(filename, newline="") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def write_rows(filename, fields, rows):
    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def setup():
    users = read_rows(USERS_FILE)
    if len(users) == 0:
        users.append({"username": "admin", "password": "admin123", "role": "admin"})
        write_rows(USERS_FILE, USER_FIELDS, users)

    questions = read_rows(QUESTIONS_FILE)
    if len(questions) == 0:
        samples = [
            ["What is the capital of France?", "Berlin", "Paris", "Rome", "Madrid", "B"],
            ["What is 7 x 8?", "54", "56", "58", "64", "B"],
            ["Which planet is known as the Red Planet?", "Venus", "Jupiter", "Mars", "Saturn", "C"],
            ["How many days are there in a week?", "5", "6", "7", "8", "C"],
            ["Which gas do humans breathe in to live?", "Oxygen", "Helium", "Nitrogen", "Carbon dioxide", "A"],
        ]
        number = 1
        for s in samples:
            questions.append({
                "id": str(number),
                "text": s[0],
                "a": s[1],
                "b": s[2],
                "c": s[3],
                "d": s[4],
                "answer": s[5],
            })
            number = number + 1
        write_rows(QUESTIONS_FILE, QUESTION_FIELDS, questions)


def get_user(username):
    for u in read_rows(USERS_FILE):
        if u["username"] == username:
            return u
    return None


def get_deadline(attempt):
    return int(attempt["start_time"]) + TIME_LIMIT_MINUTES * 60


def time_is_over(attempt):
    return time.time() > get_deadline(attempt) + GRACE_SECONDS


def close_late_attempts():
    attempts = read_rows(ATTEMPTS_FILE)
    changed = False
    for a in attempts:
        if a["status"] == "started" and time_is_over(a):
            a["score"] = "0"
            a["seconds"] = str(TIME_LIMIT_MINUTES * 60)
            a["status"] = "done"
            changed = True
    if changed:
        write_rows(ATTEMPTS_FILE, ATTEMPT_FIELDS, attempts)
    return attempts


def find_attempt(attempts, username):
    for a in attempts:
        if a["username"] == username:
            return a
    return None


def login_page(message):
    return render_template("login.html", user=None, message=message)


def home_page(user):
    if user["role"] == "admin":
        return admin_page(user, "")
    attempts = close_late_attempts()
    attempt = find_attempt(attempts, user["username"])
    total = len(read_rows(QUESTIONS_FILE))
    return render_template("home.html", user=user, attempt=attempt, total=total, minutes=TIME_LIMIT_MINUTES)


def result_page(user):
    attempts = close_late_attempts()
    attempt = find_attempt(attempts, user["username"])
    if attempt is None or attempt["status"] != "done":
        return home_page(user)
    total = len(read_rows(QUESTIONS_FILE))
    return render_template("result.html", user=user, attempt=attempt, total=total)


def admin_page(user, message):
    attempts = close_late_attempts()
    scores = []
    for a in attempts:
        if a["status"] == "done":
            scores.append(int(a["score"]))
    stats = None
    if len(scores) > 0:
        stats = {
            "count": len(scores),
            "mean": round(statistics.mean(scores), 2),
            "median": statistics.median(scores),
            "highest": max(scores),
            "lowest": min(scores),
        }
    questions = read_rows(QUESTIONS_FILE)
    return render_template("admin.html", user=user, stats=stats, questions=questions, message=message)


def sort_key(attempt):
    return (-int(attempt["score"]), int(attempt["seconds"]))


@app.route("/")
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return login_page("")
    username = request.form["username"].strip()
    password = request.form["password"]
    user = get_user(username)
    if user is not None and user["password"] == password:
        return home_page(user)
    return login_page("Wrong username or password.")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", user=None, message="")
    username = request.form["username"].strip()
    password = request.form["password"]
    if not username.isalnum():
        return render_template("register.html", user=None, message="Username can only have letters and numbers.")
    if len(password) < 4 or "," in password:
        return render_template("register.html", user=None, message="Password must be 4 or more characters and have no commas.")
    users = read_rows(USERS_FILE)
    for u in users:
        if u["username"].lower() == username.lower():
            return render_template("register.html", user=None, message="That username is already taken.")
    users.append({"username": username, "password": password, "role": "student"})
    write_rows(USERS_FILE, USER_FIELDS, users)
    return login_page("Account created. Please login.")


@app.route("/home/<username>")
def home(username):
    user = get_user(username)
    if user is None:
        return login_page("Please login first.")
    return home_page(user)


@app.route("/start/<username>", methods=["POST"])
def start(username):
    user = get_user(username)
    if user is None or user["role"] != "student":
        return login_page("Please login first.")
    attempts = close_late_attempts()
    if find_attempt(attempts, username) is None and len(read_rows(QUESTIONS_FILE)) > 0:
        attempts.append({
            "username": username,
            "start_time": str(int(time.time())),
            "score": "0",
            "seconds": "0",
            "status": "started",
        })
        write_rows(ATTEMPTS_FILE, ATTEMPT_FIELDS, attempts)
    return exam(username)


@app.route("/exam/<username>")
def exam(username):
    user = get_user(username)
    if user is None or user["role"] != "student":
        return login_page("Please login first.")
    attempts = close_late_attempts()
    attempt = find_attempt(attempts, username)
    if attempt is None or attempt["status"] != "started":
        return home_page(user)
    questions = read_rows(QUESTIONS_FILE)
    deadline = time.strftime("%H:%M:%S", time.localtime(get_deadline(attempt)))
    return render_template("exam.html", user=user, questions=questions, deadline=deadline)


@app.route("/submit/<username>", methods=["POST"])
def submit(username):
    user = get_user(username)
    if user is None or user["role"] != "student":
        return login_page("Please login first.")
    attempts = close_late_attempts()
    attempt = find_attempt(attempts, username)
    if attempt is None:
        return home_page(user)
    if attempt["status"] != "started":
        return result_page(user)
    questions = read_rows(QUESTIONS_FILE)
    score = 0
    for q in questions:
        chosen = request.form.get("q" + q["id"])
        if chosen == q["answer"]:
            score = score + 1
    seconds = int(time.time()) - int(attempt["start_time"])
    attempt["score"] = str(score)
    attempt["seconds"] = str(seconds)
    attempt["status"] = "done"
    write_rows(ATTEMPTS_FILE, ATTEMPT_FIELDS, attempts)
    return result_page(user)


@app.route("/result/<username>")
def result(username):
    user = get_user(username)
    if user is None or user["role"] != "student":
        return login_page("Please login first.")
    return result_page(user)


@app.route("/leaderboard/<username>")
def leaderboard(username):
    user = get_user(username)
    if user is None:
        return login_page("Please login first.")
    attempts = close_late_attempts()
    done = []
    for a in attempts:
        if a["status"] == "done":
            done.append(a)
    done.sort(key=sort_key)
    return render_template("leaderboard.html", user=user, rows=done)


@app.route("/admin/<username>")
def admin(username):
    user = get_user(username)
    if user is None or user["role"] != "admin":
        return login_page("Admins only.")
    return admin_page(user, "")


@app.route("/add/<username>", methods=["POST"])
def add(username):
    user = get_user(username)
    if user is None or user["role"] != "admin":
        return login_page("Admins only.")
    text = request.form["text"].strip()
    a = request.form["a"].strip()
    b = request.form["b"].strip()
    c = request.form["c"].strip()
    d = request.form["d"].strip()
    answer = request.form["answer"]
    if text == "" or a == "" or b == "" or c == "" or d == "":
        return admin_page(user, "Please fill in every box.")
    questions = read_rows(QUESTIONS_FILE)
    biggest = 0
    for q in questions:
        if int(q["id"]) > biggest:
            biggest = int(q["id"])
    questions.append({
        "id": str(biggest + 1),
        "text": text,
        "a": a,
        "b": b,
        "c": c,
        "d": d,
        "answer": answer,
    })
    write_rows(QUESTIONS_FILE, QUESTION_FIELDS, questions)
    return admin_page(user, "Question added.")


@app.route("/delete/<username>/<question_id>", methods=["POST"])
def delete(username, question_id):
    user = get_user(username)
    if user is None or user["role"] != "admin":
        return login_page("Admins only.")
    questions = read_rows(QUESTIONS_FILE)
    kept = []
    for q in questions:
        if q["id"] != question_id:
            kept.append(q)
    write_rows(QUESTIONS_FILE, QUESTION_FIELDS, kept)
    return admin_page(user, "Question deleted.")


if __name__ == "__main__":
    setup()
    app.run(debug=True)
