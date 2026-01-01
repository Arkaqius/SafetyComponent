# Project Overview

## Purpose
Safety Component for Home Assistant. The project focuses on monitoring, assessing, and mitigating safety and security risks in a home environment. See `README.md` and the safety docs under `docs/sys/` for hazard analysis and safety goals.

## Executive Summary
This repository contains a multi-part system:
- A frontend UI (React + Vite) intended for Home Assistant UI deployment.
- A backend Python module set that implements safety logic and supporting managers.

## Tech Stack Summary

| Part | Language | Framework/Runtime | Build/Tooling | Notes |
|---|---|---|---|---|
| frontend | TypeScript | React 18 | Vite, Tailwind CSS | Home Assistant UI deployment scripts |
| backend | Python | n/a | pytest (inferred) | No package manifest found |

## Architecture Type
Multi-part repository: separate frontend and backend directories.

## Repository Structure
- `frontend/`: React/Vite UI
- `backend/`: Python safety logic modules and tests
- `docs/`: safety analysis documentation
- `bmad/`: BMAD tooling and outputs

## Related Docs
- Source Tree: `source-tree-analysis.md`
- Architecture: `architecture-frontend.md`, `architecture-backend.md`
- Component Inventory: `component-inventory-frontend.md`, `component-inventory-backend.md`
- Development Guides: `development-guide-frontend.md`, `development-guide-backend.md`
- Deployment Guide: `deployment-guide.md`
- Integration: `integration-architecture.md`
