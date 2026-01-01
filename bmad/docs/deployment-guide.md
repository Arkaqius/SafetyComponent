# Deployment Guide

## Frontend
- Deploy via SSH using the built-in script: `npm run deploy` (see `frontend/scripts/deploy.ts`).
- Requires `.env` values: `VITE_SSH_USERNAME`, `VITE_SSH_HOSTNAME`, `VITE_SSH_PASSWORD`, `VITE_FOLDER_NAME`.

## Backend
- A `backend/deploy.py` script exists, but no usage instructions are provided.
- Review script behavior before running in production.
