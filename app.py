# =============================================================================
# QuizMaster Pro — app.py
# UPGRADED: PostgreSQL + Ban/Unban + Admin Chat Control + Backend hardening
# =============================================================================

from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, flash)
from werkzeug.security import generate_password_hash, check_password_hash

# ── CHANGED: removed sqlite3, added psycopg2 ─────────────────────────────────
import psycopg2
import psycopg2.extras          # gives us RealDictCursor (dict-style rows)

import os, csv, io, json, random, re
from functools import wraps

# =============================================================================
# APP CONFIG
# =============================================================================
app = Flask(__name__)
app.secret_key = os.environ.get(
    'SECRET_KEY',
    'QM_pr0_s3cr3t_K3y_Ayush2024_!@#$_do_not_share'
)

# =============================================================================
# ── CHANGED: PostgreSQL DATABASE URL ─────────────────────────────────────────
# =============================================================================
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres.aqtygpfqdlxwrgzthlpv:JQVs03Xa2gxSBv9M@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres'
)
# Render sometimes gives "postgres://" — normalise to "postgresql://"
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# =============================================================================
# ── NEW: Reusable DB helpers ──────────────────────────────────────────────────
# =============================================================================

def get_db():
    """
    Open a new PostgreSQL connection.
    Uses RealDictCursor so every row is a dict (same usage as sqlite3.Row).
    Always call conn.close() when done, or use in a try/finally block.
    """
    conn = psycopg2.connect(DATABASE_URL, sslmode='require',
                            cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def query_db(query, params=(), fetchone=False, fetchall=False,
             commit=False, conn=None):
    """
    ── NEW helper ──
    Runs a query and optionally fetches results or commits.
    Accepts an existing connection (conn=) so callers can batch ops.
    If no conn is passed, opens+closes one automatically.

    Usage examples
    --------------
    # Single row
    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), fetchone=True)

    # Multiple rows
    rows = query_db("SELECT * FROM questions", fetchall=True)

    # Write (INSERT / UPDATE / DELETE)
    query_db("INSERT INTO ...", (...,), commit=True)

    # Re-use a connection (batch writes)
    conn = get_db()
    query_db("INSERT ...", (...,), commit=False, conn=conn)
    query_db("INSERT ...", (...,), commit=True,  conn=conn)
    conn.close()
    """
    _own_conn = conn is None
    if _own_conn:
        conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        result = None
        if fetchone:
            result = cur.fetchone()
        elif fetchall:
            result = cur.fetchall()
        if commit:
            conn.commit()
        return result
    except Exception as e:
        if commit:
            conn.rollback()
        raise e
    finally:
        if _own_conn:
            conn.close()


# =============================================================================
# ── CHANGED: init_db — SQLite → PostgreSQL syntax ────────────────────────────
#   • INTEGER PRIMARY KEY AUTOINCREMENT  →  SERIAL PRIMARY KEY
#   • executescript()                    →  individual execute() calls
#   • Added is_banned column to users
#   • Added id column to chat_messages for admin delete
# =============================================================================

def init_db():
    conn = get_db()
    try:
        cur = conn.cursor()

        # ── users table ───────────────────────────────────────────────────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id         SERIAL PRIMARY KEY,
                name       TEXT    NOT NULL,
                email      TEXT    UNIQUE NOT NULL,
                password   TEXT    NOT NULL,
                is_admin   INTEGER DEFAULT 0,
                is_banned  BOOLEAN DEFAULT FALSE,   -- NEW: ban system
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')

        # ── questions table ───────────────────────────────────────────────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS questions (
                id             SERIAL PRIMARY KEY,
                class_name     TEXT NOT NULL,
                subject        TEXT NOT NULL,
                chapter        TEXT NOT NULL,
                question       TEXT NOT NULL,
                option_a       TEXT NOT NULL,
                option_b       TEXT NOT NULL,
                option_c       TEXT NOT NULL,
                option_d       TEXT NOT NULL,
                correct_option TEXT NOT NULL,
                explanation    TEXT,
                created_at     TIMESTAMPTZ DEFAULT NOW()
            )
        ''')

        # ── results table ─────────────────────────────────────────────────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS results (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id),
                class_name TEXT NOT NULL,
                subject    TEXT NOT NULL,
                chapter    TEXT NOT NULL,
                score      INTEGER NOT NULL,
                total      INTEGER NOT NULL,
                time_taken INTEGER,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')

        # ── chat_messages table ───────────────────────────────────────────────
        # NEW: id kept so admin can DELETE individual messages
        cur.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                user_name  TEXT    NOT NULL,
                message    TEXT    NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')

        # ── comments table ────────────────────────────────────────────────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                user_name  TEXT    NOT NULL,
                class_name TEXT    NOT NULL,
                subject    TEXT    NOT NULL,
                chapter    TEXT    NOT NULL,
                comment    TEXT    NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')

        # ── notifications table  (NEW — added for notification system) ─────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id          SERIAL PRIMARY KEY,
                title       TEXT    NOT NULL,
                message     TEXT    NOT NULL,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        ''')
        # User-notification pivot: tracks per-user read state
        cur.execute('''
            CREATE TABLE IF NOT EXISTS notification_reads (
                id              SERIAL PRIMARY KEY,
                notification_id INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
                user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                is_read         BOOLEAN DEFAULT FALSE,
                read_at         TIMESTAMPTZ,
                UNIQUE (notification_id, user_id)
            )
        ''')

        # ── mocktest_results table  (NEW — Mocktest system) ─────────────────────
        cur.execute('''
            CREATE TABLE IF NOT EXISTS mocktest_results (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                score      INTEGER NOT NULL,
                total      INTEGER NOT NULL,
                accuracy   NUMERIC(5,2) NOT NULL,
                time_taken INTEGER DEFAULT 0,
                answers    JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')

        # ── ADD is_banned column if upgrading an existing DB ──────────────────
        # Safe to run on a DB that already has the other columns
        cur.execute('''
            ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE
        ''')

        # ── Seed / sync admin account ─────────────────────────────────────────
        ADMIN_EMAIL = 'admin@quizapp.com'
        ADMIN_PASS  = '1111@@@@aaaa####'
        cur.execute("SELECT id FROM users WHERE email=%s", (ADMIN_EMAIL,))
        existing = cur.fetchone()
        if not existing:
            cur.execute(
                "INSERT INTO users (name,email,password,is_admin) VALUES (%s,%s,%s,1)",
                ('Admin', ADMIN_EMAIL, generate_password_hash(ADMIN_PASS))
            )
        else:
            cur.execute(
                "UPDATE users SET password=%s WHERE email=%s",
                (generate_password_hash(ADMIN_PASS), ADMIN_EMAIL)
            )

        # ── Seed sample questions (only if table is empty) ────────────────────
        cur.execute("SELECT COUNT(*) AS cnt FROM questions")
        if cur.fetchone()['cnt'] == 0:
            seed_questions(cur)

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[init_db] ERROR: {e}")
        raise
    finally:
        conn.close()


def seed_questions(cur):
    """Insert starter questions using %s placeholders (PostgreSQL)."""
    samples = [
        ('10th','Physics','Motion','What is the SI unit of velocity?','m/s','km/h','cm/s','ft/s','A','Metre per second is SI unit'),
        ('10th','Physics','Motion','Which of the following is a vector quantity?','Speed','Distance','Velocity','Time','C','Velocity has both magnitude and direction'),
        ('10th','Physics','Motion','A car travels 60 km in 2 hours. What is its average speed?','20 km/h','30 km/h','60 km/h','120 km/h','B','Speed = Distance/Time = 60/2 = 30 km/h'),
        ('10th','Physics','Motion','What is inertia?','A type of force','Resistance to change in motion','Acceleration due to gravity','None of these','B','Inertia is resistance to change in state of motion'),
        ('10th','Physics','Motion',"Newton's first law is also called:",'Law of acceleration','Law of inertia','Law of action reaction','Law of gravitation','B','First law is the law of inertia'),
        ('10th','Physics','Motion','Distance is a __ quantity','Vector','Scalar','Both','Neither','B','Distance is a scalar - only magnitude'),
        ('10th','Physics','Motion','If velocity is constant, acceleration is:','Positive','Negative','Zero','Infinite','C','No change in velocity means zero acceleration'),
        ('10th','Physics','Motion','Unit of acceleration is:','m/s','m/s2','km/h','None','B','Acceleration = m/s2'),
        ('10th','Physics','Motion','Speed = Distance / ___','Velocity','Acceleration','Time','Force','C','Speed = Distance / Time'),
        ('10th','Physics','Motion','Uniform motion means:','Changing speed','Constant speed','Increasing speed','Decreasing speed','B','Uniform = constant speed'),
        ('10th','Chemistry','Acids Bases','pH of pure water is:','7','0','14','1','A','Pure water is neutral with pH 7'),
        ('10th','Chemistry','Acids Bases','Which is a strong acid?','Acetic acid','Hydrochloric acid','Citric acid','Carbonic acid','B','HCl is a strong acid'),
        ('10th','Chemistry','Acids Bases','Litmus paper turns red in:','Base','Acid','Neutral','Salt','B','Acid turns blue litmus red'),
        ('10th','Chemistry','Acids Bases','NaOH is a:','Acid','Salt','Base','None','C','NaOH is sodium hydroxide - a base'),
        ('10th','Chemistry','Acids Bases','Neutralization produces:','Acid + Water','Salt + Water','Base + Water','None','B','Acid + Base = Salt + Water'),
        ('10th','Chemistry','Acids Bases','pH below 7 indicates:','Acidic','Basic','Neutral','None','A','pH < 7 is acidic'),
        ('10th','Chemistry','Acids Bases','Which gas is produced when acid reacts with metal?','O2','CO2','H2','N2','C','Acid + Metal = Salt + Hydrogen gas'),
        ('10th','Chemistry','Acids Bases','Baking soda is:','Acidic','Basic','Neutral','Salt','B','Baking soda (NaHCO3) is basic'),
        ('10th','Chemistry','Acids Bases','Vinegar contains:','HCl','H2SO4','CH3COOH','HNO3','C','Vinegar contains acetic acid'),
        ('10th','Chemistry','Acids Bases','Bases have pH:','Less than 7','Equal to 7','Greater than 7','Equal to 0','C','Bases have pH > 7'),
        ('11th','Physics','Laws of Motion','Newton second law: F = ?','ma','mv','m/a','a/m','A','Force = mass x acceleration'),
        ('11th','Physics','Laws of Motion','Action and reaction forces act on:','Same body','Different bodies','Same direction','None','B','Action-reaction act on different bodies'),
        ('11th','Physics','Laws of Motion','Unit of force is:','Joule','Newton','Pascal','Watt','B','SI unit of force is Newton'),
        ('11th','Physics','Laws of Motion','Momentum = ?','mv','ma','Fv','Fa','A','Momentum = mass x velocity'),
        ('11th','Physics','Laws of Motion','Impulse = ?','Fxt','Fxa','mxa','mxv','A','Impulse = Force x time'),
        ('11th','Math','Trigonometry','sin2 + cos2 = ?','0','1','2','-1','B','Pythagorean identity'),
        ('11th','Math','Trigonometry','Value of sin 30 is:','1/2','sqrt(3)/2','1','0','A','sin 30 = 0.5'),
        ('11th','Math','Trigonometry','tan = ?','sin/cos','cos/sin','1/sin','1/cos','A','tan = sin/cos'),
        ('11th','Math','Trigonometry','cos 0 = ?','0','1','-1','1/2','B','cos 0 = 1'),
        ('11th','Math','Trigonometry','sin 90 = ?','0','1/2','sqrt(3)/2','1','D','sin 90 = 1'),
        ('12th','Math','Integration','integral x dx = ?','x','x^2/2','x^2','2x','B','integral x dx = x^2/2 + C'),
        ('12th','Math','Integration','integral 1 dx = ?','0','1','x','1/x','C','integral 1 dx = x + C'),
        ('12th','Math','Integration','integral e^x dx = ?','e^x','xe^x','e^x/x','e','A','integral e^x dx = e^x + C'),
        ('12th','Chemistry','Electrochemistry','Electrolysis is used to:','Extract metals','Create alloys','Both A and B','None','C','Both extraction and plating'),
        ('12th','Chemistry','Electrochemistry','Cathode is:','Positive electrode','Negative electrode','Neutral','None','B','Cathode = negative electrode'),
    ]
    # ── CHANGED: ? → %s ──────────────────────────────────────────────────────
    for s in samples:
        cur.execute('''
            INSERT INTO questions
                (class_name,subject,chapter,question,
                 option_a,option_b,option_c,option_d,
                 correct_option,explanation)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ''', s)


# =============================================================================
# DECORATORS
# =============================================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


# =============================================================================
# INPUT VALIDATION HELPERS  ── NEW ────────────────────────────────────────────
# =============================================================================

def is_valid_email(email):
    return re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email) is not None


def sanitise_str(s, max_len=500):
    return str(s).strip()[:max_len]


# =============================================================================
# AUTH ROUTES
# =============================================================================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name     = sanitise_str(request.form.get('name', ''), 100)
        email    = sanitise_str(request.form.get('email', ''), 200).lower()
        password = request.form.get('password', '')

        # ── NEW: input validation ─────────────────────────────────────────────
        if not name:
            flash('Name is required.', 'error')
            return render_template('register.html')
        if not is_valid_email(email):
            flash('Please enter a valid email address.', 'error')
            return render_template('register.html')
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('register.html')

        try:
            conn = get_db()
            try:
                cur = conn.cursor()
                # ── CHANGED: ? → %s ──────────────────────────────────────────
                cur.execute("SELECT id FROM users WHERE email=%s", (email,))
                if cur.fetchone():
                    flash('Email already registered.', 'error')
                    return render_template('register.html')

                cur.execute(
                    "INSERT INTO users (name,email,password) VALUES (%s,%s,%s)",
                    (name, email, generate_password_hash(password))
                )
                conn.commit()

                cur.execute("SELECT * FROM users WHERE email=%s", (email,))
                user = cur.fetchone()
                session['user_id']   = user['id']
                session['user_name'] = user['name']
                session['is_admin']  = False
                flash(f'Welcome, {name}! Account created successfully.', 'success')
                return redirect(url_for('dashboard'))
            finally:
                conn.close()
        except Exception as e:
            flash('Registration failed. Please try again.', 'error')
            app.logger.error(f'[register] {e}')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = sanitise_str(request.form.get('email', ''), 200).lower()
        password = request.form.get('password', '')

        try:
            conn = get_db()
            try:
                cur = conn.cursor()
                # ── CHANGED: ? → %s ──────────────────────────────────────────
                cur.execute("SELECT * FROM users WHERE email=%s", (email,))
                user = cur.fetchone()
            finally:
                conn.close()

            if user and check_password_hash(user['password'], password):
                # ── NEW: ban check ────────────────────────────────────────────
                if user.get('is_banned'):
                    flash('Your account has been banned by admin.', 'error')
                    return render_template('login.html')

                session['user_id']   = user['id']
                session['user_name'] = user['name']
                session['is_admin']  = bool(user['is_admin'])

                if user['is_admin']:
                    return redirect(url_for('admin_dashboard'))

                flash(f'Welcome back, {user["name"]}!', 'success')
                return redirect(url_for('dashboard'))

            flash('Invalid email or password.', 'error')
        except Exception as e:
            flash('Login failed. Please try again.', 'error')
            app.logger.error(f'[login] {e}')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# =============================================================================
# USER ROUTES
# =============================================================================

@app.route('/dashboard')
@login_required
def dashboard():
    uid = session['user_id']
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM results WHERE user_id=%s ORDER BY created_at DESC LIMIT 5",
                (uid,)
            )
            results = cur.fetchall()

            cur.execute("SELECT COUNT(*) AS cnt FROM results WHERE user_id=%s", (uid,))
            total_attempts = cur.fetchone()['cnt']

            cur.execute(
                "SELECT MAX(CAST(score AS FLOAT)/total*100) AS best FROM results WHERE user_id=%s",
                (uid,)
            )
            row = cur.fetchone()
            best_score = round(row['best']) if row and row['best'] else 0

            # Mocktest stats
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM mocktest_results WHERE user_id=%s", (uid,)
            )
            mock_attempts = cur.fetchone()['cnt']

            cur.execute(
                "SELECT MAX(accuracy) AS best FROM mocktest_results WHERE user_id=%s", (uid,)
            )
            mock_row  = cur.fetchone()
            mock_best = round(float(mock_row['best'])) if mock_row and mock_row['best'] else 0
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[dashboard] {e}')
        results, total_attempts, best_score = [], 0, 0
        mock_attempts, mock_best = 0, 0

    return render_template('dashboard.html', results=results,
                           total_attempts=total_attempts, best_score=best_score,
                           mock_attempts=mock_attempts, mock_best=mock_best)


@app.route('/quiz')
@login_required
def quiz_home():
    classes  = ['10th', '11th', '12th']
    subjects = {c: ['Physics', 'Chemistry', 'Math'] for c in classes}
    chapters = {}
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT class_name, subject, chapter FROM questions")
            for row in cur.fetchall():
                key = f"{row['class_name']}_{row['subject']}"
                chapters.setdefault(key, [])
                if row['chapter'] not in chapters[key]:
                    chapters[key].append(row['chapter'])
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[quiz_home] {e}')

    return render_template('quiz_home.html', classes=classes,
                           subjects=subjects, chapters=chapters)


@app.route('/quiz/start')
@login_required
def quiz_start():
    cls  = sanitise_str(request.args.get('class_name', ''), 20)
    sub  = sanitise_str(request.args.get('subject', ''), 50)
    chap = sanitise_str(request.args.get('chapter', ''), 100)

    if not all([cls, sub, chap]):
        return redirect(url_for('quiz_home'))

    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            # ── CHANGED: ? → %s ──────────────────────────────────────────────
            cur.execute(
                "SELECT * FROM questions WHERE class_name=%s AND subject=%s AND chapter=%s",
                (cls, sub, chap)
            )
            questions = cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[quiz_start] {e}')
        flash('Could not load questions. Please try again.', 'error')
        return redirect(url_for('quiz_home'))

    if not questions:
        flash('No questions available for this selection.', 'error')
        return redirect(url_for('quiz_home'))

    selected = random.sample(list(questions), min(10, len(questions)))
    q_list = [{
        'id':          q['id'],
        'question':    q['question'],
        'options':     {'A': q['option_a'], 'B': q['option_b'],
                        'C': q['option_c'], 'D': q['option_d']},
        'correct':     q['correct_option'],
        'explanation': q['explanation'] or ''
    } for q in selected]

    session['quiz_data'] = {'questions': q_list, 'class': cls,
                            'subject': sub, 'chapter': chap}
    return render_template('quiz.html', cls=cls, subject=sub, chapter=chap,
                           questions=json.dumps(q_list), total=len(q_list))


@app.route('/quiz/submit', methods=['POST'])
@login_required
def quiz_submit():
    data      = request.get_json() or {}
    quiz_data = session.get('quiz_data')
    if not quiz_data:
        return jsonify({'error': 'No active quiz'}), 400

    answers   = data.get('answers', {})
    questions = quiz_data['questions']
    score     = sum(1 for q in questions
                    if answers.get(str(q['id'])) == q['correct'])

    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            # ── CHANGED: ? → %s ──────────────────────────────────────────────
            cur.execute(
                '''INSERT INTO results
                   (user_id, class_name, subject, chapter, score, total, time_taken)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                (session['user_id'], quiz_data['class'], quiz_data['subject'],
                 quiz_data['chapter'], score, len(questions),
                 data.get('time_taken', 0))
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[quiz_submit] {e}')
        return jsonify({'error': 'Could not save result'}), 500

    return jsonify({'score': score, 'total': len(questions)})


# =============================================================================
# CHAT ROUTES
# =============================================================================

@app.route('/chat')
@login_required
def chat():
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT 50"
            )
            messages = list(reversed(cur.fetchall()))
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[chat] {e}')
        messages = []
    return render_template('chat.html', messages=messages)


