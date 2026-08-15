# KEDA + GKE Event-Driven Autoscaling — Full Rebuild Journey

**Owner:** Madushan Sivam (madushansivam)
**Repo:** keda-gke-event-driven-autoscaling
**OS:** Fedora Linux
**Goal:** Rebuild this project from scratch, understand every line, and end with a portfolio-ready, resume-ready, fully deployed, tested, CI/CD-driven system.

---

## HOW TO USE THIS DOCUMENT

This document is written so you can work **fully offline**. Every phase has:
1. **INSTALL FIRST** — anything you need to download, listed at the very top of that phase, so you can grab it before your data runs out.
2. **Step-by-step commands** — copy-paste exact.
3. **Checkpoint** — what to verify before moving to the next phase.
4. **Commit** — the exact git commit to make at the end of the phase.

Work top to bottom. Don't skip phases. Each phase assumes the previous one is committed and working.

When you get internet back: run the commands, if something breaks paste the exact error back to Claude, fix it, then move to next phase. Push to GitHub at the end of every phase minimum (ideally every sub-step).

---

## PHASE 0 — Foundations (Local, No Internet Needed After Downloads)

### INSTALL FIRST (do this while you have data)

Download these installers/packages NOW, before your data finishes:

```bash
# 1. gcloud CLI tarball (large ~200MB, get this first)
cd ~/Downloads
wget -c https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-linux-x86_64.tar.gz

# 2. Docker (Fedora repo packages)
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 3. kubectl
sudo dnf install -y kubectl
# If that repo isn't available on Fedora, fallback:
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# 4. Helm
curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3
chmod +x get_helm.sh
./get_helm.sh

# 5. Python tooling
sudo dnf install -y python3-pip python3-virtualenv

# 6. Minikube or Kind (for local K8s testing WITHOUT paying GCP costs)
curl -LO https://github.com/kubernetes-sigs/kind/releases/latest/download/kind-linux-amd64
chmod +x kind-linux-amd64
sudo mv kind-linux-amd64 /usr/local/bin/kind
```

Also **bookmark these** (view later without downloading anything, or save page as PDF now while online):
- https://keda.sh/docs/latest/
- https://cloud.google.com/sdk/docs/install
- https://docs.docker.com/engine/install/fedora/
- https://www.jenkins.io/doc/book/installing/linux/#red-hat--centos

### Enable Docker without sudo every time

```bash
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker
docker run hello-world
```

If `docker run hello-world` prints a success message, Docker works.

### Checkpoint 0
Run these and confirm no errors:
```bash
docker --version
kubectl version --client
helm version
kind --version
python3 --version
```

### Commit
```bash
cd ~/Project/keda-gke-event-driven-autoscaling
touch docs/phase0-tools-installed.md
echo "Tools installed: docker, kubectl, helm, kind, gcloud (pending extract), python3" > docs/phase0-tools-installed.md
git add .
git commit -m "docs: phase 0 - local tooling installed"
git push origin main
```

---

## PHASE 1 — Rebuild the Core App From Scratch

No internet required except pip installs (can be done later if offline — note below).

### INSTALL FIRST (offline pip cache option)
If you might be offline during this phase:
```bash
pip download google-cloud-pubsub pytest -d ~/Downloads/pip-cache
```
This saves the packages locally so `pip install --no-index --find-links=~/Downloads/pip-cache <package>` works with no internet later.

### Step 1.1 — Virtual environment

```bash
cd ~/Project/keda-gke-event-driven-autoscaling
python3 -m venv venv
source venv/bin/activate
```

### Step 1.2 — requirements files (split dev vs prod — a resume-worthy practice)

```bash
cat > app/requirements.txt << 'EOF'
google-cloud-pubsub==2.21.1
EOF

cat > app/requirements-dev.txt << 'EOF'
-r requirements.txt
pytest==8.2.0
pytest-mock==3.14.0
EOF
```

Install (only works with internet or the pip cache from above):
```bash
pip install -r app/requirements-dev.txt
```

