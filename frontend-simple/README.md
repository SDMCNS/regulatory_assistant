# AeroReg Simple Chatbot (Standalone Frontend)

A lightweight, optional conversational front end for the **Aviation Regulatory Assistant**.

Unlike the comprehensive multi-tab workspace front end in `frontend/`, `frontend-simple/` is completely standalone, minimal, and focused exclusively on a clean, responsive chatbot experience interacting directly with the `POST /llm/ask` endpoint.

---

## Features

- **Direct RAG Chatbot**: Powered entirely by the FastAPI `/llm/ask` endpoint with multi-turn conversation memory.
- **Regulatory Domain Filtering**: Instant one-click chips to restrict retrieval context to specific domains:
  - `All Domains`
  - `Flight Ops (Air Ops)`
  - `Airworthiness & CAMO`
  - `ATM / Air Navigation`
  - `Aerodromes & Ground`
  - `Flight Crew & Licensing`
  - `Drones / UAS`
- **Knowledge Governance & Superseded Alerts**: Automatically detects and renders amber warning notices if referenced chunks originate from deactivated or superseded regulatory instruments.
- **Regulatory Provision Citations**: Expandable citation cards showing the matched Document ID, Origin, Provision Path / Breadcrumb, similarity score, and verbatim text excerpt.
- **Provider Switching**: Toggle between Local LM Studio and Google Gemini Cloud directly in settings.
- **Modern Glassmorphic Dark UI**: High-contrast, responsive interface using modern typography (`Outfit`, `Inter`, `JetBrains Mono`) and zero external CSS bloat.

---

## Quick Start

### 1. Ensure the Backend is Running
From the repository root (`c:\Projects\Regs`):
```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### 2. Install & Start the Simple Chatbot
From this directory (`c:\Projects\Regs\frontend-simple`):
```bash
npm install
npm run dev
```

The simple chatbot will be available at:
👉 **`http://localhost:3001`**

By default, Vite proxies `/api` requests to `http://127.0.0.1:8000`, eliminating any CORS hurdles.

---

## Project Structure

```
frontend-simple/
├── index.html       # Clean, accessible semantic HTML5 layout
├── styles.css       # Obsidian & cyan glassmorphic vanilla CSS design system
├── app.js           # Multi-turn chat logic, citation drawer, domain filtering
├── vite.config.js   # Vite server configured for port 3001 with /api backend proxy
├── package.json     # Node script configuration
└── README.md        # Documentation
```
