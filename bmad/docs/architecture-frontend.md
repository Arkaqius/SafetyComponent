# Architecture - Frontend

## Overview
React + TypeScript SPA built with Vite. Intended for Home Assistant UI deployment.

## Key Building Blocks
- Entry points: `index.html`, `src/main.tsx`, `src/App.tsx`
- UI components: `src/components/*`
- State and behavior: `src/hooks/*`
- Pages/routes: `src/pages/*` (routing via react-router-dom)
- Styling: Tailwind CSS (`tailwind.config.js`, `src/styles/*`)

## Configuration
- Vite config: `vite.config.ts`
- TS config: `tsconfig*.json`
- Env: `frontend/.env` (deployment and Home Assistant sync)

## Build/Run
- `npm run dev` for local dev
- `npm run build` for production
- `npm run deploy` for SSH deploy to Home Assistant

## Notes
Quick scan only; no API client files detected by name pattern.
