
from flask import Flask, request, render_template, redirect, url_for, session, flash
import json, os, random, uuid, datetime


app = Flask(__name__)
app.secret_key = os.environ.get("QUIZ_SECRET_KEY", "dev-secret")
JSON_PATH = "questions.json"

# -------------------------------
# Load & Save Questions
# -------------------------------

def _make_question(
    definition, term,
    attempts=0, correct_count=0, wrong_count=0,
    last_seen=None, topic="", level="", tags=None, notes="", id_=None
):
    return {
        "id": id_ or str(uuid.uuid4()),
        "definition": definition or "",
        "term": term or "",
        "attempts": attempts or 0,
        "correct_count": correct_count or 0,
        "wrong_count": wrong_count or 0,
        "last_seen": last_seen,  # ISO string or None
        "topic": topic or "",
        "level": level or "",
        "tags": tags or [],
        "notes": notes or ""
    }

def load_questions(json_path=JSON_PATH):
    """
    Load questions; migrate legacy list-format rows to dicts.
    Legacy row structure in your current app: [definition, term, attempts].  [1](https://gdsto365-my.sharepoint.com/personal/c_hopkinson_put_gdst_net/Documents/Microsoft%20Copilot%20Chat%20Files/main_cs.py)
    """
    if not os.path.exists(json_path):
        print("questions.json NOT FOUND")
        return []

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = []
    for item in data:
        if isinstance(item, list):
            # Legacy: [definition, term, attempts]
            definition = item[0] if len(item) > 0 else ""
            term = item[1] if len(item) > 1 else ""
            attempts = item[2] if len(item) > 2 else 0
            questions.append(_make_question(definition, term, attempts=attempts))
        elif isinstance(item, dict):
            # Ensure required keys; fill defaults
            q = _make_question(
                definition=item.get("definition", ""),
                term=item.get("term", ""),
                attempts=item.get("attempts", 0),
                correct_count=item.get("correct_count", 0),
                wrong_count=item.get("wrong_count", 0),
                last_seen=item.get("last_seen"),
                topic=item.get("topic", ""),
                level=item.get("level", ""),
                tags=item.get("tags", []),
                notes=item.get("notes", ""),
                id_=item.get("id")
            )
            questions.append(q)
        else:
            # Skip unknown rows
            continue

    return questions

def save_questions(questions, json_path=JSON_PATH):
    """Always write the new dict-based schema to disk."""
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, indent=4, ensure_ascii=False)


def get_stats():
    total_answered = 0
    total_unanswered = 0
    total_correct = 0
    for q in questions:
        if q[2] > 0:
            total_answered += 1
        else:
            total_unanswered += 1
        total_correct += q[2]
    return [total_answered, total_unanswered, total_correct]

# -------------------------------
# Load Computer Science Questions
# -------------------------------

questions = load_questions()
current_question_index = 0

# ---------------------------
# Small utilities
# ---------------------------
def index_clamp(i, n):
    return max(0, min(i, n - 1))

def find_index_by_id(qid):
    for i, q in enumerate(questions):
        if q["id"] == qid:
            return i
    return None

def move_index(delta):
    global current_question_index
    n = len(questions)
    if n == 0:
        current_question_index = 0
        return 0
    current_question_index = (current_question_index + delta) % n
    return current_question_index


# -------------------------------
# ROUTES - URL endpoints.
# -------------------------------

@app.route("/stats")
def stats():
    s = get_stats()
    return  f"""
            <b>Total questions answered correctly:</b> {s[0]}<br>
            <b>Total questions not yet answered:</b> {s[1]}<br>
            <b>Total correct answers:</b> {s[2]}
            """

@app.route("/shuffle")
def shuffle_questions():
    """Shuffle the question order and reset the index."""
    global questions, current_question_index
    random.shuffle(questions)
    current_question_index = 0
    return redirect(url_for("quiz"))
