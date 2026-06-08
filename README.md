# Pipeline Automatizado — Binario Websites

Automated outreach pipeline for local businesses in Rosario, Argentina. Discovers businesses without a proper website, sends a WhatsApp message offering a free demo site, generates the site using Claude or HTML templates, deploys it to Netlify and GitHub, then sends the live link back.

## Pipeline

```
dataset.json  ->  [1] discover  ->  [2] send  ->  [3] generate-webs  ->  [4] deploy  ->  [5] send-links
```

State is tracked in `data/estado.csv` with one row per lead, updated at each stage.

## How each stage works

**1. discover** — reads `dataset.json` and prints a summary of available leads (total, with phone, with website). Nothing is written.

**2. send** — sends WhatsApp outreach messages via whatsplay (browser automation). Rotates through 20 message templates to avoid detection. Writes results to the CSV status file after each send.

**3. generate-webs** — for every lead with `enviado=SI` and no `project_path`, generates an `index.html`/`styles.css`/`script.js` website using `claude -p <prompt>` with the lead's real data (name, address, phone, rating). Falls back to a pre-built HTML template matched by category if the CLI call fails.

**4. deploy** — runs `git init`, commits, creates a new GitHub repo via `gh repo create`, and deploys to Netlify via `netlify deploy --prod`. Writes the live URL to the CSV.

**5. send-links** — sends the Netlify URL back to each lead that has a `live_url` but no `enviado_links`.

## Directory structure

```
pipeline-automated/
├── main.py                  # CLI entry point and stage orchestration
├── config.py                # Directory paths and environment config
├── run.sh                   # Interactive menu shell script
├── setup.sh                 # Initial environment setup
├── dataset.json             # Input: businesses from Maps/OSM scrape
├── data/
│   └── estado.csv           # Pipeline state (generated at runtime)
├── modules/
│   ├── claude_builder.py    # Website generation via Claude CLI + template fallback
│   ├── deploy.py            # GitHub + Netlify deployment
│   ├── outreach.py          # WhatsApp message sending (whatsplay)
│   ├── send_links.py        # WhatsApp link delivery
│   ├── whatsapp.py          # Legacy Twilio-based sender
│   ├── discovery.py         # Google Maps lead discovery
│   ├── osm_discovery.py     # OpenStreetMap lead discovery
│   ├── analyzer.py          # Lead scoring and filtering
│   ├── analytics.py         # Analytics utilities
│   └── messages.py          # Message template management
├── templates/
│   ├── barber.html
│   ├── beauty.html
│   ├── cafe.html
│   ├── gym.html
│   └── restaurant.html
├── websites/                # Generated sites, one subdirectory per lead
├── dashboard/
│   ├── app.py               # Flask server on port 5000
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── style.css
│       └── script.js
└── logs/
```

## Prerequisites

- Python 3.11+
- Claude CLI with an active session (`claude` binary in PATH)
- GitHub CLI (`gh`) authenticated
- Netlify CLI (`netlify`) authenticated
- A WhatsApp account accessible from the machine (for whatsplay browser automation)

## Setup

```bash
git clone <repo-url>
cd pipeline-automated
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install flask whatsplay
```

Set environment variables (`.env` file or export):

```
GITHUB_USERNAME=your_github_username
```

## Usage

### Interactive menu

```bash
./run.sh
```

### Individual stages

```bash
# Preview the dataset
python3 main.py --discover dataset.json

# Send outreach messages and create estado.csv
python3 main.py --send dataset.json data/estado.csv

# Generate websites for interested leads
python3 main.py --generate-webs data/estado.csv

# Deploy to GitHub and Netlify
python3 main.py --deploy data/estado.csv

# Send live URLs via WhatsApp
python3 main.py --send-links data/estado.csv

# Run all stages in sequence
python3 main.py --full dataset.json data/estado.csv

# Show current pipeline status
python3 main.py --status data/estado.csv
```

## Dataset format

`dataset.json` is an array of business objects from Google Maps or OpenStreetMap:

```json
[
  {
    "title": "Peluqueria Lopez",
    "phone": "3413001234",
    "website": "https://instagram.com/peluquerialopez",
    "categoryName": "Peluqueria",
    "address": "Bv. Orono 1234, Rosario",
    "rating": 4.7,
    "reviewCount": 89
  }
]
```

Leads with a standalone website (`sitio_propio`) are skipped. Leads with only a social media profile, a WhatsApp link, or no website at all are targeted.

## Status CSV columns

| Column | Description |
|---|---|
| nombre | Business name |
| telefono | Phone number |
| categoria | Business category |
| direccion | Address |
| puntaje | Star rating |
| resenas | Review count |
| enviado | SI / NO |
| fecha_envio | ISO timestamp of outreach send |
| project_path | Local path to the generated site directory |
| live_url | Netlify URL after deploy |
| enviado_links | SI / NO |
| fecha_envio_links | ISO timestamp of link delivery |

## Dashboard

```bash
cd dashboard
python3 app.py
```

Open `http://localhost:5000`. The dashboard reads `data/estado.csv` directly and auto-refreshes every 30 seconds. It shows the pipeline funnel, per-stage KPIs, activity timeline, category breakdown, lead table with search/filter, and deployed sites.

## WhatsApp session

The outreach and send-links steps open a Chromium window via whatsplay for browser-based WhatsApp Web automation. The session is persisted in `~/whatsapp_session/` so the QR code scan is only required once.

## Website generation

`claude_builder.py` calls `claude -p <prompt>` to generate a custom site from the lead's real data (name, address, phone, rating, review count, category). The prompt explicitly instructs Claude not to use SaaS/startup templates and to produce something that feels local and specific.

Template fallback categories: `barber`, `beauty`, `cafe`, `gym`, `restaurant`.