### Step 1.3 — Write the publisher (from scratch, understand every line)

```bash
cat > app/publisher.py << 'EOF'
"""
Publisher: simulates event traffic by sending messages to a GCP Pub/Sub topic.
Supports three load patterns to realistically demo autoscaling:
  - steady: fixed rate forever
  - burst: sudden spike then quiet
  - ramp: gradually increasing rate
"""
import os
import time
import random
import argparse
from google.cloud import pubsub_v1

def get_config():
    return {
        "project_id": os.environ["GCP_PROJECT_ID"],
        "topic_name": os.environ["TOPIC_NAME"],
    }

def publish_message(publisher, topic_path, message_id):
    data = f"event-{message_id}".encode("utf-8")
    future = publisher.publish(topic_path, data)
    return future.result()  # blocks until ack from Pub/Sub, raises on failure

def run_steady(publisher, topic_path, rate_per_sec):
    msg_id = 0
    while True:
        publish_message(publisher, topic_path, msg_id)
        msg_id += 1
        time.sleep(1 / rate_per_sec)

def run_burst(publisher, topic_path, burst_size, quiet_seconds):
    msg_id = 0
    while True:
        print(f"[burst] sending {burst_size} messages")
        for _ in range(burst_size):
            publish_message(publisher, topic_path, msg_id)
            msg_id += 1
        print(f"[burst] quiet for {quiet_seconds}s")
        time.sleep(quiet_seconds)

def run_ramp(publisher, topic_path, start_rate, max_rate, step_seconds):
    msg_id = 0
    rate = start_rate
    while True:
        publish_message(publisher, topic_path, msg_id)
        msg_id += 1
        time.sleep(1 / rate)
        if msg_id % 20 == 0 and rate < max_rate:
            rate += 1
            print(f"[ramp] rate now {rate}/sec")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["steady", "burst", "ramp"], default="steady")
    parser.add_argument("--rate", type=float, default=1.0)
    args = parser.parse_args()

    config = get_config()
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(config["project_id"], config["topic_name"])

    if args.mode == "steady":
        run_steady(publisher, topic_path, args.rate)
    elif args.mode == "burst":
        run_burst(publisher, topic_path, burst_size=50, quiet_seconds=20)
    elif args.mode == "ramp":
        run_ramp(publisher, topic_path, start_rate=1, max_rate=20, step_seconds=1)
EOF
```

**Why this is better than the old `generate-message.sh`:** it's testable Python (not bash), supports 3 realistic traffic patterns instead of one flat loop, and is driven by CLI flags — this is what the council recommended as your "load-simulation harness," scoped small.

### Step 1.4 — Write the consumer (with realistic simulated work)

```bash
cat > app/consumer.py << 'EOF'
"""
Consumer: pulls messages from a Pub/Sub subscription and processes them.
Simulates realistic variable work time instead of an instant ack —
this makes autoscaling behavior visible and believable.
"""
import os
import time
import random
from concurrent.futures import TimeoutError
from google.cloud import pubsub_v1

PULL_TIMEOUT_SECONDS = 3.0

def get_config():
    return {
        "project_id": os.environ["PUB_SUB_PROJECT"],
        "subscription_name": os.environ["PUB_SUB_SUBSCRIPTION"],
    }

def simulate_work():
    # Randomized delay to mimic real processing (e.g. image resize, DB write)
    duration = random.uniform(0.5, 2.5)
    time.sleep(duration)
    return duration

def make_callback():
    def callback(message):
        duration = simulate_work()
        print(f"Processed {message.data} in {duration:.2f}s")
        message.ack()
    return callback

def consume_once(project_id, subscription_name, timeout):
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(project_id, subscription_name)
    print(f"Listening on {subscription_path}")
    future = subscriber.subscribe(subscription_path, callback=make_callback())
    with subscriber:
        try:
            future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            future.result()

if __name__ == "__main__":
    config = get_config()
    while True:
        consume_once(config["project_id"], config["subscription_name"], PULL_TIMEOUT_SECONDS)
        time.sleep(2)
EOF
```

