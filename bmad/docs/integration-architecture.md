# Integration Architecture

## Parts
- frontend (React/Vite UI)
- backend (Python safety logic)

## Observed Integration Signals (quick scan)
- No explicit API client files detected in frontend.
- No API route/controller folders detected in backend.
- No shared workspace tooling detected (no pnpm-workspace, lerna, nx, etc.).

## Likely Integration Model
- Frontend appears to target Home Assistant UI deployment (see frontend/README.md deploy instructions).
- Backend likely provides safety logic modules used by Home Assistant or separate runtime.
- Direct in-repo coupling between frontend and backend is not evident from filename scan.

## Recommended Follow-up
- Confirm how the frontend communicates with safety logic (Home Assistant services, REST, websocket, or local integration).
- If APIs exist, re-run with deep scan to extract endpoints and contracts.
