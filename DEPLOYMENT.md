# CV Pilot 2.0 Deployment — Deadline Checklist

## GitHub
1. Create a new empty repository named `CV-Pilot` on GitHub.
2. From this folder run:
   ```bash
   git init
   git add .
   git commit -m "CV Pilot 2.0 final submission"
   git branch -M main
   git remote add origin YOUR_GITHUB_REPOSITORY_URL
   git push -u origin main
   ```

## Backend — Render
Create a Web Service from the GitHub repository.
- Root Directory: `backend`
- Runtime: Python 3
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app`
- Add `JWT_SECRET_KEY` as a secret.
- After the frontend URL exists, set `FRONTEND_ORIGIN` to that URL.

Render's Flask guide uses `pip install -r requirements.txt` and `gunicorn app:app` for deployment.

## Frontend — Vercel
Import the same GitHub repository.
- Root Directory: `frontend`
- Framework: Vite
- Build Command: `npm run build`
- Output Directory: `dist`
- Environment Variable: `VITE_API_URL=https://YOUR-RENDER-SERVICE.onrender.com/api`

After deployment, copy the Vercel URL into Render's `FRONTEND_ORIGIN` and redeploy the backend.

## Important database note
The starter uses SQLite for a simple final-year demo. It is suitable for a demonstration but is not a durable production database on a typical free server deployment. For a production-grade release, migrate to PostgreSQL.
