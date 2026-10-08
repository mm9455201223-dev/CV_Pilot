import io
import json
import os
import re
import secrets
import sqlite3
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, get_jwt_identity, jwt_required
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv()
BASE = Path(__file__).resolve().parent
DB = BASE / "cvpilot.db"
UPLOADS = BASE / "uploads"
UPLOADS.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", secrets.token_hex(32))
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=8)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")
CORS(app, resources={r"/api/*": {"origins": FRONTEND_ORIGIN}})
JWTManager(app)

ALLOWED_EXTENSIONS = {"pdf", "docx"}
SKILLS = {
    "python", "java", "javascript", "typescript", "react", "node.js", "flask", "django",
    "sql", "mysql", "postgresql", "mongodb", "git", "github", "linux", "windows",
    "networking", "wireshark", "nmap", "burp suite", "metasploit", "kali linux",
    "cybersecurity", "penetration testing", "ethical hacking", "soc", "siem", "splunk",
    "aws", "azure", "docker", "kubernetes", "html", "css", "rest api", "machine learning",
    "data analysis", "pandas", "numpy", "scikit-learn", "incident response", "cloud security",
    "forensics", "autopsy", "volatility", "communication", "leadership", "problem solving"
}

ROLE_RULES = {
    "Cybersecurity Intern": {"skills": {"python", "linux", "networking", "wireshark", "nmap", "cybersecurity"}, "gaps": ["SIEM", "Incident Response", "Cloud Security"]},
    "SOC Analyst Intern": {"skills": {"linux", "networking", "siem", "soc", "wireshark"}, "gaps": ["Splunk", "Incident Response", "Log Analysis"]},
    "Security Testing Intern": {"skills": {"linux", "nmap", "burp suite", "penetration testing", "python"}, "gaps": ["Web Security", "OWASP", "API Security"]},
    "Network Security Intern": {"skills": {"networking", "linux", "wireshark", "nmap"}, "gaps": ["Firewalls", "IDS/IPS", "Cloud Networking"]},
    "Junior Python Developer": {"skills": {"python", "git", "sql", "rest api"}, "gaps": ["Testing", "Docker", "CI/CD"]},
    "Data Analyst Intern": {"skills": {"python", "sql", "pandas", "numpy", "data analysis"}, "gaps": ["Power BI", "Statistics", "Data Visualization"]},
}


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS resumes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
      title TEXT NOT NULL, data TEXT NOT NULL, score INTEGER DEFAULT 0,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS analyses(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
      resume_id INTEGER, source TEXT NOT NULL, result TEXT NOT NULL,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(resume_id) REFERENCES resumes(id)
    );
    """)
    c.commit(); c.close()


def extract_skills(text):
    low = text.lower()
    return sorted([s for s in SKILLS if re.search(r"(?<!\w)" + re.escape(s) + r"(?!\w)", low)])


def resume_text(data):
    keys = ["summary", "education", "skills", "experience", "projects", "certifications", "linkedin", "github"]
    return " ".join(str(data.get(k, "")) for k in keys)


def analyze_resume(data):
    text = resume_text(data)
    sections = {k: bool(str(data.get(k, "")).strip()) for k in ["summary", "education", "skills", "experience", "projects", "certifications"]}
    skills = extract_skills(text)
    words = len(text.split())
    quantified = bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:%|x|users|hours|days|projects|devices|records)?\b", text, re.I))
    score = 0
    score += 12 if sections["summary"] else 0
    score += 15 if sections["education"] else 0
    score += 15 if sections["skills"] else 0
    score += 15 if sections["projects"] else 0
    score += 10 if sections["experience"] else 0
    score += 8 if sections["certifications"] else 0
    score += min(10, len(skills))
    score += 5 if quantified else 0
    score += 5 if words >= 150 else 0
    score = min(100, score)
    ats = min(100, score + (5 if data.get("linkedin") else 0) + (5 if data.get("github") else 0))
    strengths, suggestions = [], []
    if sections["projects"]: strengths.append("Relevant project evidence is present.")
    if len(skills) >= 5: strengths.append("The resume contains a useful technical skill set.")
    if sections["education"]: strengths.append("Education section is clearly represented.")
    if not sections["summary"]: suggestions.append("Add a 2–3 line role-focused professional summary.")
    if not sections["projects"]: suggestions.append("Add 2–3 relevant projects with technologies and outcomes.")
    if not sections["experience"]: suggestions.append("Add internships, volunteering, labs, freelance work, or practical experience if applicable.")
    if not quantified: suggestions.append("Add truthful measurable outcomes where possible (time saved, users, records, accuracy, scale, etc.).")
    if not data.get("linkedin"): suggestions.append("Add a LinkedIn profile URL if you have one.")
    if not data.get("github"): suggestions.append("Add GitHub if you have relevant public projects.")
    if words < 150: suggestions.append("Add useful detail; avoid both under-filled and overly long sections.")
    return {
        "score": score, "ats_score": ats, "skills": skills, "sections": sections,
        "word_count": words, "strengths": strengths, "suggestions": suggestions,
        "priority_actions": suggestions[:3]
    }


def match_resume_job(resume, job):
    try:
        mat = TfidfVectorizer(stop_words="english").fit_transform([resume, job])
        similarity = float(cosine_similarity(mat[0:1], mat[1:2])[0][0]) * 100
    except ValueError:
        similarity = 0
    rs, js = set(extract_skills(resume)), set(extract_skills(job))
    matched, missing = sorted(rs & js), sorted(js - rs)
    skill_score = (len(matched) / len(js) * 100) if js else 0
    overall = round(similarity * 0.55 + skill_score * 0.45)
    return overall, matched, missing


def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_uploaded_text(path):
    ext = path.suffix.lower()
    if ext == ".pdf":
        import fitz
        doc = fitz.open(path)
        return "\n".join(page.get_text() for page in doc)
    if ext == ".docx":
        from docx import Document
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    raise ValueError("Unsupported file type")


def text_to_resume_data(text):
    low = text.lower()
    def section(*names):
        pattern = r"(?:^|\n)\s*(?:" + "|".join(re.escape(n) for n in names) + r")\s*[:\-]?\s*\n?(.*?)(?=\n\s*(?:summary|objective|education|skills|technical skills|experience|work experience|projects|certifications|achievements|contact|linkedin|github)\b|\Z)"
        m = re.search(pattern, text, re.I | re.S)
        return m.group(1).strip() if m else ""
    return {
        "summary": section("summary", "objective"),
        "education": section("education"),
        "skills": section("skills", "technical skills"),
        "experience": section("experience", "work experience"),
        "projects": section("projects"),
        "certifications": section("certifications", "achievements"),
        "linkedin": "linkedin.com" if "linkedin.com" in low else "",
        "github": "github.com" if "github.com" in low else ""
    }


def career_recommendations(data):
    skills = set(extract_skills(resume_text(data)))
    results = []
    for role, rule in ROLE_RULES.items():
        matched = sorted(skills & rule["skills"])
        missing = sorted(rule["skills"] - skills)
        pct = round(len(matched) / len(rule["skills"]) * 100) if rule["skills"] else 0
        results.append({"role": role, "match": pct, "matched": matched, "gaps": missing or rule["gaps"]})
    return sorted(results, key=lambda x: x["match"], reverse=True)


def save_analysis(uid, resume_id, source, result):
    c = db(); c.execute("INSERT INTO analyses(user_id,resume_id,source,result) VALUES(?,?,?,?)", (uid, resume_id, source, json.dumps(result))); c.commit(); c.close()


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "CV Pilot API", "version": "2.0"})


@app.post("/api/auth/register")
def register():
    data = request.get_json() or {}
    name, email, password = data.get("name", "").strip(), data.get("email", "").strip().lower(), data.get("password", "")
    if len(name) < 2 or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email): return jsonify({"error": "Valid name and email are required"}), 400
    if len(password) < 8: return jsonify({"error": "Password must be at least 8 characters"}), 400
    c = db()
    try:
        cur = c.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)", (name, email, generate_password_hash(password)))
        c.commit(); uid = cur.lastrowid
    except sqlite3.IntegrityError: return jsonify({"error": "Email already registered"}), 409
    finally: c.close()
    return jsonify({"token": create_access_token(identity=str(uid)), "user": {"id": uid, "name": name, "email": email}}), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json() or {}; c = db(); u = c.execute("SELECT * FROM users WHERE email=?", (data.get("email", "").lower(),)).fetchone(); c.close()
    if not u or not check_password_hash(u["password_hash"], data.get("password", "")): return jsonify({"error": "Invalid credentials"}), 401
    return jsonify({"token": create_access_token(identity=str(u["id"])), "user": {"id": u["id"], "name": u["name"], "email": u["email"]}})


@app.get("/api/resumes")
@jwt_required()
def resumes():
    uid = int(get_jwt_identity()); c = db(); rows = c.execute("SELECT id,title,score,created_at FROM resumes WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall(); c.close()
    return jsonify([dict(r) for r in rows])


@app.post("/api/resumes")
@jwt_required()
def save_resume():
    uid = int(get_jwt_identity()); data = request.get_json() or {}; title = data.get("title", "My Resume").strip()[:100]
    analysis = analyze_resume(data); c = db(); cur = c.execute("INSERT INTO resumes(user_id,title,data,score) VALUES(?,?,?,?)", (uid, title, json.dumps(data), analysis["score"])); c.commit(); rid = cur.lastrowid; c.close()
    save_analysis(uid, rid, "builder", analysis)
    return jsonify({"id": rid, "analysis": analysis}), 201


@app.post("/api/analyze")
@jwt_required()
def analyze():
    data = request.get_json() or {}; result = analyze_resume(data); save_analysis(int(get_jwt_identity()), None, "builder", result); return jsonify(result)


@app.post("/api/upload-analyze")
@jwt_required()
def upload_analyze():
    f = request.files.get("resume")
    if not f or not f.filename: return jsonify({"error": "Choose a PDF or DOCX resume."}), 400
    if not allowed_file(f.filename): return jsonify({"error": "Only PDF and DOCX files are supported."}), 400
    safe = secure_filename(f.filename)
    path = UPLOADS / f"{secrets.token_hex(8)}_{safe}"
    f.save(path)
    try:
        text = extract_uploaded_text(path)
        data = text_to_resume_data(text)
        result = analyze_resume(data); result["extracted_text_preview"] = text[:1200]
        result["source_file"] = safe
        save_analysis(int(get_jwt_identity()), None, "upload", result)
        return jsonify({"data": data, "analysis": result})
    except Exception as e:
        return jsonify({"error": f"Could not read the document: {e}"}), 422
    finally:
        try: path.unlink(missing_ok=True)
        except Exception: pass


@app.post("/api/match")
@jwt_required()
def match():
    data = request.get_json() or {}; job = data.get("job_description", ""); resume = resume_text(data)
    if not job.strip(): return jsonify({"error": "Job description is required"}), 400
    score, matched, missing = match_resume_job(resume, job)
    return jsonify({"match_score": score, "matched_skills": matched, "missing_skills": missing, "actions": [f"Add or demonstrate {s} only if you genuinely have it." for s in missing[:5]]})


@app.post("/api/career-recommendations")
@jwt_required()
def career():
    data = request.get_json() or {}; return jsonify({"recommendations": career_recommendations(data)})


@app.post("/api/interview")
@jwt_required()
def interview():
    data = request.get_json() or {}; role = data.get("role", "the target role"); skills = extract_skills(data.get("resume_text", ""))
    qs = [f"Tell me about yourself and why you are interested in {role}.", "Walk me through your strongest project and your specific contribution.", "Describe a technical problem you faced and how you solved it.", f"How have you used {skills[0] if skills else 'your main technical skill'} in a real project?", "What would you improve if you had more time on your main project?", "Describe a situation where you had to learn a new technology quickly."]
    return jsonify({"questions": qs})


@app.post("/api/generate-pdf")
@jwt_required()
def generate_pdf():
    data = request.get_json() or {}; title = data.get("name", "Resume")
    buffer = io.BytesIO(); styles = getSampleStyleSheet(); story = []
    name_style = ParagraphStyle("Name", parent=styles["Title"], alignment=TA_CENTER, fontSize=20, spaceAfter=5)
    contact_style = ParagraphStyle("Contact", parent=styles["Normal"], alignment=TA_CENTER, fontSize=9, textColor=colors.HexColor("#555555"), spaceAfter=12)
    section_style = ParagraphStyle("Section", parent=styles["Heading2"], fontSize=11, leading=14, spaceBefore=7, spaceAfter=4, textColor=colors.HexColor("#243b6b"))
    body_style = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=9.5, leading=13, spaceAfter=5)
    story.append(Paragraph(title or "Resume", name_style))
    contact = " • ".join(x for x in [data.get("email"), data.get("phone"), data.get("linkedin"), data.get("github"), data.get("location")] if x)
    if contact: story.append(Paragraph(contact, contact_style))
    for label, key in [("SUMMARY", "summary"), ("EDUCATION", "education"), ("SKILLS", "skills"), ("EXPERIENCE", "experience"), ("PROJECTS", "projects"), ("CERTIFICATIONS & ACHIEVEMENTS", "certifications")]:
        value = str(data.get(key, "")).strip()
        if value:
            story.append(Paragraph(label, section_style)); story.append(Paragraph(value.replace("\n", "<br/>"), body_style))
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=14*mm, bottomMargin=14*mm, title="CV Pilot Resume")
    doc.build(story); buffer.seek(0)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name="CV_Pilot_Resume.pdf")


@app.errorhandler(413)
def too_large(e): return jsonify({"error": "Uploaded file is too large (max 8 MB)."}), 413


init_db()
if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000)