@app.route('/chat/send', methods=['POST'])
@login_required
def chat_send():
    msg = (request.get_json() or {}).get('message', '').strip()
    if not msg or len(msg) > 500:
        return jsonify({'error': 'Invalid message'}), 400

    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            # ── CHANGED: ? → %s ──────────────────────────────────────────────
            cur.execute(
                "INSERT INTO chat_messages (user_id, user_name, message) VALUES (%s,%s,%s)",
                (session['user_id'], session['user_name'], msg)
            )
            conn.commit()
            cur.execute(
                "SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT 50"
            )
            messages = list(reversed(cur.fetchall()))
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[chat_send] {e}')
        return jsonify({'error': 'Could not send message'}), 500

    msgs = [{'id': m['id'], 'user_name': m['user_name'],
             'message': m['message'],
             'created_at': str(m['created_at'])} for m in messages]
    return jsonify({'messages': msgs})


@app.route('/chat/messages')
@login_required
def chat_messages():
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT 50"
            )
            messages = list(reversed(cur.fetchall()))
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[chat_messages] {e}')
        messages = []

    msgs = [{'id': m['id'], 'user_name': m['user_name'],
             'message': m['message'],
             'created_at': str(m['created_at'])} for m in messages]
    return jsonify({'messages': msgs})


