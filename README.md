# AI Endurance Coach — Backend

Production backend for an AI-powered endurance coaching platform.

## Stack
- Python 3.12
- FastAPI
- Supabase (Postgres)
- Strava API
- Anthropic / OpenAI (planned)

## Local development

1. Create a virtual environment:
   \`\`\`bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   \`\`\`

2. Install dependencies:
   \`\`\`bash
   pip install -r requirements.txt
   \`\`\`

3. Copy environment file:
   \`\`\`bash
   cp .env.example .env
   \`\`\`

4. Run the server:
   \`\`\`bash
   uvicorn app.main:app --reload
   \`\`\`

5. Visit http://localhost:8000/docs for the interactive API docs.

## Project structure

See `app/` — layered architecture: `api/routes` (HTTP) → `services` (business logic) → `db` (persistence). See commit history for incremental build-out.




ai-endurance-coach/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app factory, startup/shutdown
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # Pydantic Settings (env vars)
│   │   └── logging.py          # Structured logging config
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── health.py       # Health check endpoint
│   ├── models/
│   │   └── __init__.py         # Pydantic schemas (empty for now)
│   ├── services/
│   │   └── __init__.py         # Business logic (empty for now)
│   └── db/
│       └── __init__.py         # DB access layer (empty for now)
├── tests/
│   └── __init__.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md