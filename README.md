# KEDA GKE Event-Driven Autoscaling

> Kubernetes workloads that scale from **zero to N and back to zero**, driven by event backlog — not CPU/memory alone.

Most Kubernetes autoscaling (HPA) reacts to CPU and memory. That's a poor proxy for workloads like queue consumers, where a pod can sit at low CPU while a backlog of thousands of unprocessed messages builds up. This project uses [KEDA](https://keda.sh) to scale a Kubernetes Deployment off external event signals, including scaling to **zero replicas** when there's no work — something native HPA cannot do on its own.

---

## Current Status

This project is built and verified against a **local Kubernetes cluster** (`kind`) with a **GCP Pub/Sub emulator**, rather than live GKE and real Pub/Sub. That's a deliberate, temporary choice, not an oversight — see [Why Local, Not Live GKE](#why-local-not-live-gke) below.

| Component | Status |
|---|---|
| Publisher / Consumer app (Python) | ✅ Built, tested, working |
| Docker image (multi-stage, non-root) | ✅ Built and verified |
| Local Kubernetes cluster (`kind`) + KEDA | ✅ Installed and verified |
| Autoscaling proven end-to-end | ✅ Demonstrated (0→5→1 replica cycle recorded — see demo below) |
| GCP Pub/Sub (real, live) | ⏸️ Written and ready; not yet run against live GCP |
| Google Kubernetes Engine (real, live) | ⏸️ Manifests ready; not yet deployed |
| GitHub Actions CI (test + build) | ✅ Live and passing on every push |

---

## Demo

![Scaling demo](docs/demo.gif)

*(0 → 5 replicas as load increases, back to 1 as it clears — recorded against the local cluster below.)*

---

## Architecture (Local Setup)

```
┌──────────────────────────────────────────────────────────────────┐
│  publisher.py                                                     │
│  Simulates event traffic: steady / burst / ramp load patterns     │
└───────────────────────────┬──────────────────────────────────────┘
                             │ publishes
┌────────────────────────────▼──────────────────────────────────────┐
│  GCP Pub/Sub Emulator (in-cluster pod)                             │
│  Topic: keda-demo-topic → Subscription: keda-demo-topic-subscription│
└────────────────────────────┬──────────────────────────────────────┘
                             │ polled
┌────────────────────────────▼──────────────────────────────────────┐
│  KEDA (installed via Helm, in-cluster)                              │
│  ScaledObject watches backlog / CPU metric                         │
│  minReplicas: 0-1 → maxReplicas: 5-10                              │
└────────────────────────────┬──────────────────────────────────────┘
                             │ scales
┌────────────────────────────▼──────────────────────────────────────┐
│  kind (Kubernetes-in-Docker)                                       │
│  Deployment: keda-demo-consumer                                    │
│  consumer.py — pulls messages, simulates variable work, acks       │
└──────────────────────────────────────────────────────────────────┘
```

The same manifests (`k8s/deployment.yaml`, `k8s/keda-scaledobject.yaml`) are written for real GKE + Workload Identity + live Pub/Sub, and require no code changes to deploy there — see [`docs/DEPLOY.md`](docs/DEPLOY.md).

---

## Why Local, Not Live GKE

Real GKE and Pub/Sub require a linked GCP billing account. I attempted to activate GCP's free trial, but the required one-time verification charge was declined by my bank and the trial account never activated — a real, unresolved friction point common for cards issued outside a handful of countries GCP fully supports for this flow.

Rather than block the whole project on that, I rebuilt the entire stack locally:
- **`kind`** (Kubernetes-in-Docker) in place of GKE
- **GCP's own official Pub/Sub emulator** in place of live Pub/Sub — same client library, same API surface, running as a pod in the cluster
- **KEDA**, installed and configured identically to how it would run on GKE

This let me build, test, and prove the entire autoscaling mechanism — including a real scale-up/scale-down cycle driven by Kubernetes' HPA and KEDA, verified live — at zero cost. The moment real GCP billing is available, `docs/DEPLOY.md` walks through deploying the exact same manifests to live GKE with no code changes required.