# ── NEW: Admin delete single chat message ─────────────────────────────────────
@app.route('/admin/chat/delete/<int:msg_id>', methods=['POST'])
@admin_required
def admin_chat_delete(msg_id):
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM chat_messages WHERE id=%s", (msg_id,))
            conn.commit()
        finally:
            conn.close()
        flash('Message deleted.', 'info')
    except Exception as e:
        app.logger.error(f'[admin_chat_delete] {e}')
        flash('Could not delete message.', 'error')
    return redirect(url_for('admin_chat'))


# ── NEW: Admin clear ALL chat messages ────────────────────────────────────────
@app.route('/admin/chat/clear', methods=['POST'])
@admin_required
def admin_chat_clear():
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM chat_messages")
            conn.commit()
        finally:
            conn.close()
        flash('All chat messages cleared.', 'success')
    except Exception as e:
        app.logger.error(f'[admin_chat_clear] {e}')
        flash('Could not clear chat.', 'error')
    return redirect(url_for('admin_chat'))


# ── NEW: Admin chat management page ──────────────────────────────────────────
@app.route('/admin/chat')
@admin_required
def admin_chat():
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT 200"
            )
            messages = cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[admin_chat] {e}')
        messages = []
    return render_template('admin_chat.html', messages=messages)


# =============================================================================
# COMMENTS
# =============================================================================