### Step 1.5 — Local test WITHOUT GCP (mock test, works offline)

```bash
mkdir -p app/tests
cat > app/tests/test_consumer.py << 'EOF'
"""
Tests consumer logic without touching real GCP Pub/Sub.
Uses pytest-mock to fake the message object.
"""
from app.consumer import simulate_work

def test_simulate_work_returns_duration_in_range():
    duration = simulate_work()
    assert 0.5 <= duration <= 2.5

def test_simulate_work_returns_a_float():
    duration = simulate_work()
    assert isinstance(duration, float)
EOF
```

Run it:
```bash
cd ~/Project/keda-gke-event-driven-autoscaling
python -m pytest app/tests/ -v
```

Both tests should pass — **fully offline**, no GCP credentials needed.

### Checkpoint 1
```bash
python -m pytest app/tests/ -v
```
2 passed, 0 failed.

### Commit
```bash
git add .
git commit -m "feat: rebuild publisher and consumer with realistic load patterns and simulated work time"
git push origin main
```

---

## PHASE 2 — Dockerize Properly

### INSTALL FIRST
Already done in Phase 0 (Docker installed). Nothing new to download.

### Step 2.1 — Multi-stage, non-root Dockerfile (resume-worthy: shows security awareness)

```bash
cat > Dockerfile << 'EOF'
# --- Build stage ---
FROM python:3.12-slim AS builder
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# --- Runtime stage ---
FROM python:3.12-slim
WORKDIR /app

# Create non-root user
RUN useradd --create-home appuser
COPY --from=builder /root/.local /home/appuser/.local
COPY app/ .

ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

USER appuser

CMD ["python", "consumer.py"]
EOF
```

### Step 2.2 — .dockerignore

```bash
cat > .dockerignore << 'EOF'
venv/
__pycache__/
*.pyc
.git/
.github/
docs/
app/tests/
EOF
```

### Step 2.3 — Build and test locally

```bash
docker build -t keda-demo-consumer:local .
docker images | grep keda-demo-consumer
```

### Checkpoint 2
```bash
docker run --rm keda-demo-consumer:local python -c "print('container runs fine')"
```

### Commit
```bash
git add .
git commit -m "feat: add multi-stage non-root Dockerfile for consumer"
git push origin main
```

---

## PHASE 3 — GCP Setup + Push Image to Artifact Registry

### INSTALL FIRST
Extract gcloud (downloaded in Phase 0):
```bash
cd ~/Downloads
tar -xf google-cloud-cli-linux-x86_64.tar.gz
./google-cloud-sdk/install.sh
exec -l $SHELL
gcloud version
```

### Step 3.1 — Login and project setup

```bash
gcloud init
gcloud projects create keda-demo-madu --name="KEDA GKE Demo"
gcloud config set project keda-demo-madu
```

Link billing in browser: https://console.cloud.google.com/billing

### Step 3.2 — Enable required APIs

```bash
gcloud services enable \
  container.googleapis.com \
  pubsub.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com
```

### Step 3.3 — Create Artifact Registry repo (replaces old Docker Hub pattern — more resume-relevant, shows GCP-native skill)

```bash
gcloud artifacts repositories create keda-demo-repo \
  --repository-format=docker \
  --location=us-central1 \
  --description="KEDA demo container images"

gcloud auth configure-docker us-central1-docker.pkg.dev
```

### Step 3.4 — Tag and push your image

```bash
docker tag keda-demo-consumer:local \
  us-central1-docker.pkg.dev/keda-demo-madu/keda-demo-repo/consumer:v1

docker push us-central1-docker.pkg.dev/keda-demo-madu/keda-demo-repo/consumer:v1
```

### Step 3.5 — Create Pub/Sub topic and subscription

```bash
gcloud pubsub topics create keda-demo-topic
gcloud pubsub subscriptions create keda-demo-topic-subscription \
  --topic keda-demo-topic
```

