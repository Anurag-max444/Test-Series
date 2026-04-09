# 🎯 Quizly — Full Stack Quiz Web App

A professional, feature-rich quiz platform built with **Flask + SQLite + HTML/CSS/JS**.

---

## 🚀 Quick Start

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the app
```bash
python app.py
```

### 3. Open in browser
```
http://localhost:5000
```

---

## 🔑 Default Credentials

### Admin Panel
- URL: 
- Email: 
- Password: 


### Student
- Register at: `http://localhost:5000/register`

---

## 📁 Project Structure

```
quizapp/
├── app.py                    # Main Flask application
├── quiz.db                   # SQLite database (auto-created)
├── requirements.txt          # Python dependencies
│
├── templates/                # Jinja2 HTML templates
│   ├── base.html             # Base layout (navbar, footer, modal)
│   ├── index.html            # Homepage with hero + features
│   ├── login.html            # User login
│   ├── register.html         # User registration
│   ├── dashboard.html        # User dashboard with stats
│   ├── quiz_home.html        # Quiz selection page
│   ├── quiz.html             # Active quiz with timer
│   ├── leaderboard.html      # Leaderboard with filters
│   ├── chat.html             # Live global chat
│   ├── about.html            # About SEO page
│   ├── contact.html          # Contact SEO page
│   ├── admin_base.html       # Admin layout with sidebar
│   ├── admin_login.html      # Admin login page
│   ├── admin_dashboard.html  # Admin overview + stats
│   ├── admin_questions.html  # Question management list
│   ├── admin_question_form.html  # Add/Edit question form
│   ├── admin_upload_csv.html # Bulk CSV uploader
│   └── admin_users.html      # User management table
│
└── static/
    ├── css/
    │   ├── style.css         # Main stylesheet (dark theme)
    │   └── admin.css         # Admin panel styles
    └── js/
        └── main.js           # Quiz engine, chat, toasts, modals
```

---

## ✨ Features

### 👤 User System
- Register / Login / Logout with secure password hashing
- Personalized dashboard with score history
- Session-based authentication

### 📝 Quiz System
- Class-wise: 10th, 11th, 12th
- Subject-wise: Physics, Chemistry, Math
- Chapter-wise test selection
- 10 random questions per test
- 60-second timer per question (auto-advance)
- Live progress bar
- Instant answer feedback with explanations
- Score result screen at end

### 🏆 Leaderboard
- Top performers by score %
- Filter by class and subject

### 💬 Live Chat
- Global real-time chat (polls every 3 seconds)
- YouTube-style bubble layout

### 💬 Discussion
- Per-quiz comment section for doubts

### ⚙️ Admin Panel
- Separate admin login at `/admin`
- Dashboard: total users, attempts, questions
- Add / Edit / Delete questions manually
- Bulk question upload via CSV
- View all student data and scores

### 🎨 UI/UX
- Dark mode design with deep blue palette
- Fully mobile responsive
- Smooth animations and transitions
- Toast notifications (success/error/info)
- Loading spinners
- Coming Soon modal for future features

### 🔮 Future Features (placeholders on dashboard)
- 📊 Analytics
- 💎 Premium Tests
- 📱 Mobile App
- 🤖 AI Doubt Solver
- 🎯 Daily Challenge

### 💰 Ad Spaces
- AdSense placeholder banners on homepage, dashboard, quiz, and about pages

---

## 📤 CSV Upload Format

```csv
class_name,subject,chapter,question,option_a,option_b,option_c,option_d,correct_option,explanation
10th,Physics,Motion,What is speed?,Fast,Slow,Distance/Time,None,C,Speed = Distance ÷ Time
```

**Rules:**
- `class_name`: `10th`, `11th`, or `12th`
- `subject`: `Physics`, `Chemistry`, or `Math`
- `correct_option`: `A`, `B`, `C`, or `D`
- `explanation`: optional but recommended

---

## 🛡️ Security Notes for Production

1. Change `app.secret_key` in `app.py` to a long random string
2. Change admin password from `admin123`
3. Set `debug=False` in `app.run()`
4. Use a production WSGI server like **gunicorn**:
   ```bash
   pip install gunicorn
   gunicorn -w 4 app:app
   ```
5. Add HTTPS via nginx or a reverse proxy

---

## 🗃️ Database Tables

| Table | Description |
|-------|-------------|
| `users` | id, name, email, password (hashed), is_admin, created_at |
| `questions` | id, class_name, subject, chapter, question, options A-D, correct_option, explanation |
| `results` | id, user_id, class_name, subject, chapter, score, total, time_taken, created_at |
| `chat_messages` | id, user_id, user_name, message, created_at |
| `comments` | id, user_id, user_name, class_name, subject, chapter, comment, created_at |

---

Built with ❤️ for students across India.