@app.route('/comments/get')
def comments_get():
    cls  = sanitise_str(request.args.get('class_name', ''), 20)
    sub  = sanitise_str(request.args.get('subject', ''), 50)
    chap = sanitise_str(request.args.get('chapter', ''), 100)
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            # ── CHANGED: ? → %s ──────────────────────────────────────────────
            cur.execute(
                '''SELECT * FROM comments
                   WHERE class_name=%s AND subject=%s AND chapter=%s
                   ORDER BY created_at DESC LIMIT 20''',
                (cls, sub, chap)
            )
            rows = cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[comments_get] {e}')
        rows = []
    return jsonify([{'user_name': r['user_name'], 'comment': r['comment'],
                     'created_at': str(r['created_at'])} for r in rows])


@app.route('/comments/add', methods=['POST'])
@login_required
def comments_add():
    data = request.get_json() or {}
    comment = sanitise_str(data.get('comment', ''), 1000)
    if not comment:
        return jsonify({'error': 'Empty comment'}), 400
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            # ── CHANGED: ? → %s ──────────────────────────────────────────────
            cur.execute(
                '''INSERT INTO comments
                   (user_id, user_name, class_name, subject, chapter, comment)
                   VALUES (%s,%s,%s,%s,%s,%s)''',
                (session['user_id'], session['user_name'],
                 data.get('class_name',''), data.get('subject',''),
                 data.get('chapter',''), comment)
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[comments_add] {e}')
        return jsonify({'error': 'Could not save comment'}), 500
    return jsonify({'status': 'ok'})


# =============================================================================
# ADMIN ROUTES
# =============================================================================

@app.route('/admin')
def admin_index():
    return redirect(url_for('admin_dashboard') if session.get('is_admin')
                    else url_for('admin_login'))


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        email    = sanitise_str(request.form.get('email', ''), 200).lower()
        password = request.form.get('password', '')
        try:
            conn = get_db()
            try:
                cur = conn.cursor()
                # ── CHANGED: ? → %s ──────────────────────────────────────────
                cur.execute(
                    "SELECT * FROM users WHERE email=%s AND is_admin=1",
                    (email,)
                )
                user = cur.fetchone()
            finally:
                conn.close()

            if user and check_password_hash(user['password'], password):
                session['user_id']   = user['id']
                session['user_name'] = user['name']
                session['is_admin']  = True
                return redirect(url_for('admin_dashboard'))
            flash('Invalid admin credentials.', 'error')
        except Exception as e:
            app.logger.error(f'[admin_login] {e}')
            flash('Login error. Please try again.', 'error')
    return render_template('admin_login.html')


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS cnt FROM users WHERE is_admin=0")
            total_users = cur.fetchone()['cnt']
            cur.execute("SELECT COUNT(*) AS cnt FROM results")
            total_attempts = cur.fetchone()['cnt']
            cur.execute("SELECT COUNT(*) AS cnt FROM questions")
            total_questions = cur.fetchone()['cnt']
            cur.execute(
                "SELECT * FROM users WHERE is_admin=0 ORDER BY created_at DESC LIMIT 5"
            )
            recent_users = cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[admin_dashboard] {e}')
        total_users = total_attempts = total_questions = 0
        recent_users = []

    return render_template('admin_dashboard.html',
                           total_users=total_users,
                           total_attempts=total_attempts,
                           total_questions=total_questions,
                           recent_users=recent_users)


@app.route('/admin/questions')
@admin_required
def admin_questions():
    cls_filter = sanitise_str(request.args.get('class_name', ''), 20)
    sub_filter = sanitise_str(request.args.get('subject', ''), 50)
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            # ── CHANGED: ? → %s, build dynamic WHERE ─────────────────────────
            query      = "SELECT * FROM questions"
            params     = []
            conditions = []
            if cls_filter:
                conditions.append("class_name=%s")
                params.append(cls_filter)
            if sub_filter:
                conditions.append("subject=%s")
                params.append(sub_filter)
            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)
            query += ' ORDER BY id DESC'
            cur.execute(query, params)
            questions = cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[admin_questions] {e}')
        questions = []
    return render_template('admin_questions.html', questions=questions,
                           cls_filter=cls_filter, sub_filter=sub_filter)


