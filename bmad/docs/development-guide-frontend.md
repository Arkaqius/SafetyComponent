# Development Guide - Frontend

## Prerequisites
- Node.js >= 18
- npm >= 7
- Optional: NVM (recommended)

## Local Development
- `nvm use && npm i && npm run dev`

## Build
- `npm run build`

## Deploy (Home Assistant)
- Configure `.env` values: `VITE_SSH_USERNAME`, `VITE_SSH_HOSTNAME`, `VITE_SSH_PASSWORD`, `VITE_FOLDER_NAME`
- Run: `npm run deploy`

## TypeScript Sync
- Configure `.env`: `VITE_HA_URL`, `VITE_HA_TOKEN`
- Run: `npm run sync`
