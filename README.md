# Event Horizon

Explainable AI match intelligence built on Azure. Event Horizon turns synthetic football events into live statistics, evidence-linked stories, synchronized graphics, and personalized recaps for fans, analysts, studios, and streaming teams.

## Try the project — no installation required

1. **Open the live website:** [Event Horizon on Azure](https://ehdemo-app.icypond-d7044f5d.swedencentral.azurecontainerapps.io/).
2. **Watch the demonstration:** [Event Horizon — 1 minute 49 seconds](https://youtu.be/NtMRFDtNP0Q).
3. Select **English** and **Analyst** in section **01** to start the walkthrough below.
4. Use the numbered navigation **01–14** to move between sections. New live moments appear as the match progresses.
5. If the live match has ended, open [the complete match replay](https://ehdemo-app.icypond-d7044f5d.swedencentral.azurecontainerapps.io/demo). The replay does not depend on a developer's laptop.

### Availability for judging

**Planned hosting period: through 10 November 2026 at 23:59 Pacific Standard Time (UTC−08:00), equivalent to 11 November 2026 at 07:59 UTC.** Use the public website link above throughout this period.

Azure was checked on **27 October 2026**: the application was running, public ingress was enabled, the subscription was enabled, the minimum replica count was one, and the readiness endpoint returned HTTP 200 with `status: ok`. These checks confirm the current deployment; they do not guarantee uninterrupted future uptime, available credit, or Azure service health. The site must remain funded and enabled until judging ends.

**Access:** match viewing and public evidence do not require an account. Server-side restart, new Replay Lab comparisons, and editorial publishing/suppression require operator access. Judges who need these controls must receive separate test credentials through the submission's testing instructions. Do not publish credentials in this repository.

## Architecture

Synthetic simulator and video frames → Azure Functions event relay → validated match state and statistics → Microsoft Foundry agents through Microsoft Agent Framework → verified narrative → personalized screen cards and recap.

The analysis, writing, and fact-checking agents have separate roles and share evidence references. Strict structured outputs, numeric grounding, bounded repair, and factual fallback protect the published story. Azure Container Apps hosts the application. Application Insights and Azure Monitor provide operational telemetry. Infrastructure templates are in `azure/infra/`; deployment and smoke checks are in `azure/scripts/`. Run `python azure/scripts/deploy.py --help` for required deployment arguments. Select your own resource group, region, model deployment, and credentials. Do not commit generated credentials or deployment receipts.

## Judge walkthrough — all 14 sections

Use the numbered navigation on the hosted project. Start with English and Analyst mode. Live episodes appear as the match progresses; the full replay remains available after full time. Viewer access is public. Editorial mutation controls require an operator account and are not part of anonymous viewer access.

### 01. One match, understood

- **What to do:** Change **Viewing mode** between Fan, Analyst, and Player Focus. Select a favourite team and player. Check the visible feedback and the different depth of explanations. Reload to confirm saved preferences.
- **What to check:** Different viewing modes use the same match facts with different levels of detail; the selected preferences remain after reload.

### 02. Live match & statistics

- **What to do:** Watch the clock and players advance. Check passes, shots, possession, and pressure. Compare **Alongside the match** and **Over the image** in section 1.
- **What to check:** The match clock, player positions, and calculated statistics update together.

### 03. Reproduce the match

- **What to do:** Open **Replay Lab**. Inspect the repeatability explanation. Starting a new server-side comparison requires operator access. For an independent local comparison, run `python3 -B -c "from reproducibility_lab import verify; print(verify(42,30))"`. Matching seeds and scenarios must produce matching event hashes.
- **What to check:** Identical seeds and scenarios produce identical event hashes. A server-side test requires operator access.

### 04. Key moments & review

- **What to do:** Select a shot, goal, pressure change, or rhythm change in **How the game unfolded**. The selected breakdown stays open while live play continues. **Broadcast desk** is the editorial view; publishing and suppression require operator access.
- **What to check:** A selected moment can be inspected without losing it when another live event arrives.

### 05. From event to insight

- **What to do:** Select a recent completed pass. Check the route, distance, forward/backward progress, and completed-pass counter. Open **Verify the data path**. **Pin episode** holds the selection; **Follow live play** returns to live updates.
- **What to check:** The displayed explanation can be traced to the selected pass and its calculated metrics.

### 06. One episode, three formats

- **What to do:** Compare Studio, Broadcast, and Streaming cards. Their wording and length differ while the shared fact fingerprint stays the same.
- **What to check:** Three presentation formats share the same underlying facts.

### 07. Five connected stages

- **What to do:** Inspect Event received, Context calculated, Meaning explained, Screen display, and Your perspective. In **Why this moment?**, select an episode, step through its event sequence, and inspect the source links. Arrows show earlier passes in the attack; player positions belong to the selected frame.
- **What to check:** Every stage connects an event to a viewer-facing explanation with inspectable evidence.

### 08. Made for your perspective

- **What to do:** Open **Statistics on screen** and change the selected metrics. Compare fan and analyst views of the same period. Select Player Focus in section 1 to inspect the chosen player's contribution.
- **What to check:** The selected audience mode, player, and metrics change the presentation.

### 09. Players, patterns & performance

- **What to do:** Inspect player identification, pass distance, accuracy, difficulty, and ball-speed estimates. Open **How recognition is checked** to see measured quality. Inspect rhythm and match-story panels and their sources. Recognition is evaluated on the project's fixed synthetic camera, not real broadcast footage.
- **What to check:** Metrics and recognition-quality results are visible, with the synthetic-camera limitation made clear.

### 10. Synthetic match laboratory

- **What to do:** Inspect the generator passport, seed, scenario, and consistency checks. Open **Checks · JSON** or download the reference clip with its annotations and predictions. Only synthetic football data is used.
- **What to check:** The match has reproducible generator settings and inspectable synthetic-data checks.

### 11. One match, seven languages

- **What to do:** Expand **One match · seven explanation languages** and change the explanation language. The main language selector in section 1 changes the overall interface. Supported languages: English, Czech, German, French, Italian, Spanish, and Portuguese.
- **What to check:** The selected language changes the story; the main selector also changes the interface.

### 12. Compare the same facts

- **What to do:** Expand **One episode · three languages**. Check that the same episode, numbers, fact fingerprint, and evidence links are preserved across translations. This panel needs an available key episode.
- **What to check:** Translations retain the same episode, numerical facts, and source references.

### 13. Azure & trustworthy AI

- **What to do:** Open **Inspect agent evidence**. Look for a verified Foundry result, the separate agent stages, and application to a current episode. A pending or fallback state must not be described as verified. Open **Materials and display latency** for timing evidence. Fallback preserves computed match facts when an AI run fails verification.
- **What to check:** A successful AI result shows distinct analysis, writing, and verification stages. Pending and fallback results remain explicitly labeled.

### 14. The complete match

- **What to do:** Open **Open full replay**. Test Play, Pause, speed, and the match timeline. Use **Go to final summary** to inspect the complete 90-minute recap and linked episodes. Compare viewing modes and languages against the same replay facts.
- **What to check:** The full 90-minute replay and final recap are available independently of the live match clock.

## Run locally

Use Python 3.12. The basic simulation and interface use the standard library. Generate the reproducible full-match archive before starting:

```sh
mkdir -p data
python3 -B full_match_acceptance.py --output data/full-match.sqlite3
python3 -B app.py
```

Open `http://127.0.0.1:8000/`. The default local run uses factual explanations; cloud AI requires your own Foundry configuration. Archive generation runs a complete synthetic match and its acceptance checks; it can take several minutes. Generated databases and local recordings are intentionally excluded from Git.

For the Azure/Foundry integration, install the pinned dependencies:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-azure.lock.txt
```

Build the container after generating the archive:

```sh
docker build -t event-horizon .
export EVENT_HORIZON_OPERATOR_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker run --rm -p 127.0.0.1:8000:8000 -e EVENT_HORIZON_OPERATOR_PASSWORD event-horizon
```

## Verification

```sh
python3 -B -m unittest discover -s tests
```

Some tests need the generated full-match archive, Azure SDK dependencies, or local loopback access. The public demo does not require access to a developer laptop. Credentials are never required to inspect public match evidence.

## Data and security

All players, teams, events, and video frames are synthetic. Names in the fictional roster are not author details. Runtime secrets belong in environment variables or the cloud secret store. Personal files, recorded videos, logs, `.env` files, local deployment parameters, and runtime databases are excluded. Infrastructure location parameters and match timestamps are functional configuration, not personal location history.

For public access links, the judging window, and the latest recorded deployment check, see **Try the project** above.