@app.route('/admin/questions/add', methods=['GET', 'POST'])
@admin_required
def admin_add_question():
    if request.method == 'POST':
        f = request.form
        try:
            conn = get_db()
            try:
                cur = conn.cursor()
                # ── CHANGED: ? → %s ──────────────────────────────────────────
                cur.execute(
                    '''INSERT INTO questions
                       (class_name,subject,chapter,question,
                        option_a,option_b,option_c,option_d,
                        correct_option,explanation)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (f['class_name'], f['subject'], f['chapter'], f['question'],
                     f['option_a'], f['option_b'], f['option_c'], f['option_d'],
                     f['correct_option'], f.get('explanation', ''))
                )
                conn.commit()
            finally:
                conn.close()
            flash('Question added successfully!', 'success')
        except Exception as e:
            app.logger.error(f'[admin_add_question] {e}')
            flash('Could not add question.', 'error')
        return redirect(url_for('admin_questions'))
    return render_template('admin_question_form.html', q=None, action='Add')


@app.route('/admin/questions/edit/<int:qid>', methods=['GET', 'POST'])
@admin_required
def admin_edit_question(qid):
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            if request.method == 'POST':
                f = request.form
                # ── CHANGED: ? → %s ──────────────────────────────────────────
                cur.execute(
                    '''UPDATE questions
                       SET class_name=%s, subject=%s, chapter=%s, question=%s,
                           option_a=%s, option_b=%s, option_c=%s, option_d=%s,
                           correct_option=%s, explanation=%s
                       WHERE id=%s''',
                    (f['class_name'], f['subject'], f['chapter'], f['question'],
                     f['option_a'], f['option_b'], f['option_c'], f['option_d'],
                     f['correct_option'], f.get('explanation', ''), qid)
                )
                conn.commit()
                flash('Question updated!', 'success')
                return redirect(url_for('admin_questions'))
            cur.execute("SELECT * FROM questions WHERE id=%s", (qid,))
            q = cur.fetchone()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[admin_edit_question] {e}')
        flash('Could not load question.', 'error')
        return redirect(url_for('admin_questions'))
    return render_template('admin_question_form.html', q=q, action='Edit')


@app.route('/admin/questions/delete/<int:qid>', methods=['POST'])
@admin_required
def admin_delete_question(qid):
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM questions WHERE id=%s", (qid,))
            conn.commit()
        finally:
            conn.close()
        flash('Question deleted.', 'info')
    except Exception as e:
        app.logger.error(f'[admin_delete_question] {e}')
        flash('Could not delete question.', 'error')
    return redirect(url_for('admin_questions'))


@app.route('/admin/upload_csv', methods=['GET', 'POST'])
@admin_required
def admin_upload_csv():
    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file:
            flash('No file selected.', 'error')
            return redirect(request.url)
        stream = io.StringIO(file.stream.read().decode('UTF-8'), newline=None)
        reader = csv.DictReader(stream)
        count  = 0
        errors = 0
        try:
            conn = get_db()
            try:
                cur = conn.cursor()
                for row in reader:
                    try:
                        # ── CHANGED: ? → %s ──────────────────────────────────
                        cur.execute(
                            '''INSERT INTO questions
                               (class_name,subject,chapter,question,
                                option_a,option_b,option_c,option_d,
                                correct_option,explanation)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                            (row['class_name'], row['subject'], row['chapter'],
                             row['question'], row['option_a'], row['option_b'],
                             row['option_c'], row['option_d'],
                             row['correct_option'], row.get('explanation', ''))
                        )
                        count += 1
                    except Exception:
                        errors += 1
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            app.logger.error(f'[admin_upload_csv] {e}')
            flash('CSV upload failed.', 'error')
            return redirect(request.url)

        msg = f'{count} question(s) uploaded successfully!'
        if errors:
            msg += f' ({errors} row(s) skipped due to errors)'
        flash(msg, 'success')
        return redirect(url_for('admin_questions'))
    return render_template('admin_upload_csv.html')