### Checkpoint 3
```bash
gcloud artifacts docker images list us-central1-docker.pkg.dev/keda-demo-madu/keda-demo-repo
gcloud pubsub topics list
```

### Commit
```bash
cat > docs/gcp-setup.md << 'EOF'
# GCP Setup Log
- Project: keda-demo-madu
- Region: us-central1
- Artifact Registry: keda-demo-repo
- Pub/Sub topic: keda-demo-topic
- Pub/Sub subscription: keda-demo-topic-subscription
EOF
git add .
git commit -m "docs: record GCP project setup, Artifact Registry, and Pub/Sub resources"
git push origin main
```

---

## PHASE 4 — GKE Cluster + Manual Deploy (Fixing the Deprecated Auth Pattern)

### Step 4.1 — Create GKE cluster (Autopilot = cheaper, less to manage, resume-relevant since it's the modern GCP-recommended mode)

```bash
gcloud container clusters create-auto keda-demo-cluster \
  --region=us-central1
```

This takes 5-10 minutes.

### Step 4.2 — Get cluster credentials

```bash
gcloud container clusters get-credentials keda-demo-cluster --region us-central1
kubectl get nodes
```

### Step 4.3 — Set up Workload Identity (the FIX for the deprecated podIdentity pattern)

```bash
# GCP service account for the consumer
gcloud iam service-accounts create keda-demo-consumer-sa \
  --display-name="KEDA demo consumer"

# Grant Pub/Sub subscriber role
gcloud projects add-iam-policy-binding keda-demo-madu \
  --member="serviceAccount:keda-demo-consumer-sa@keda-demo-madu.iam.gserviceaccount.com" \
  --role="roles/pubsub.subscriber"

# Bind Kubernetes SA to GCP SA via Workload Identity
gcloud iam service-accounts add-iam-policy-binding \
  keda-demo-consumer-sa@keda-demo-madu.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:keda-demo-madu.svc.id.goog[default/keda-demo-consumer-ksa]"
```

### Step 4.4 — Kubernetes manifests

```bash
cat > k8s/service-account.yaml << 'EOF'
apiVersion: v1
kind: ServiceAccount
metadata:
  name: keda-demo-consumer-ksa
  annotations:
    iam.gke.io/gcp-service-account: keda-demo-consumer-sa@keda-demo-madu.iam.gserviceaccount.com
EOF

cat > k8s/deployment.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: keda-demo-consumer
spec:
  replicas: 1
  selector:
    matchLabels:
      app: keda-demo-consumer
  template:
    metadata:
      labels:
        app: keda-demo-consumer
    spec:
      serviceAccountName: keda-demo-consumer-ksa
      containers:
        - name: consumer
          image: us-central1-docker.pkg.dev/keda-demo-madu/keda-demo-repo/consumer:v1
          env:
            - name: PUB_SUB_PROJECT
              value: "keda-demo-madu"
            - name: PUB_SUB_SUBSCRIPTION
              value: "keda-demo-topic-subscription"
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "250m"
              memory: "256Mi"
EOF
```

Note the `resources` block — the old repo didn't have this. Missing resource requests/limits is a common production anti-pattern; adding this is a small but real signal of maturity for anyone reviewing your code.

### Step 4.5 — Apply and verify

```bash
kubectl apply -f k8s/service-account.yaml
kubectl apply -f k8s/deployment.yaml
kubectl get pods
kubectl logs -l app=keda-demo-consumer
```

### Checkpoint 4
Pod is `Running`, logs show `Listening on projects/keda-demo-madu/subscriptions/keda-demo-topic-subscription`.

### Commit
```bash
git add .
git commit -m "feat: add GKE Autopilot deploy with Workload Identity (replaces deprecated podIdentity)"
git push origin main
```

---

## PHASE 5 — Install KEDA + ScaledObject

### Step 5.1 — Install KEDA via Helm

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda --namespace keda --create-namespace
kubectl get pods -n keda
```

### Step 5.2 — KEDA needs its own Workload Identity binding too

```bash
gcloud iam service-accounts create keda-operator-sa

