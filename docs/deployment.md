# RideWave — Production Deployment Guide: Railway & Vercel

This document outlines the step-by-step process for deploying **RideWave Backend** to **Railway** and the **RideWave Frontend** to **Vercel**.

---

## Part 1: Deploy Backend, PostgreSQL (PostGIS) & Redis on Railway

### 1. Create a Project on Railway
1. Go to [railway.app](https://railway.app) and log in with GitHub.
2. Click **New Project** $\to$ **Provision PostgreSQL**.
3. In the project canvas, click **+ New** $\to$ **Database** $\to$ **Add Redis**.

### 2. Enable PostGIS Extension on Railway PostgreSQL
1. Click on the PostgreSQL card $\to$ click the **Data** or **Connect** tab.
2. In the query terminal or via `psql`, execute:
   ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```

### 3. Deploy the FastAPI Backend
1. In the same project canvas, click **+ New** $\to$ **GitHub Repo**.
2. Select your `RideWave` repository.
3. In the service settings for the repository:
   - Go to **Settings** $\to$ **Root Directory**: set to `/backend`.
   - Railway will automatically detect [`backend/railway.toml`](file:///c:/Users/Hp/Downloads/uber/backend/railway.toml) and [`backend/Dockerfile`](file:///c:/Users/Hp/Downloads/uber/backend/Dockerfile).
4. Go to **Variables** tab and add:
   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (Use Railway variable reference) |
   | `REDIS_URL` | `${{Redis.REDIS_URL}}` (Use Railway variable reference) |
   | `SECRET_KEY` | Generate a random 32-character secret key |
   | `APP_ENV` | `production` |
   | `AI_ENABLED` | `true` (or `false` if not using OpenRouter) |
   | `OPENROUTER_API_KEY` | Your OpenRouter free API key |
   | `OPENROUTER_MODEL` | `meta-llama/llama-3.2-3b-instruct:free` |

5. Go to **Settings** $\to$ **Networking** $\to$ **Generate Domain**.
   - Your backend public URL will look like: `https://backend-production-xxxx.up.railway.app`
   - Test it: `https://backend-production-xxxx.up.railway.app/health/live` $\to$ returns `{"status":"ok"}`.

---

## Part 2: Deploy Next.js Frontend on Vercel

### 1. Import Repository on Vercel
1. Go to [vercel.com](https://vercel.com) and sign in with GitHub.
2. Click **Add New...** $\to$ **Project**.
3. Select your `RideWave` repository.

### 2. Configure Build & Root Directory
1. In the **Root Directory** field, click **Edit** and choose `frontend`.
2. Framework Preset will automatically detect **Next.js**.

### 3. Set Environment Variables
In the **Environment Variables** section, add:
| Key | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://your-railway-backend-url.up.railway.app/api/v1` |

*(Note: Replace with your actual Railway domain generated in Part 1).*

### 4. Deploy
1. Click **Deploy**.
2. Vercel will run `npm run build` and provision an edge CDN URL: `https://ridewave-xxxx.vercel.app`.

---

## Part 3: Verification Checklist

1. Open your Vercel deployment URL.
2. Sign up as a Rider $\to$ map renders with OpenStreetMap tiles.
3. Click on the map to pick coordinates $\to$ request a ride.
4. Open an Incognito window $\to$ log in as Driver $\to$ go `ONLINE`.
5. Driver receives the ride request $\to$ click `Accept` $\to$ `Arrived` $\to$ `Start` $\to$ `Complete`.
6. Inspect the trip appearing in Recent Trips history.