@app.route('/admin/users')
@admin_required
def admin_users():
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            # ── CHANGED: ? → %s, ROUND syntax for PostgreSQL ─────────────────
            # ── CHANGED: GROUP BY must include all non-aggregate columns ──────
            cur.execute('''
                SELECT u.id, u.name, u.email, u.is_banned, u.created_at,
                       COUNT(r.id)                                               AS attempts,
                       COALESCE(
                           MAX(ROUND((CAST(r.score AS FLOAT)/r.total*100)::numeric, 1)),
                           0
                       )                                                         AS best_pct
                FROM users u
                LEFT JOIN results r ON u.id = r.user_id
                WHERE u.is_admin = 0
                GROUP BY u.id, u.name, u.email, u.is_banned, u.created_at
                ORDER BY u.created_at DESC
            ''')
            users = cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[admin_users] {e}')
        users = []
    return render_template('admin_users.html', users=users)


# ── NEW: Ban a user ───────────────────────────────────────────────────────────
@app.route('/admin/users/ban/<int:uid>', methods=['POST'])
@admin_required
def admin_ban_user(uid):
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET is_banned=TRUE WHERE id=%s AND is_admin=0",
                (uid,)
            )
            conn.commit()
        finally:
            conn.close()
        flash('User has been banned.', 'warning')
    except Exception as e:
        app.logger.error(f'[admin_ban_user] {e}')
        flash('Could not ban user.', 'error')
    return redirect(url_for('admin_users'))


# ── NEW: Unban a user ─────────────────────────────────────────────────────────
@app.route('/admin/users/unban/<int:uid>', methods=['POST'])
@admin_required
def admin_unban_user(uid):
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET is_banned=FALSE WHERE id=%s",
                (uid,)
            )
            conn.commit()
        finally:
            conn.close()
        flash('User has been unbanned.', 'success')
    except Exception as e:
        app.logger.error(f'[admin_unban_user] {e}')
        flash('Could not unban user.', 'error')
    return redirect(url_for('admin_users'))


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))


# =============================================================================
# MOCKTEST ROUTES  (NEW — replaces old per-chapter quiz on /quiz)
# =============================================================================

@app.route('/mocktest')
@login_required
def mocktest_home():
    """Landing page: choose class → subject → chapter then launch mock."""
    classes  = ['10th', '11th', '12th']
    subjects = ['Physics', 'Chemistry', 'Math']

    # Build chapter map: { "10th_Physics": ["Motion", "Force", ...], ... }
    chapters = {}
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT class_name, subject, chapter FROM questions ORDER BY class_name, subject, chapter"
            )
            for row in cur.fetchall():
                key = f"{row['class_name']}_{row['subject']}"
                chapters.setdefault(key, [])
                if row['chapter'] not in chapters[key]:
                    chapters[key].append(row['chapter'])
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[mocktest_home chapters] {e}')

    return render_template('mocktest_home.html',
                           classes=classes,
                           subjects=subjects,
                           chapters=chapters)


