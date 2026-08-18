# Deployment

Phase 9 turns the control plane into something you can run in production. This
document covers the container image, the Helm chart, the Terraform substrate,
GitOps delivery through Argo CD, and the supply-chain guarantees on release
images. Nothing here is a bounded context; it is the operational layer around
the application built in Phases 1 through 8.

## Container image

The image is built from the multi-stage `Dockerfile` at the repository root. The
builder stage installs the package into a virtualenv; the runtime stage copies
that venv into a slim base, adds the migrations and `alembic.ini`, drops to a
non-root user, and declares a `HEALTHCHECK` against `/livez`. The entrypoint is
the `cascade` console script, which runs uvicorn bound to `CASCADE_HTTP_HOST`
and `CASCADE_HTTP_PORT`.

Build it locally:

```bash
docker build -t cascade:dev .
docker run --rm -p 8000:8000 \
  -e CASCADE_AUTH_ENABLED=false \
  -e CASCADE_DATABASE_URL=postgresql+asyncpg://cascade:cascade@host.docker.internal:5432/cascade \
  cascade:dev
curl localhost:8000/livez
```

## Helm chart

The chart lives at `deploy/helm/cascade`. It renders a hardened Deployment plus
the surrounding objects: a ConfigMap for non-secret `CASCADE_` env vars, a Secret
(or a reference to an existing one), a Service, an optional Ingress, an HPA, a
PodDisruptionBudget, a ServiceAccount with token automounting disabled, and a
default-deny NetworkPolicy that allows only DNS, Postgres, Redis, and outbound
HTTPS egress.

Database migrations run as a `pre-install` and `pre-upgrade` Helm hook Job that
executes `alembic upgrade head` before the new pods roll out, so a release never
serves traffic against an unmigrated schema.

The pod and container security contexts are locked down by default: non-root
user, read-only root filesystem (with an `emptyDir` mounted at `/tmp`), all Linux
capabilities dropped, no privilege escalation, and the RuntimeDefault seccomp
profile.

Render and lint before applying:

```bash
helm lint deploy/helm/cascade
helm template cascade deploy/helm/cascade -f deploy/helm/cascade/values-prod.yaml | kubeconform -strict -summary
```

Install or upgrade:

```bash
helm upgrade --install cascade deploy/helm/cascade \
  --namespace cascade --create-namespace \
  -f deploy/helm/cascade/values-prod.yaml
```

In production, provision the database and Redis URLs as a Kubernetes Secret out
of band and point the chart at it with `secret.existingSecret`, rather than
inlining values. Pin `image.tag` to the immutable digest signed by the release
workflow.

## Terraform (GCP substrate)

`deploy/terraform` provisions the infrastructure the chart expects: a VPC with a
subnet and secondary ranges for pods and services, a private GKE cluster with
Workload Identity, a regional Cloud SQL Postgres instance on a private IP with
backups and point-in-time recovery, a Memorystore Redis instance, an Artifact
Registry repository, and the Workload Identity binding that lets the in-cluster
service account act as a Google service account with the Cloud SQL client role.

State is stored in a GCS bucket configured at init time. The Postgres password
is passed as a sensitive variable rather than generated inline, so it never lands
in state as plaintext.

```bash
cd deploy/terraform
terraform init -backend-config="bucket=YOUR_TF_STATE_BUCKET" -backend-config="prefix=cascade"
terraform fmt -check
terraform validate
terraform plan -var="project_id=YOUR_PROJECT" -var="postgres_password=$(openssl rand -base64 24)"
```

This is a skeleton meant to be read and adapted, not applied blind. Review the
machine types, ranges, and deletion-protection settings against your own
environment first.

## GitOps with Argo CD

`deploy/argocd` holds an `AppProject` that scopes what may be deployed and from
where, and an `Application` that points at the Helm chart on `main` with both
`values.yaml` and `values-prod.yaml`. Sync is automated with prune and self-heal,
and the namespace is created on first sync.

```bash
kubectl apply -f deploy/argocd/project.yaml
kubectl apply -f deploy/argocd/application.yaml
```

Once applied, Argo CD reconciles the cluster to the chart on every commit to
`main`, so deployment becomes a git push rather than a manual `helm upgrade`.

## Supply chain

The `release` workflow runs on every `v*` tag. It builds and pushes the image to
GHCR, signs it keyless with cosign using GitHub OIDC (no long-lived keys),
generates an SPDX SBOM with syft and attaches it as a cosign attestation, emits
build provenance, and scans the image with Trivy.

Verify a release image before deploying:

```bash
cosign verify \
  --certificate-identity-regexp "https://github.com/Talif787/cascade/.github/workflows/release.yml@.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  ghcr.io/talif787/cascade@sha256:<digest>

cosign verify-attestation --type spdxjson \
  --certificate-identity-regexp "https://github.com/Talif787/cascade/.github/workflows/release.yml@.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  ghcr.io/talif787/cascade@sha256:<digest>
```

The `security` workflow adds a Trivy filesystem scan and a Trivy IaC/config scan
of `deploy/`, uploading both as SARIF to GitHub code scanning, and runs weekly on
a schedule as well as on pull requests. Dependabot keeps the pip, GitHub Actions,
and Docker dependencies current.

## Operational endpoints

Regardless of how it is deployed, the service exposes `/livez` for liveness,
`/readyz` for readiness (which checks database and Redis connectivity), and
`/metrics` for Prometheus. The chart's pod annotations mark the pods for
Prometheus scraping on the metrics path.
