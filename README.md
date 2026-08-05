# Employee Portal

A web-based employee portal with TimeStation integration. Employees log in with their TimeStation PIN to view hours, request time off, see their calendar, and sign documents. Managers get dashboards for attendance, time-off approvals, and pay adjustments.

## Features

### Employee
- **PIN login** — uses existing TimeStation 4-digit PIN
- **Dashboard** — monthly calendar showing days worked (green), late arrivals (red), and hours
- **Hours summary** — total hours worked per month with shift details
- **Time-off requests** — submit vacation/sick/personal/unpaid requests
- **Email notifications** — receive email when time-off is approved or denied
- **Documents** — view and sign employee handbooks and policy documents
- **Pay summary** — view back hours and vacation hours for each pay period (8th & 22nd)

### Manager
- **Today's attendance** — live view of who's clocked in and who's not
- **Time-off management** — approve/deny requests (triggers employee email)
- **Pay adjustments** — input back hours and vacation hours for pay dates
- **Document management** — upload handbooks, view who has/hasn't signed
- **Scheduled shifts** — set expected start times (enables late detection)

## Tech Stack
- **Backend:** Python FastAPI, SQLAlchemy, APScheduler
- **Frontend:** React 18, Vite, Tailwind CSS, TanStack Query
- **Database:** SQLite (dev) / PostgreSQL (prod)
- **TimeStation API:** v1.2 with TTL caching (5,000 calls/day limit)
- **Email:** Resend (free tier: 3,000/mo)

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
cp .env.example .env
# Edit .env with your TimeStation API key

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
python -m scripts.set_manager "Employee Name" "Another Name"
```

### Run Tests
```bash
cd backend
source .venv/Scripts/activate
python -m pytest tests/ -v  # 33 tests
```

## Deployment

### Docker
```bash
docker build -t employee-portal .
docker run -p 8000:8000 \
  -e TIMESTATION_API_KEY=your_key \
  -e SECRET_KEY=your_secret \
  -e DATABASE_URL=postgresql://... \
  employee-portal
```

### Render / Railway
1. Connect this repo
2. Set environment variables (see below)
3. Deploy — the Dockerfile handles everything

### Environment Variables
| Variable | Required | Default | Description |
|---|---|---|---|
| `TIMESTATION_API_KEY` | Yes | — | Your TimeStation API key |
| `SECRET_KEY` | Yes | dev-default | JWT signing secret (generate with `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `DATABASE_URL` | No | sqlite:///./employee_portal.db | Database URL (use PostgreSQL in prod) |
| `RESEND_API_KEY` | No | — | Resend API key for email notifications |
| `EMAIL_FROM` | No | noreply@portal.local | Sender email address |
| `FRONTEND_URL` | No | http://localhost:5173 | Frontend URL for CORS |
| `LATE_THRESHOLD_MINUTES` | No | 5 | Minutes after scheduled start to flag as late |

## Security Notes
- PIN-based auth includes rate limiting (5 failures → 15-min lockout, 10 IP failures → 1-hr ban)
- JWT tokens expire after 8 hours
- TimeStation API key is server-side only, never exposed to frontend
- Document files are served through authenticated endpoints
- HTTPS is enforced by the hosting platform

## API Endpoints

### Auth
- `POST /auth/login` — Login with PIN, returns JWT
- `GET /api/me/` — Current employee profile

### Employee
- `GET /api/me/hours?start=Y&end=Z` — Shift history + total hours
- `GET /api/me/calendar?start=Y&end=Z` — Calendar data with late flags
- `GET /api/me/pay-summary?pay_date=Y` — Back/vacation hours for pay date
- `PUT /api/me/email` — Update email address

### Time Off
- `POST /api/time-off` — Create time-off request
- `GET /api/time-off` — List my requests
- `GET /api/time-off/all` — Manager: list all requests
- `PUT /api/time-off/{id}/review` — Manager: approve/deny

### Manager
- `GET /api/manager/today` — Who's at work / not at work
- `GET /api/manager/employees` — All employees with status
- `POST /api/manager/pay-adjustment` — Add back/vacation hours
- `GET /api/manager/pay-adjustments?pay_date=Y` — View adjustments
- `GET /api/manager/approved-time-off?start=Y&end=Z` — Approved time off
- `POST /api/manager/scheduled-shifts` — Set schedule (for late detection)
- `PUT /api/manager/role` — Set employee/manager role

### Documents
- `GET /api/documents` — List active documents
- `POST /api/documents` — Manager: upload document
- `GET /api/documents/{id}/download` — Download document
- `POST /api/documents/{id}/sign` — Sign document
- `GET /api/documents/{id}/signatures` — Manager: view signatures
