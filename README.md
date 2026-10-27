# Event Horizon

Explainable AI match intelligence built on Azure. Event Horizon turns synthetic football events into live statistics, evidence-linked stories, synchronized graphics, and personalized recaps for fans, analysts, studios, and streaming teams.

## Try the project — no installation required

1. **Open the live website:** [Event Horizon on Azure](https://ehdemo-app.icypond-d7044f5d.swedencentral.azurecontainerapps.io/).
2. **Watch the demonstration:** [Event Horizon — 1 minute 49 seconds](https://youtu.be/NtMRFDtNP0Q).
3. For the 14-section walkthrough, open the [live dashboard](https://ehdemo-app.icypond-d7044f5d.swedencentral.azurecontainerapps.io/live), then select **English** and **Analyst** in section **01**.
4. Use the numbered navigation **01–14** to move between sections. New live moments appear as the match progresses.
5. If the live match has ended, open [the complete match replay](https://ehdemo-app.icypond-d7044f5d.swedencentral.azurecontainerapps.io/demo). The replay does not depend on a developer's laptop.

The main website opens a personal replay from **00:00**, with a short English **Kick-off** animation and automatic **1×** playback. Each browser has its own playback clock. Opening or refreshing it does not reset other viewers or the shared live simulation. Use **Live dashboard · 14 sections** to inspect the live pipeline. The direct `/demo` page keeps its manual playback controls.

### Availability for judging

**Planned hosting period: through 10 November 2026 at 23:59 Pacific Standard Time (UTC−08:00), equivalent to 11 November 2026 at 07:59 UTC.** Use the public website link above throughout this period.

Azure was checked on **27 October 2026**: the application was running, public ingress was enabled, the subscription was enabled, the minimum replica count was one, and the readiness endpoint returned HTTP 200 with `status: ok`.

## Operator access for judges

Public viewing needs no account. To test editorial actions and reproducibility controls:

1. Open [the editor sign-in page](https://ehdemo-app.icypond-d7044f5d.swedencentral.azurecontainerapps.io/editor).
2. Enter username **editor** and the application password supplied in the private testing instructions.
3. Review a completed moment, confirm its caption, select it for broadcast, or hold it.
4. Open [Replay Lab controls](https://ehdemo-app.icypond-d7044f5d.swedencentral.azurecontainerapps.io/replay-lab/control), using the same application credentials if prompted, and run a comparison.

The submission's private testing instructions must include the password. It is intentionally excluded from this public repository. This is an application-only demonstration account; judges do not need access to Azure, Microsoft, or GitHub accounts. Operator changes affect the shared demo. A live-match restart resets the current run for all viewers; [the complete replay](https://ehdemo-app.icypond-d7044f5d.swedencentral.azurecontainerapps.io/demo) remains independent.

## Architecture

Synthetic simulator and video frames → Azure Functions event relay → validated match state and statistics → Microsoft Foundry agents through Microsoft Agent Framework → verified narrative → personalized screen cards and recap.

The analysis, writing, and fact-checking agents have separate roles and share evidence references. Strict structured outputs, numeric grounding, bounded repair, and factual fallback protect the published story. Azure Container Apps hosts the application. Application Insights and Azure Monitor provide operational telemetry. Infrastructure templates are in `azure/infra/`; deployment and smoke checks are in `azure/scripts/`. Run `python azure/scripts/deploy.py --help` for required deployment arguments. Select your own resource group, region, model deployment, and credentials. Do not commit generated credentials or deployment receipts.

## Judge walkthrough — all 14 sections

Use the numbered navigation on the [live dashboard](https://ehdemo-app.icypond-d7044f5d.swedencentral.azurecontainerapps.io/live). Start with English and Analyst mode. Live episodes appear as the match progresses; the full replay remains available after full time. Viewer access is public. Editorial mutation controls require an operator account and are not part of anonymous viewer access.

Open the website and follow sections 01–14. Start with English and Analyst mode. Operator access is required for server-side tests and editorial changes.

1. **One match, understood:** Choose Fan, Analyst, or Player Focus, then select your favourite team and player.  
2. **Live match & statistics:** Watch the match and live stats; compare the alongside and overlay display modes.  
3. **Reproduce the match:** Open Replay Lab to explore repeatability; operator access is required to run a new comparison.  
4. **Key moments & review:** Select a key moment to inspect it; use Broadcast desk with operator access to review and publish cards.  
5. **From event to insight:** Select a completed pass and inspect its route, distance, progress, and source data.  
6. **One episode, three formats:** Compare Studio, Broadcast, and Streaming cards based on the same facts.  
7. **Five connected stages:** Follow the five stages, then open “Why this moment?” to explore the event sequence and evidence.  
8. **Made for your perspective:** Change the visible statistics and compare audience modes and player-focused stories.  
9. **Players, patterns & performance:** Explore player tracking, pass quality, ball speed, match patterns, and recognition results.  
10. **Synthetic match laboratory:** Inspect the generator settings, data checks, and reference video.  
11. **One match, seven languages:** Switch between seven languages to compare the interface and match stories.  
12. **Compare the same facts:** Open the three-language comparison and check that numbers and source links remain unchanged.  
13. **Azure & trustworthy AI:** Inspect the agent evidence, verification status, and event-to-display latency.  
14. **The complete match:** Open the full replay, try playback controls, and explore the final recap and linked moments.  

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
