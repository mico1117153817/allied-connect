# Allied Connect

A web-based employee portal with TimeStation integration. Employees log in with their TimeStation PIN to view hours, request time off, see their calendar, and sign documents. Managers get dashboards for attendance, time-off approvals, pay adjustments, and portal settings.

## Features

### Employee
- **PIN login** — uses existing TimeStation 4-digit PIN (or local PIN for execs)
- **Dashboard** — monthly calendar showing days worked (green), late arrivals (red), and hours
- **Hours summary** — total hours worked per month with shift details
- **Time-off requests** — submit vacation/sick/personal/unpaid requests
- **Email notifications** — receive email when time-off is approved or denied (via Postmark)
- **Documents** — view and sign employee handbooks and policy documents
- **Pay summary** — view back hours and vacation hours for each pay period (8th & 22nd)

### Manager
- **Today's attendance** — live view of who's clocked in and who's not
- **Time-off management** — approve/deny requests (triggers employee email)
- **Pay adjustments** — input back hours and vacation hours for pay dates
- **Document management** — upload handbooks, view who has/hasn't signed
- **Settings** — configure late threshold (default: 1 minute) and portal name
- **Scheduled shifts** — set expected start times (enables late detection)
- **Local accounts** — create accounts for executives not in TimeStation

## Tech Stack
- **Backend:** Python FastAPI, SQLAlchemy, APScheduler
- **Frontend:** React 18, Vite, Tailwind CSS, TanStack Query
- **Database:** SQLite (dev) / PostgreSQL (prod)
- **TimeStation API:** v1.2 with TTL caching (5,000 calls/day limit)
- **Email:** Postmark (@alliedalliancegroupinc.com domain)

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- TimeStation API key (Settings > API Keys in TimeStation)

### Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate  # Windows (git-bash)
# or: source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

# Configure environment
# Edit .env with your TimeStation API key and Postmark API key

# Run
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev  # starts on http://localhost:5173
```

### Set Up Managers
```bash
cd backend
source .venv/Scripts/activate
python -m scripts.set_manager
```
This creates:
- Margaret Montimerano (PIN: 2586) — manager
- Brandon Shampoe (PIN: 7111) — manager
- Marc Mancuso (PIN: 1001) — manager (local account, President)
- Nicole Mancuso (PIN: 1002) — manager (local account, VP)

### Run Tests
```bash
cd backend
source .venv/Scripts/activate
python -m pytest tests/ -v  # 33 tests
```

## Deployment

### Docker
```bash
docker build -t allied-connect .
docker run -p 8000:8000 \
  -e TIMESTATION_API_KEY=your_key \
  -e SECRET_KEY=your_secret \
  -e POSTMARK_API_KEY=your_postmark_key \
  -e DATABASE_URL=postgresql://... \
  allied-connect
```

### Render / Railway
1. Connect this repo
2. Set environment variables (see below)
3. Deploy — the Dockerfile handles everything

### Environment Variables
| Variable | Required | Default | Description |
|---|---|---|---|
| `TIMESTATION_API_KEY` | Yes | — | Your TimeStation API key |
| `SECRET_KEY` | Yes | dev-default | JWT signing secret |
| `DATABASE_URL` | No | sqlite:///./employee_portal.db | Database URL (use PostgreSQL in prod) |
| `POSTMARK_API_KEY` | No | — | Postmark server API key for email notifications |
| `EMAIL_FROM` | No | Allied Connect \<noreply@alliedalliancegroupinc.com\> | Sender email address |
| `FRONTEND_URL` | No | http://localhost:5173 | Frontend URL for CORS |
| `LATE_THRESHOLD_MINUTES` | No | 1 | Minutes after scheduled start to flag as late (overridable via Settings UI) |

## Manager PINs
| Name | PIN | Source |
|---|---|---|
| Margaret Montimerano | 2586 | TimeStation |
| Brandon Shampoe | 7111 | TimeStation |
| Marc Mancuso | 1001 | Local account (President) |
| Nicole Mancuso | 1002 | Local account (VP) |
