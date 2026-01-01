# Source Tree Analysis

## Repository Overview

```
SafetyComponent/
|-- backend/                 # Python safety logic and templates
|-- frontend/                # React/Vite frontend
|-- docs/                    # System safety documentation (root docs)
|-- bmad/                    # BMAD tooling and output
|-- package.json             # Root tooling for BMAD
|-- README.md                # Project overview
```

## Backend (backend/)

```
backend/
|-- shared/                  # Core safety modules and managers
|-- templates/               # Template(s) for component generation
|-- tests/                   # Pytest-style tests
|-- app_cfg.yaml             # Backend configuration
|-- SafetyFunctions.py       # Main safety function module
|-- deploy.py                # Deployment helper script
```

Notes:
- No conventional API routes/controllers detected in quick scan.
- Core logic appears under shared/ modules.

## Frontend (frontend/)

```
frontend/
|-- src/
|   |-- assets/              # Static assets
|   |-- components/          # UI components
|   |-- hooks/               # React hooks
|   |-- pages/               # Page-level components
|   |-- styles/              # Styling assets
|   |-- App.tsx              # Root component
|   |-- main.tsx             # Application entry point
|-- index.html               # Vite entry HTML
|-- package.json             # Dependencies and scripts
|-- vite.config.ts           # Vite config
|-- tailwind.config.js       # Tailwind config
|-- tsconfig.json            # TypeScript config
```

Notes:
- Component-driven SPA structure typical of React + Vite.
