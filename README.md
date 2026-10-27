# Event Horizon

Explainable AI match intelligence built on Azure. Event Horizon turns synthetic football events into live statistics, evidence-linked stories, synchronized graphics, and personalized recaps for fans, analysts, studios, and streaming teams.

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

## Architecture

Synthetic simulator and video frames → Azure Functions event relay → validated match state and statistics → Microsoft Foundry agents through Microsoft Agent Framework → verified narrative → personalized screen cards and recap.

The analysis, writing, and fact-checking agents have separate roles and share evidence references. Strict structured outputs, numeric grounding, bounded repair, and factual fallback protect the published story. Azure Container Apps hosts the application. Application Insights and Azure Monitor provide operational telemetry. Infrastructure templates are in `azure/infra/`; deployment and smoke checks are in `azure/scripts/`. Run `python azure/scripts/deploy.py --help` for required deployment arguments. Select your own resource group, region, model deployment, and credentials. Do not commit generated credentials or deployment receipts.

## Judge walkthrough — all 14 sections

Use the numbered navigation on the hosted project. Start with English and Analyst mode. Live episodes appear as the match progresses; the full replay remains available after full time. Viewer access is public. Editorial mutation controls require an operator account and are not part of anonymous viewer access.

1. **One match, understood.** Change **Viewing mode** between Fan, Analyst, and Player Focus. Select a favourite team and player. Check the visible feedback and the different depth of explanations. Reload to confirm saved preferences.
2. **Live match & statistics.** Watch the clock and players advance. Check passes, shots, possession, and pressure. Compare **Alongside the match** and **Over the image** in section 1.
3. **Reproduce the match.** Open **Replay Lab**. Inspect the repeatability explanation. Starting a new server-side comparison requires operator access. For an independent local comparison, run `python3 -B -c "from reproducibility_lab import verify; print(verify(42,30))"`. Matching seeds and scenarios must produce matching event hashes.
4. **Key moments & review.** Select a shot, goal, pressure change, or rhythm change in **How the game unfolded**. The selected breakdown stays open while live play continues. **Broadcast desk** is the editorial view; publishing and suppression require operator access.
5. **From event to insight.** Select a recent completed pass. Check the route, distance, forward/backward progress, and completed-pass counter. Open **Verify the data path**. **Pin episode** holds the selection; **Follow live play** returns to live updates.
6. **One episode, three formats.** Compare Studio, Broadcast, and Streaming cards. Their wording and length differ while the shared fact fingerprint stays the same.
7. **Five connected stages.** Inspect Event received, Context calculated, Meaning explained, Screen display, and Your perspective. In **Why this moment?**, select an episode, step through its event sequence, and inspect the source links. Arrows show earlier passes in the attack; player positions belong to the selected frame.
8. **Made for your perspective.** Open **Statistics on screen** and change the selected metrics. Compare fan and analyst views of the same period. Select Player Focus in section 1 to inspect the chosen player's contribution.
9. **Players, patterns & performance.** Inspect player identification, pass distance, accuracy, difficulty, and ball-speed estimates. Open **How recognition is checked** to see measured quality. Inspect rhythm and match-story panels and their sources. Recognition is evaluated on the project's fixed synthetic camera, not real broadcast footage.
10. **Synthetic match laboratory.** Inspect the generator passport, seed, scenario, and consistency checks. Open **Checks · JSON** or download the reference clip with its annotations and predictions. Only synthetic football data is used.
11. **One match, seven languages.** Expand **One match · seven explanation languages** and change the explanation language. The main language selector in section 1 changes the overall interface. Supported languages: English, Czech, German, French, Italian, Spanish, and Portuguese.
12. **Compare the same facts.** Expand **One episode · three languages**. Check that the same episode, numbers, fact fingerprint, and evidence links are preserved across translations. This panel needs an available key episode.
13. **Azure & trustworthy AI.** Open **Inspect agent evidence**. Look for a verified Foundry result, the separate agent stages, and application to a current episode. A pending or fallback state must not be described as verified. Open **Materials and display latency** for timing evidence. Fallback preserves computed match facts when an AI run fails verification.
14. **The complete match.** Open **Open full replay**. Test Play, Pause, speed, and the match timeline. Use **Go to final summary** to inspect the complete 90-minute recap and linked episodes. Compare viewing modes and languages against the same replay facts.

## Verification

```sh
python3 -B -m unittest discover -s tests
```

Some tests need the generated full-match archive, Azure SDK dependencies, or local loopback access. The public demo does not require access to a developer laptop. Credentials are never required to inspect public match evidence.

## Data and security

All players, teams, events, and video frames are synthetic. Names in the fictional roster are not author details. Runtime secrets belong in environment variables or the cloud secret store. Personal files, recorded videos, logs, `.env` files, local deployment parameters, and runtime databases are excluded. Infrastructure location parameters and match timestamps are functional configuration, not personal location history.

The hosted judging window ends **10 November 2026 at 23:59 Pacific Standard Time (11 November 2026 at 07:59 UTC)**. The hosting is intended to remain enabled through that time; future uptime depends on the Azure subscription, available credit, and service health. A deployment check cannot guarantee uninterrupted future uptime.