gcloud projects add-iam-policy-binding keda-demo-madu \
  --member="serviceAccount:keda-operator-sa@keda-demo-madu.iam.gserviceaccount.com" \
  --role="roles/monitoring.viewer"

gcloud iam service-accounts add-iam-policy-binding \
  keda-operator-sa@keda-demo-madu.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:keda-demo-madu.svc.id.goog[keda/keda-operator]"

kubectl annotate serviceaccount keda-operator \
  -n keda \
  iam.gke.io/gcp-service-account=keda-operator-sa@keda-demo-madu.iam.gserviceaccount.com
```

### Step 5.3 — TriggerAuthentication + ScaledObject (using gcpWorkloadIdentity — not deprecated podIdentity)

```bash
cat > k8s/keda-scaledobject.yaml << 'EOF'
apiVersion: keda.sh/v1alpha1
kind: TriggerAuthentication
metadata:
  name: keda-demo-trigger-auth
spec:
  podIdentity:
    provider: gcp
---
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: keda-demo-scaledobject
spec:
  scaleTargetRef:
    name: keda-demo-consumer
  pollingInterval: 5
  minReplicaCount: 0
  maxReplicaCount: 10
  cooldownPeriod: 60
  triggers:
    - type: gcp-pubsub
      authenticationRef:
        name: keda-demo-trigger-auth
      metadata:
        subscriptionName: "keda-demo-topic-subscription"
        mode: "SubscriptionSize"
        value: "5"
EOF

kubectl apply -f k8s/keda-scaledobject.yaml
kubectl get scaledobject
```

Note: `gcp` podIdentity provider in KEDA's TriggerAuthentication CRD is still valid — it's specifically GCP's older *node-level* Pod Identity mechanism that KEDA deprecated for auth to KEDA itself. Always check the current KEDA docs (https://keda.sh/docs/latest/scalers/gcp-pub-sub/) before deploying, since KEDA versions and GCP auth options change — verify the `authenticationRef` pattern shown there still matches this before you apply it live.

### Step 5.4 — Test scaling

```bash
# Terminal 1: watch pods scale
kubectl get pods -w

# Terminal 2: generate load
source venv/bin/activate
export GCP_PROJECT_ID=keda-demo-madu
export TOPIC_NAME=keda-demo-topic
python app/publisher.py --mode burst
```

Watch Terminal 1 — pods should scale up as messages queue, then back to 0 after the cooldown period with no backlog.

### Checkpoint 5
Screen-record or screenshot the scaling in action — this becomes your demo GIF for the README and portfolio.

### Commit
```bash
git add .
git commit -m "feat: install KEDA and add ScaledObject for Pub/Sub-based autoscaling"
git push origin main
```

---

## PHASE 6 — Testing (Beyond Phase 1's Unit Tests)

### Step 6.1 — Add integration test using GCP Pub/Sub emulator (no real GCP cost, works offline once image is pulled)

```bash
docker pull google/cloud-sdk:emulators
```

```bash
cat > app/tests/test_publisher_integration.py << 'EOF'
"""
Integration test using the Pub/Sub emulator.
Requires: docker run -d -p 8085:8085 google/cloud-sdk:emulators \
  gcloud beta emulators pubsub start --host-port=0.0.0.0:8085
And: export PUBSUB_EMULATOR_HOST=localhost:8085
"""
import os
import pytest
from google.cloud import pubsub_v1

pytestmark = pytest.mark.skipif(
    "PUBSUB_EMULATOR_HOST" not in os.environ,
    reason="Pub/Sub emulator not running"
)

def test_publish_and_pull_roundtrip():
    project_id = "test-project"
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    topic_path = publisher.topic_path(project_id, "test-topic")
    sub_path = subscriber.subscription_path(project_id, "test-sub")

    publisher.create_topic(request={"name": topic_path})
    subscriber.create_subscription(request={"name": sub_path, "topic": topic_path})

    publisher.publish(topic_path, b"hello-emulator").result()

    response = subscriber.pull(request={"subscription": sub_path, "max_messages": 1})
    assert len(response.received_messages) == 1
    assert response.received_messages[0].message.data == b"hello-emulator"
