# RideWave Local Development & Setup Guide

A complete guide for running, migrating, and testing RideWave on a local developer workstation across **Windows (PowerShell & CMD)** and **macOS / Linux (Bash)**.

---

## 1. Prerequisites

| Component | Minimum Version | Required / Optional | Purpose |
|---|---|---|---|
| **Python** | 3.11+ | **Required** | FastAPI backend, Alembic migrations, Pytest |
| **Node.js** | 18+ (20 recommended) | **Required** | Next.js frontend |
| **npm** | 9+ | **Required** | Frontend package manager |
| **Docker & Docker Compose** | 24+ | *Optional* | PostgreSQL with PostGIS & Redis container runtime |
| **Ollama** | 0.3+ | *Optional* | Local zero-cost AI assistant (`llama3.2:3b`) |

---

## 2. Step-by-Step Setup from a Clean Clone

### Step 2.1: Clone the Repository
```bash
git clone https://github.com/vamsi080/RideWave.git
cd RideWave
```

### Step 2.2: Configure Environment Variables
Copy the sanitized environment configuration template:

```bash
# Linux / macOS / Git Bash
cp .env.example .env

# Windows (PowerShell)
Copy-Item .env.example .env

# Windows (Command Prompt)
copy .env.example .env
```

> [!IMPORTANT]
> **Environment Settings to Verify:**
> - `SECRET_KEY`: Must be at least 32 characters long. The production validator will abort startup if it is insecure.
> - `DATABASE_URL`: Use `postgresql+psycopg://ridewave:ridewave_password@localhost:5432/ridewave_db` for PostgreSQL, or `sqlite+aiosqlite:///./ridewave.db` for zero-dependency local testing.
> - `REDIS_URL`: `redis://localhost:6379/0` (fallback mocks are automatically used if Redis is offline during local test scripts).
> - `AI_ENABLED`: Set to `true` to enable the conversational assistant or `false` to disable without affecting core ride booking.

---

## 3. Backend Setup & Database Migrations

### Windows (PowerShell)
```powershell
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install ".[dev]" aiosqlite "pydantic[email]" "sqlalchemy[asyncio]" greenlet

# Run Alembic database migrations to head
alembic upgrade head

# Start FastAPI development server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Windows (Command Prompt - CMD)
```cmd
cd backend

:: Create virtual environment
python -m venv venv

:: Activate virtual environment
venv\Scripts\activate.bat

:: Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install ".[dev]" aiosqlite "pydantic[email]" "sqlalchemy[asyncio]" greenlet

:: Run Alembic database migrations to head
alembic upgrade head

:: Start FastAPI development server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### macOS / Linux (Bash)
```bash
cd backend

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install ".[dev]" aiosqlite "pydantic[email]" "sqlalchemy[asyncio]" greenlet

# Run Alembic database migrations to head
alembic upgrade head

# Start FastAPI development server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

---

## 4. Frontend Setup

In a new terminal window:

### Windows (PowerShell or CMD)
```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

### macOS / Linux (Bash)
```bash
cd frontend
npm install
npm run dev
```

The Next.js application will be available at [http://localhost:3000](http://localhost:3000), communicating with the backend API at [http://127.0.0.1:8000](http://127.0.0.1:8000).

---

## 5. Running Tests

Run the complete backend integration and concurrency test suite:

```bash
cd backend

# Run all 21 unit, concurrency, security, and lifecycle tests
pytest -v

# Run with verbose output and test timing
pytest -v -rP
```

---

## 6. Running the Performance Benchmark

Execute the reproducible spatial matching benchmark across driver densities (10, 50, 100, 500):

```bash
cd backend

# Fast dry run (2 iterations)
python scripts/benchmark_matching.py --dry-run

# Standard benchmark (100 iterations per density with JSON export)
python scripts/benchmark_matching.py --iterations 100 --warmup 10 --output ../docs/benchmark_results.json
```

---

## 7. Running with Docker Compose (PostgreSQL & Redis)

If you prefer running isolated PostGIS and Redis containers:

```bash
# Start PostgreSQL (port 5432) and Redis (port 6379) bound to 127.0.0.1
docker compose up -d postgres redis

# Check container health status
docker compose ps

# Apply schema migrations
cd backend
alembic upgrade head
```

---

## 8. Setting Up Local AI Assistant (Ollama)

RideWave uses zero-cost local LLM inference for trip planning and driver recommendations:

1. Install Ollama from [ollama.com](https://ollama.com).
2. Pull the lightweight 3B model:
   ```bash
   ollama pull llama3.2:3b
   ```
3. Start Ollama:
   ```bash
   ollama serve
   ```
4. Configure `.env`:
   ```env
   AI_ENABLED=true
   AI_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=llama3.2:3b
   ```
If Ollama is offline or unavailable, the backend gracefully falls back to deterministic rule-based trip assistance without crashing or disrupting ride dispatch.

---

## 9. Troubleshooting & FAQ

### Issue: `RuntimeError: SECRET_KEY must be at least 32 characters in production mode`
- **Cause**: Security validator detected a default or truncated secret key.
- **Solution**: Set `SECRET_KEY` in your `.env` to a secure 32+ character string:
  ```env
  SECRET_KEY=ridewave-super-secure-production-secret-key-32-chars
  ```

### Issue: PowerShell blocks script execution (`PSSecurityException`)
- **Cause**: Default Windows execution policy blocks activating virtual environments or running `npm`.
- **Solution**: Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`, or execute commands with `npm.cmd` and `python -m pytest`.

### Issue: `ConnectionRefusedError: [Errno 111 / WinError 1225] connecting to localhost:5432`
- **Cause**: PostgreSQL is not running locally.
- **Solution**: Either start Docker via `docker compose up -d postgres`, or configure `DATABASE_URL=sqlite+aiosqlite:///./ridewave.db` in `.env` for zero-dependency local development.

### Issue: `alembic: command not found`
- **Cause**: Python virtual environment is not activated.
- **Solution**: Activate `backend/venv` or run through python:
  ```bash
  python -m alembic upgrade head
  ```
