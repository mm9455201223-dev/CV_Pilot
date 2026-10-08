# CV Pilot 2.0 — AI Resume Intelligence & Career Platform

CV Pilot is a final-year BCA Cyber Security & Forensics project that combines resume creation, document analysis, ATS-style scoring, job matching, career recommendations and interview preparation.

## New upgrade set
- Professional printable PDF resume generation
- PDF/DOCX upload and resume parsing
- Existing-resume analysis
- Detailed strengths + priority improvement report
- Skill extraction and skill gaps
- Job description matching using TF-IDF + cosine similarity
- Career-role recommendations based on the user's actual skills
- Direct job-search links for recommended roles
- Interview question generation
- Secure authentication with password hashing and JWT
- SQLite persistence for development

## Run on macOS

### Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Backend: http://127.0.0.1:5000/api/health

### Frontend
Open a second Terminal:
```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173

## Phone testing on the same Wi-Fi
The backend is configured to listen on `0.0.0.0`. For Vite, use:
```bash
npm run dev -- --host 0.0.0.0
```
Then use your Mac's local IP on your phone. For the React API URL, set the `API` constant in `frontend/src/main.jsx` to `http://YOUR_MAC_IP:5000/api`.

## Production roadmap
For the final deployed version, migrate SQLite to PostgreSQL, move uploads to secure object storage, use environment variables for secrets, add CSRF/rate limiting/structured logging, add richer resume templates, and connect approved job feeds/APIs rather than scraping job sites.

## Important product rule
AI suggestions should improve wording and identify gaps, but must not invent qualifications, employment, certifications, projects or achievements that the candidate did not provide.