**One known gap:** KEDA's native `gcp-pubsub` scaler type requires real Google Application Credentials and cannot be pointed at the emulator, even with the emulator host configured — this is a hard requirement in KEDA's scaler implementation, not a configuration issue on my end. So the local demo above uses a **CPU-based ScaledObject** to prove the scaling mechanism (KEDA watching a metric, driving Kubernetes' HPA, scaling the Deployment up and down), while the actual Pub/Sub-triggered `ScaledObject` YAML is written, reviewed against KEDA's current documentation, and ready for live GCP.

I also discovered, while researching this, that KEDA has deprecated the `gcp-pubsub` scaler type in favor of a Prometheus-based approach (GCP is deprecating the underlying query language the old scaler depends on). `k8s/keda-scaledobject.yaml` already reflects the updated, current approach.

---

## Quick Start (Local Dev, No GCP Needed)

### Prerequisites

- Python ≥ 3.10 (project pinned to 3.12 — see `.python-version`)
- Docker
- `kind`, `kubectl`, `helm` (for full local cluster testing)

### 1. Clone and install

```bash
git clone https://github.com/madushansivam/keda-gke-event-driven-autoscaling.git
cd keda-gke-event-driven-autoscaling
python3 -m venv venv
source venv/bin/activate
pip install -r app/requirements-dev.txt
```

### 2. Run unit tests (no GCP credentials required)

```bash
python -m pytest app/tests/test_consumer.py -v
```

### 3. Run against the Pub/Sub emulator

```bash
docker run -d -p 8085:8085 gcr.io/google.com/cloudsdktool/cloud-sdk:emulators \
  gcloud beta emulators pubsub start --host-port=0.0.0.0:8085
export PUBSUB_EMULATOR_HOST=localhost:8085
python -m pytest app/tests/test_publisher_integration.py -v
```

### 4. Full local Kubernetes + KEDA demo

```bash
kind create cluster --name keda-demo
helm repo add kedacore https://kedacore.github.io/charts
helm install keda kedacore/keda --namespace keda --create-namespace
kind load docker-image keda-demo-consumer:local --name keda-demo
kubectl apply -f k8s/local/pubsub-emulator.yaml
kubectl apply -f k8s/local/consumer-deployment.yaml
kubectl apply -f k8s/local/keda-scaledobject-cpu-demo.yaml
```

Then watch it scale — full walkthrough in [`docs/DEPLOY.md`](docs/DEPLOY.md).

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.12 |
| Messaging | GCP Pub/Sub (emulator locally; live GCP-ready) |
| Autoscaling | KEDA 2.20 (Helm) |
| Local orchestration | `kind` (Kubernetes-in-Docker) |
| Target orchestration | Google Kubernetes Engine (manifests ready) |
| Containerization | Docker (multi-stage, non-root) |
| Testing | pytest, pytest-cov, Pub/Sub emulator |
| CI | GitHub Actions (test + build, live and passing) |

---

## Project Structure

```
keda-gke-event-driven-autoscaling/
├── app/
│   ├── publisher.py          # Load generator: steady/burst/ramp patterns
│   ├── consumer.py           # Pub/Sub consumer with simulated work time
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── tests/
│       ├── test_consumer.py
│       └── test_publisher_integration.py
├── k8s/
│   ├── service-account.yaml       # Workload Identity-bound KSA (real GKE)
│   ├── deployment.yaml            # Consumer Deployment with resource limits (real GKE)
│   ├── keda-scaledobject.yaml     # Prometheus-based Pub/Sub scaler (real GKE)
│   └── local/
│       ├── pubsub-emulator.yaml
│       ├── consumer-deployment.yaml
│       └── keda-scaledobject-cpu-demo.yaml
├── .github/workflows/
│   └── ci.yml                 # test → build, live and passing
├── Dockerfile                 # Multi-stage, non-root
├── .python-version             # Pinned to 3.12
└── docs/
    ├── DEPLOY.md               # Full GCP + GKE + KEDA setup (for when billing is available)
    └── demo.gif
```

---

## What I Learned

- Why HPA's resource-based model breaks down for queue-consumer workloads, and how KEDA closes that gap using external metrics adapters
- How to build and validate an entire event-driven autoscaling pipeline locally, at zero cost, when cloud billing isn't an option — and to treat that as a legitimate engineering path, not a compromise
- That `kind` clusters need `metrics-server` installed manually (unlike GKE, which ships it by default) before HPA/KEDA can read CPU metrics
- KEDA's `gcp-pubsub` scaler unconditionally requires real Google Application Credentials, and cannot run against the Pub/Sub emulator even with the emulator host configured
- That KEDA has deprecated `gcp-pubsub` in favor of a Prometheus-based scaler, and how to migrate a ScaledObject to the current recommended approach
- Diagnosing real infrastructure failure modes: a stray `GITHUB_TOKEN` environment variable silently overriding git auth, a `protobuf`/Python 3.14 incompatibility, and Pub/Sub emulator state loss on pod restart (in-memory only, no persistence)

---

## License

MIT
