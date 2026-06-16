# Shorts Experiment Platform

A reusable, open-source platform for randomized experiments using a mobile-first, YouTube Shorts-style video feed. It supports consent and pre-survey flows, randomized control/treatment assignment, deterministic local-video sequences, timed exposure, post-surveys, participant completion redirects, and detailed behavioral logging.

This public distribution contains the software used to run the experiment, but **does not include the original study videos, participant data, content database, internal research documents, ethics materials, or deployment secrets**.

## Features

- Mobile-first Shorts reel with touch, button, and keyboard navigation
- Server-authoritative timed exposure window
- Control/treatment randomization and deterministic media sequences
- Consent, pre-survey, attention check, post-survey, debrief, and completion flow
- Impression-before-event logging with video title, surface, click source, rank, condition, exposure ID, and playback diagnostics
- SQLite for local development and PostgreSQL support for concurrent production fieldwork
- Optional panel-provider status redirects and secured study monitoring
- FastAPI/SQLAlchemy backend, Next.js/React/Tailwind frontend, pytest and Playwright tests

## Repository layout

- `backend/`: database models, APIs, randomization, logging, and study lifecycle
- `frontend/`: participant interface and server-side API bridge
- `study_media/`: empty control/treatment media folders; add your own MP4 files
- `analysis_code/`: reserved reproducible analysis pipeline; data and generated outputs are excluded
- `scripts/`: setup, sequence-building, validation, migration, backup, and deployment helpers
- `tests/`: backend and end-to-end regression tests

## Quick start: local development

Requirements: Node.js 20+, Python 3.11+, and npm.

```bash
cp .env.example .env
npm install
npm --prefix frontend install
npm run setup:backend
python3 scripts/seed_videos.py
npm run dev:mobile
```

Open <http://localhost:3000>. With no study MP4 files present, the application uses openly hosted toy seed videos for development.

To install the Playwright browser and run verification:

```bash
npm run test:install
npm test
npm run build
```

## Quick start: Docker Compose

```bash
docker compose up --build
```

The frontend is exposed at <http://localhost:3000>, the backend at <http://localhost:8000>, and participant behavior is stored in PostgreSQL. The content inventory remains in local SQLite. Change all example credentials before any real deployment.

## Add your experiment videos

Place legally usable MP4 files in:

```text
study_media/control/
study_media/treatment/
```

Use numeric filename prefixes to define a deterministic order. See `study_media/README.md`. The included `scripts/build_study_sequences.py` can prepare more advanced manifests. The original experiment media is not included.

## Customize before fieldwork

The included participant flow reflects the original experiment implementation and must be reviewed before reuse. At minimum, customize:

- consent and participant-information text
- pre- and post-survey questions
- attention check assets/content
- treatment labels, media, sequence logic, and exposure duration
- completion/screening redirect URLs for your panel provider
- database credentials, monitoring token, backups, retention, and access controls

Researchers are responsible for obtaining appropriate ethical approval, informed consent, media rights, privacy safeguards, and data-processing arrangements.

## Data model and logging

Content and behavior storage are separated. Behavior records include sessions, impressions, events, and search queries. Study sessions retain random assignment and lifecycle timestamps. Impressions are logged before clicks/events, and reel activity uses stable session and exposure identifiers.

For production fieldwork with simultaneous participants, use PostgreSQL for the behavior database. Never commit real `.env` files, databases, participant exports, logs, or restricted media.

## Panel-provider integration

The original flow accepts a participant ID through `?pid=...` and contains configurable-style status redirect helpers in `frontend/lib/norstat.ts`. Replace these endpoints and terminology if using another panel provider. Do not assume the included URLs are appropriate for a new study.

## License

Software is released under the ISC License. Third-party media and attention-check assets may have separate attribution or licensing terms; see `frontend/public/study/ATTRIBUTION.md`.