@app.route('/mocktest/start')
@login_required
def mocktest_start():
    cls  = sanitise_str(request.args.get('class_name', ''), 20)
    sub  = sanitise_str(request.args.get('subject', ''), 50)
    chap = sanitise_str(request.args.get('chapter', ''), 100)   # NEW

    if not cls:
        flash('Please select a class.', 'error')
        return redirect(url_for('mocktest_home'))

    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            # Filter by chapter if provided, else by subject, else whole class
            if chap and chap != 'All Chapters':
                cur.execute(
                    "SELECT * FROM questions WHERE class_name=%s AND subject=%s AND chapter=%s",
                    (cls, sub, chap)
                )
            elif sub and sub != 'All Subjects':
                cur.execute(
                    "SELECT * FROM questions WHERE class_name=%s AND subject=%s",
                    (cls, sub)
                )
            else:
                cur.execute(
                    "SELECT * FROM questions WHERE class_name=%s", (cls,)
                )
            all_qs = cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[mocktest_start] {e}')
        flash('Could not load questions.', 'error')
        return redirect(url_for('mocktest_home'))

    if len(all_qs) < 5:
        flash('Not enough questions available for this selection (need at least 5). Please choose a broader filter or add more questions.', 'error')
        return redirect(url_for('mocktest_home'))

    # Select up to 30 random questions
    selected = random.sample(list(all_qs), min(30, len(all_qs)))
    q_list = [{
        'id':          q['id'],
        'question':    q['question'],
        'subject':     q['subject'],
        'chapter':     q['chapter'],
        'options':     {'A': q['option_a'], 'B': q['option_b'],
                        'C': q['option_c'], 'D': q['option_d']},
        'correct':     q['correct_option'],
        'explanation': q['explanation'] or ''
    } for q in selected]

    # Build display label for header
    scope_label = chap if (chap and chap != 'All Chapters') else \
                  (sub if (sub and sub != 'All Subjects') else 'All Subjects')

    # Store in session — 50 min timer
    session['mocktest'] = {
        'questions':  q_list,
        'class':      cls,
        'subject':    sub or 'All Subjects',
        'chapter':    chap or 'All Chapters',
        'started_at': None,
        'duration':   50 * 60
    }
    return render_template('mocktest.html',
                           questions=json.dumps(q_list),
                           total=len(q_list),
                           duration=50 * 60,
                           cls=cls,
                           subject=scope_label)


@app.route('/mocktest/autosave', methods=['POST'])
@login_required
def mocktest_autosave():
    """AJAX — save current answers to session every 10 s."""
    data = request.get_json() or {}
    if 'mocktest' not in session:
        return jsonify({'error': 'No active mocktest'}), 400
    mt = dict(session['mocktest'])
    mt['saved_answers'] = data.get('answers', {})
    mt['time_remaining'] = data.get('time_remaining', 0)
    session['mocktest'] = mt
    return jsonify({'status': 'saved'})


@app.route('/mocktest/submit', methods=['POST'])
@login_required
def mocktest_submit():
    """AJAX — score the mocktest and save to DB."""
    data = request.get_json() or {}
    mt   = session.get('mocktest')
    if not mt:
        return jsonify({'error': 'No active mocktest'}), 400

    answers   = data.get('answers', {})
    questions = mt['questions']
    total     = len(questions)
    score     = sum(1 for q in questions
                    if answers.get(str(q['id'])) == q['correct'])
    accuracy  = round(score / total * 100, 2) if total else 0
    time_taken = data.get('time_taken', 0)

    # Build result payload (sent back to JS for result page rendering)
    result_qs = []
    for q in questions:
        user_ans = answers.get(str(q['id']))
        result_qs.append({
            'id':          q['id'],
            'question':    q['question'],
            'subject':     q['subject'],
            'chapter':     q['chapter'],
            'options':     q['options'],
            'correct':     q['correct'],
            'user_answer': user_ans,
            'is_correct':  user_ans == q['correct'],
            'explanation': q['explanation']
        })

    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                '''INSERT INTO mocktest_results
                   (user_id, score, total, accuracy, time_taken, answers)
                   VALUES (%s,%s,%s,%s,%s,%s)''',
                (session['user_id'], score, total, accuracy,
                 time_taken, json.dumps(answers))
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[mocktest_submit] {e}')
        return jsonify({'error': 'Could not save result'}), 500

    # Clear session mocktest
    session.pop('mocktest', None)

    return jsonify({
        'score':      score,
        'total':      total,
        'accuracy':   accuracy,
        'time_taken': time_taken,
        'questions':  result_qs
    })


# =============================================================================
# LEADERBOARD  (UPDATED — now shows Mocktest results)
# =============================================================================

@app.route('/leaderboard')
def leaderboard():
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute('''
                SELECT
                    u.id                                                    AS user_id,
                    u.name,
                    COUNT(mr.id)                                            AS attempts,
                    MAX(mr.score)                                           AS best_score,
                    MAX(mr.total)                                           AS total_qs,
                    MAX(mr.accuracy)                                        AS best_accuracy,
                    ROUND(AVG(mr.accuracy)::numeric, 1)                    AS avg_accuracy,
                    MAX(mr.created_at)                                      AS last_attempt
                FROM mocktest_results mr
                JOIN users u ON mr.user_id = u.id
                WHERE u.is_admin = 0
                GROUP BY u.id, u.name
                ORDER BY best_accuracy DESC, best_score DESC
                LIMIT 50
            ''')
            rows = cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[leaderboard] {e}')
        rows = []

    return render_template('leaderboard.html', rows=rows)


# Admin: reset leaderboard
@app.route('/admin/leaderboard/reset', methods=['POST'])
@admin_required
def admin_leaderboard_reset():
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM mocktest_results")
            conn.commit()
        finally:
            conn.close()
        flash('Leaderboard has been reset.', 'success')
    except Exception as e:
        app.logger.error(f'[admin_leaderboard_reset] {e}')
        flash('Could not reset leaderboard.', 'error')
    return redirect(url_for('admin_dashboard'))


# =============================================================================
# PWA ROUTES  (NEW)
# =============================================================================

@app.route('/offline')
def offline():
    """Served by Service Worker as fallback when user is offline."""
    return render_template('offline.html')


@app.route('/static/sw.js')
def service_worker():
    """Serve SW from root scope so it can control all pages."""
    from flask import send_from_directory
    return send_from_directory(app.static_folder, 'sw.js',
                               mimetype='application/javascript')


# =============================================================================
# NOTIFICATION ROUTES  (NEW)
# =============================================================================