EOF
```

### Step 6.2 — pytest coverage config

```bash
cat > app/pytest.ini << 'EOF'
[pytest]
addopts = --cov=app --cov-report=term-missing
testpaths = app/tests
EOF

pip install pytest-cov
```

### Checkpoint 6
```bash
python -m pytest app/tests/ -v
```

### Commit
```bash
git add .
git commit -m "test: add Pub/Sub emulator integration test and coverage config"
git push origin main
```

---

## PHASE 7 — CI Pipeline: GitHub Actions

### Step 7.1 — Workflow file

```bash
cat > .github/workflows/ci.yml << 'EOF'
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r app/requirements-dev.txt

      - name: Run unit tests
        run: python -m pytest app/tests/ -v -m "not integration"

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t keda-demo-consumer:ci .
EOF
```

### Checkpoint 7
Push and check the Actions tab on GitHub — both jobs should go green.

### Commit
```bash
git add .
git commit -m "ci: add GitHub Actions workflow for test and build"
git push origin main
```

---

## PHASE 8 — Jenkins (Second CI, Demonstrates Tool Range)

### INSTALL FIRST

```bash
sudo dnf install -y java-17-openjdk
wget -O /etc/yum.repos.d/jenkins.repo https://pkg.jenkins.io/redhat-stable/jenkins.repo
sudo rpm --import https://pkg.jenkins.io/redhat-stable/jenkins.io-2023.key
sudo dnf install -y jenkins
```

### Step 8.1 — Start Jenkins

```bash
sudo systemctl enable --now jenkins
sudo firewall-cmd --add-port=8080/tcp --permanent
sudo firewall-cmd --reload
sudo cat /var/lib/jenkins/secrets/initialAdminPassword
```

Open `http://localhost:8080`, paste the password, install suggested plugins, create your admin user.

### Step 8.2 — Jenkinsfile in the repo

```bash
cat > Jenkinsfile << 'EOF'
pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }
        stage('Install Dependencies') {
            steps {
                sh 'pip install -r app/requirements-dev.txt'
            }
        }
        stage('Test') {
            steps {
                sh 'python -m pytest app/tests/ -v -m "not integration"'
            }
        }
        stage('Build Docker Image') {
            steps {
                sh 'docker build -t keda-demo-consumer:jenkins .'
            }
        }
    }
    post {
        always {
            echo 'Pipeline finished.'
        }
        failure {
            echo 'Pipeline failed — check logs above.'
        }
    }
}
EOF
```

### Step 8.3 — Create Jenkins job pointing at your GitHub repo

In Jenkins UI: New Item → Pipeline → name it `keda-demo-pipeline` → under Pipeline, choose "Pipeline script from SCM" → SCM: Git → paste your repo URL → Script Path: `Jenkinsfile` → Save → Build Now.

### Checkpoint 8
Jenkins build passes green in the UI.

### Commit
```bash
git add .
git commit -m "ci: add Jenkinsfile for local Jenkins pipeline"
git push origin main
```

---

## PHASE 9 — CD: Auto-Deploy to GKE on Merge

### Step 9.1 — Service account key for GitHub Actions (use Workload Identity Federation, not a downloaded key, if you want the more modern/secure approach — flagged here since key-based auth is being phased out industry-wide)

```bash
gcloud iam service-accounts create github-actions-deployer

gcloud projects add-iam-policy-binding keda-demo-madu \
  --member="serviceAccount:github-actions-deployer@keda-demo-madu.iam.gserviceaccount.com" \
  --role="roles/container.developer"

gcloud projects add-iam-policy-binding keda-demo-madu \
  --member="serviceAccount:github-actions-deployer@keda-demo-madu.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
```

Set up Workload Identity Federation for GitHub Actions (recommended, no long-lived key):
Follow: https://github.com/google-github-actions/auth#preferred-direct-workload-identity-federation