# ---------------------------
# Admin: Add/Edit/Delete/Browse
# ---------------------------
@app.route("/question_admin", methods=["GET", "POST"])
def question_admin():
    """
    GET:
      - show current question (by ?index= or session)
      - allow prev/next browsing
    POST:
      - action = add | save | delete | prev | next | new
    """
    global questions

    # Determine which question we’re looking at
    # Priority: explicit ?index -> session -> 0
    if "admin_index" not in session:
        session["admin_index"] = 0

    if request.method == "GET":
        idx_param = request.args.get("index", None, type=int)
        if idx_param is not None and 0 <= idx_param < len(questions):
            session["admin_index"] = idx_param

    # Process form actions
    if request.method == "POST":
        action = request.form.get("action", "")
        qid = request.form.get("id", "")

        if action in ("prev", "next"):
            delta = -1 if action == "prev" else 1
            session["admin_index"] = (session["admin_index"] + delta) % max(1, len(questions))

        elif action == "new":
            # Just blank the form in the UI; handled by template logic
            pass

        elif action in ("add", "save"):
            # Gather fields from form
            form_q = {
                "id_": qid or str(uuid.uuid4()),
                "definition": request.form.get("definition", "").strip(),
                "term": request.form.get("term", "").strip(),
                "attempts": int(request.form.get("attempts", 0) or 0),
                "correct_count": int(request.form.get("correct_count", 0) or 0),
                "wrong_count": int(request.form.get("wrong_count", 0) or 0),
                "last_seen": request.form.get("last_seen") or None,
                "topic": request.form.get("topic", "").strip(),
                "level": request.form.get("level", "").strip(),
                "tags": [t.strip() for t in request.form.get("tags", "").split(",") if t.strip()],
                "notes": request.form.get("notes", "").strip()
            }

            # Normalise
            form_q = _make_question(**form_q)

            # Add vs Save
            if action == "add" or find_index_by_id(form_q["id"]) is None:
                questions.append(form_q)
                session["admin_index"] = len(questions) - 1
                flash("Question added.")
            else:
                i = find_index_by_id(form_q["id"])
                questions[i] = form_q
                session["admin_index"] = i
                flash("Question saved.")

            save_questions(questions)

        elif action == "delete":
            if qid:
                i = find_index_by_id(qid)
                if i is not None:
                    del questions[i]
                    # Move admin index safely
                    session["admin_index"] = index_clamp(i, max(1, len(questions)))
                    flash("Question deleted.")
                    save_questions(questions)

    # Prepare data for template
    n = len(questions)
    i = index_clamp(session.get("admin_index", 0), n) if n > 0 else 0
    current_q = questions[i] if n > 0 else _make_question("", "")
    return render_template(
        "question_admin.html",
        q=current_q, count=n, index=i
    )

# ---------------------------
# Existing routes (minimal tweaks)
# ---------------------------

@app.route("/")
def home():
    return "## Hello, Computer Science students! Click <a href='/quiz'>here</a> for the quiz."

@app.route("/quiz")
def quiz():
    global current_question_index, questions
    answer = request.args.get("answer")
    mc_mode = request.args.get("mc", "0") == "1"
    feedback = ""

    if not questions:
        return render_template("quiz.html",
                               response="No questions found.",
                               ans="", mc_mode=False, mc_options=[])

    # If user just answered the previous question
    if answer is not None and len(answer) > 0:
        given = answer.strip().lower()
        correct = questions[current_question_index]["term"].lower()
        # attempts = any answer attempt
        questions[current_question_index]["attempts"] += 1

        # record right/wrong and last_seen
        now = datetime.datetime.utcnow().isoformat()
        questions[current_question_index]["last_seen"] = now

        if given == correct:
            feedback = "<h1>Correct!</h1><br>"
            questions[current_question_index]["correct_count"] += 1
            save_questions(questions)
            # Move to a random question (keep your behaviour)
            current_question_index = random.randint(0, len(questions) - 1)
            mc_mode = False
        else:
            feedback = "<h1>Not quite!</h1><br>"
            questions[current_question_index]["wrong_count"] += 1
            save_questions(questions)
            mc_mode = True

    # Build MC options if needed
    mc_options = []
    if mc_mode:
        correct_term = questions[current_question_index]["term"]
        all_terms = [q["term"] for q in questions if q["term"] != correct_term]
        wrongs = random.sample(all_terms, min(3, len(all_terms))) if all_terms else []
        mc_options = [correct_term] + wrongs
        random.shuffle(mc_options)

    definition = questions[current_question_index]["definition"]
    attempts = questions[current_question_index]["attempts"]
    response_html = (
        feedback
        + f"<b>{definition}</b><br>"
        + f"<i>Answered {attempts} times.</i>"
    )

    return render_template(
        "quiz.html",
        response=response_html,
        ans=questions[current_question_index]["term"],
        mc_mode=mc_mode,
        mc_options=mc_options
    )


if __name__ == "__main__":
    app.run(debug=True)