@app.route('/notifications/get')
@login_required
def notifications_get():
    """
    Return the 20 most recent notifications for the logged-in user,
    annotated with their read state.
    """
    uid = session['user_id']
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            # Fetch notifications with this user's read state
            cur.execute('''
                SELECT n.id, n.title, n.message, n.created_at,
                       COALESCE(nr.is_read, FALSE) AS is_read
                FROM notifications n
                LEFT JOIN notification_reads nr
                       ON nr.notification_id = n.id AND nr.user_id = %s
                ORDER BY n.created_at DESC
                LIMIT 20
            ''', (uid,))
            rows = cur.fetchall()

            cur.execute('''
                SELECT COUNT(*) AS cnt
                FROM notifications n
                LEFT JOIN notification_reads nr
                       ON nr.notification_id = n.id AND nr.user_id = %s
                WHERE COALESCE(nr.is_read, FALSE) = FALSE
            ''', (uid,))
            unread = cur.fetchone()['cnt']
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[notifications_get] {e}')
        return jsonify({'notifications': [], 'unread_count': 0})

    notifs = [{
        'id':         r['id'],
        'title':      r['title'],
        'message':    r['message'],
        'created_at': str(r['created_at']),
        'is_read':    r['is_read']
    } for r in rows]
    return jsonify({'notifications': notifs, 'unread_count': unread})


@app.route('/notifications/read/<int:nid>', methods=['POST'])
@login_required
def notifications_mark_read(nid):
    """Mark a single notification as read for the current user."""
    uid = session['user_id']
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO notification_reads (notification_id, user_id, is_read, read_at)
                VALUES (%s, %s, TRUE, NOW())
                ON CONFLICT (notification_id, user_id)
                DO UPDATE SET is_read = TRUE, read_at = NOW()
            ''', (nid, uid))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[notifications_mark_read] {e}')
        return jsonify({'error': 'Could not mark as read'}), 500
    return jsonify({'status': 'ok'})


@app.route('/notifications/read-all', methods=['POST'])
@login_required
def notifications_mark_all_read():
    """Mark every notification as read for the current user."""
    uid = session['user_id']
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO notification_reads (notification_id, user_id, is_read, read_at)
                SELECT n.id, %s, TRUE, NOW()
                FROM notifications n
                ON CONFLICT (notification_id, user_id)
                DO UPDATE SET is_read = TRUE, read_at = NOW()
            ''', (uid,))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[notifications_mark_all_read] {e}')
        return jsonify({'error': 'Failed'}), 500
    return jsonify({'status': 'ok'})


# ── Admin: view + send notifications ─────────────────────────────────────────
@app.route('/admin/notifications')
@admin_required
def admin_notifications():
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            # Notifications with read count
            cur.execute('''
                SELECT n.id, n.title, n.message, n.created_at,
                       COUNT(nr.id)                                 AS total_sent,
                       SUM(CASE WHEN nr.is_read THEN 1 ELSE 0 END) AS read_count
                FROM notifications n
                LEFT JOIN notification_reads nr ON nr.notification_id = n.id
                GROUP BY n.id, n.title, n.message, n.created_at
                ORDER BY n.created_at DESC
            ''')
            notifications = cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f'[admin_notifications] {e}')
        notifications = []
    return render_template('admin_notifications.html', notifications=notifications)


@app.route('/admin/notifications/send', methods=['POST'])
@admin_required
def admin_notifications_send():
    title   = sanitise_str(request.form.get('title', ''), 120)
    message = sanitise_str(request.form.get('message', ''), 500)
    if not title or not message:
        flash('Title and message are required.', 'error')
        return redirect(url_for('admin_notifications'))
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            # Insert notification
            cur.execute(
                'INSERT INTO notifications (title, message) VALUES (%s, %s) RETURNING id',
                (title, message)
            )
            notif_id = cur.fetchone()['id']
            # Create a notification_reads row for every non-admin user
            cur.execute('''
                INSERT INTO notification_reads (notification_id, user_id, is_read)
                SELECT %s, id, FALSE FROM users WHERE is_admin = 0
            ''', (notif_id,))
            conn.commit()
            # Count how many users received it
            cur.execute("SELECT COUNT(*) AS cnt FROM users WHERE is_admin = 0")
            count = cur.fetchone()['cnt']
        finally:
            conn.close()
        flash(f'Notification sent to {count} user(s)!', 'success')
    except Exception as e:
        app.logger.error(f'[admin_notifications_send] {e}')
        flash('Failed to send notification.', 'error')
    return redirect(url_for('admin_notifications'))


@app.route('/admin/notifications/delete/<int:nid>', methods=['POST'])
@admin_required
def admin_notifications_delete(nid):
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            # ON DELETE CASCADE removes notification_reads rows automatically
            cur.execute('DELETE FROM notifications WHERE id = %s', (nid,))
            conn.commit()
        finally:
            conn.close()
        flash('Notification deleted.', 'info')
    except Exception as e:
        app.logger.error(f'[admin_notifications_delete] {e}')
        flash('Could not delete notification.', 'error')
    return redirect(url_for('admin_notifications'))


# =============================================================================
# MISC
# =============================================================================

@app.route('/api/me')
def api_me():
    if 'user_id' in session:
        return jsonify({'logged_in': True, 'name': session.get('user_name')})
    return jsonify({'logged_in': False})


@app.route('/ads.txt')
def ads_txt():
    content = 'google.com, pub-1244250782234399, DIRECT, f08c47fec0942fa0\n'
    return app.response_class(content, mimetype='text/plain')


# =============================================================================
# JINJA FILTERS
# =============================================================================

@app.template_filter('enumerate')
def jinja_enumerate(iterable):
    return list(enumerate(iterable))


# =============================================================================
# STARTUP — init DB at import time (works with Gunicorn + plain python)
# =============================================================================
with app.app_context():
    try:
        init_db()
    except Exception as _e:
        print(f"[startup] DB init warning: {_e}")


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