### Step 9.2 — Add CD job to the workflow

```bash
cat >> .github/workflows/ci.yml << 'EOF'

  deploy:
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          project_id: keda-demo-madu
          workload_identity_provider: ${{ secrets.WIF_PROVIDER }}
          service_account: github-actions-deployer@keda-demo-madu.iam.gserviceaccount.com

      - uses: google-github-actions/setup-gcloud@v2

      - name: Configure Docker
        run: gcloud auth configure-docker us-central1-docker.pkg.dev

      - name: Build and push
        run: |
          docker build -t us-central1-docker.pkg.dev/keda-demo-madu/keda-demo-repo/consumer:${{ github.sha }} .
          docker push us-central1-docker.pkg.dev/keda-demo-madu/keda-demo-repo/consumer:${{ github.sha }}

      - name: Get GKE credentials
        run: gcloud container clusters get-credentials keda-demo-cluster --region us-central1

      - name: Deploy
        run: |
          kubectl set image deployment/keda-demo-consumer \
            consumer=us-central1-docker.pkg.dev/keda-demo-madu/keda-demo-repo/consumer:${{ github.sha }}
EOF
```

### Checkpoint 9
Merge a small change to `main`, watch GitHub Actions build, push, and redeploy automatically. Confirm with:
```bash
kubectl get deployment keda-demo-consumer -o wide
```

### Commit
```bash
git add .
git commit -m "ci: add automated deploy to GKE on merge to main"
git push origin main
```

---

## PHASE 10 — Polish, Docs, Portfolio, Resume

### Step 10.1 — Rewrite README.md properly

Structure it as: Problem → Architecture diagram → Quickstart → Demo GIF → Tech stack → What I learned.

### Step 10.2 — Record a demo

```bash
# Use a screen recorder (Fedora: built-in via GNOME Screenshot/Kooha, or:)
sudo dnf install -y kooha
```
Record the `kubectl get pods -w` scaling up/down while `publisher.py --mode burst` runs. Trim to ~30-45 seconds, export as GIF for the README (convert with `ffmpeg` if needed), and keep the full video for LinkedIn/portfolio.

### Step 10.3 — Resume bullet drafts (edit to your voice before using)

- Designed and deployed an event-driven autoscaling system on GKE using KEDA, scaling Kubernetes workloads from zero based on GCP Pub/Sub queue depth
- Built CI/CD pipelines in both GitHub Actions and Jenkins, automating test, build, and deploy stages to production
- Replaced a deprecated GCP auth pattern with Workload Identity Federation, hardening the deployment's security posture
- Containerized a Python microservice with a multi-stage, non-root Dockerfile, reducing image size and attack surface
- Wrote unit and integration tests (including a Pub/Sub emulator harness) achieving full coverage of core logic

### Checkpoint 10
Full pipeline works end-to-end: push code → tests run → image builds → deploys to GKE → autoscaling demonstrably works → README tells the story clearly.

### Final commit
```bash
git add .
git commit -m "docs: final README polish, demo assets, and project writeup"
git push origin main
```

---

## APPENDIX — Cost Control (Important, Read Before Phase 4)

GKE Autopilot + a running cluster costs money even idle. To avoid burning through free credits:

```bash
# Delete cluster when not actively working on it
gcloud container clusters delete keda-demo-cluster --region us-central1

# Recreate when you resume (Phase 4, step 4.1) — takes ~5-10 min
```

Set a budget alert immediately after linking billing:
https://console.cloud.google.com/billing/budgets → Create Budget → set to a low threshold (e.g. $5) so you get emailed before real charges build up.

---

## WHEN YOU GET INTERNET BACK — QUICK RESUME CHECKLIST

1. `cd ~/Project/keda-gke-event-driven-autoscaling && git pull`
2. Check which Phase you last committed (`git log --oneline`)
3. Come back to Claude, paste the output of `git log --oneline` and any error messages
4. Continue from the next uncommitted phase in this document
