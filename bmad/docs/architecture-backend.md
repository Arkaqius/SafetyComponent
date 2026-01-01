# Architecture - Backend

## Overview
Python safety logic organized as modules. No explicit web framework or API layer detected in quick scan.

## Key Building Blocks
- Core logic: `backend/shared/*` (safety components, managers, parsers)
- Templates: `backend/templates/*`
- Tests: `backend/tests/*` (pytest-style layout)

## Configuration
- `backend/app_cfg.yaml`
- `backend/.coveragerc`

## Entry Points
- `backend/SafetyFunctions.py`
- `backend/deploy.py`

## Notes
If this backend exposes APIs or services, run a deep scan to extract routes and interfaces.
