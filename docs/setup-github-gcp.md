# GitHub and GCP setup (Cloud Shell)

This guide takes the Cascade control plane from a local folder to a GitHub repository
with keyless CI to Google Cloud, using GCP Cloud Shell as the only environment. It
assumes you are working entirely inside Cloud Shell, which already has `gcloud`,
`docker`, and `git` preinstalled and is authenticated to your Google account.

## 0. Variables

Set these once per shell session. Everything below reuses them.

```bash
export PROJECT_ID="your-gcp-project-id"       # existing GCP project with billing
export REGION="us-central1"                    # Artifact Registry / Cloud Run region
export GITHUB_USER="your-github-username"       # your GitHub user or org
export REPO_NAME="cascade"
export SA_NAME="cascade-ci"
```

## 1. Verify the Cloud Shell toolchain

```bash
gcloud --version
docker --version
git --version
gh --version || echo "gh not found: install it (see note below)"
python3 --version
```

Notes specific to Cloud Shell:

- Only your home directory (`$HOME`, about 5 GB) persists between sessions. Anything
  installed outside `$HOME` is wiped when the VM recycles (after idle timeout or the
  weekly refresh). Keep the repo and the virtualenv under `$HOME`, and commit and push
  often so nothing is lost.
- `gh` (the GitHub CLI) is normally preinstalled. If it is missing, the most durable
  option is to authenticate over HTTPS with a token instead, or reinstall `gh` each
  session; because installs outside `$HOME` do not persist, prefer `gh` when present.
- If `python3 --version` is below 3.12, use pyenv (preinstalled, and it lives under
  `$HOME/.pyenv`, so it persists):
  ```bash
  pyenv install -s 3.12
  pyenv local 3.12
  ```

## 2. Configure git identity

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
git config --global init.defaultBranch main
git config --global pull.rebase true
```

## 3. Authenticate the GitHub CLI

```bash
gh auth login          # choose GitHub.com, HTTPS, then authenticate in the browser
gh auth setup-git      # lets `git push` reuse the gh credentials over HTTPS
gh auth status
```

## 4. Confirm the GCP project

Cloud Shell is already signed in. Point it at the right project:

```bash
gcloud config set project "$PROJECT_ID"
gcloud config list
```

## 5. Import the project into Cloud Shell

You already have `cascade-phase1.zip`. Upload it with the Cloud Shell terminal menu
(the three-dot menu, then Upload), then:

```bash
cd ~
unzip -o ~/cascade-phase1.zip -d ~      # creates ~/cascade
cd ~/cascade
ls
```

On later sessions you will not repeat this step; you will simply clone from GitHub:

```bash
git clone https://github.com/$GITHUB_USER/$REPO_NAME.git ~/cascade
```

## 6. First commit and repository creation

The repository already ships a `.gitignore` that excludes `.env`, caches, and virtual
environments, so nothing sensitive is committed.

```bash
cd ~/cascade
git init -b main
git add .
git commit -m "chore: scaffold Cascade control plane (Phase 1)"

# Create the GitHub repo, set 'origin', and push in one step.
# Use --public for portfolio visibility, or --private if you prefer.
gh repo create "$GITHUB_USER/$REPO_NAME" --public --source=. --remote=origin --push
```

Confirm:

```bash
git remote -v
gh repo view --web
```

## 7. Branch strategy

Trunk-based development keeps things simple and matches the CI in this repo: `main` is
always releasable and protected; day-to-day work happens on short-lived branches that
merge back through pull requests.

- `main`: protected, always green, deployable.
- `feature/<slug>`: one branch per unit of work (for example `feature/data-contracts`).
- `fix/<slug>`, `chore/<slug>`, `docs/<slug>`: same idea, different intent.

Protect `main` (branch protection on public repos is free; on private repos some
options require a paid plan). The status check contexts below match the CI job names in
`.github/workflows/ci.yml`.

```bash
cat > /tmp/protection.json <<'JSON'
{
  "required_status_checks": { "strict": true, "contexts": ["quality", "test"] },
  "enforce_admins": true,
  "required_pull_request_reviews": { "required_approving_review_count": 0 },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON

gh api -X PUT "repos/$GITHUB_USER/$REPO_NAME/branches/main/protection" \
  -H "Accept: application/vnd.github+json" --input /tmp/protection.json
```

Create a feature branch to work in:

```bash
git switch -c feature/phase-1-hardening
```

## 8. Environment configuration

Create a local `.env` from the template. It is gitignored and never committed.

```bash
cp .env.example .env
# For local runs in Cloud Shell you can bypass auth:
sed -i 's/^CASCADE_AUTH_ENABLED=.*/CASCADE_AUTH_ENABLED=false/' .env
```

Run the stack locally in Cloud Shell (Docker is available):

```bash
# Quick path: everything in containers (no host Python needed).
make up            # postgres, redis, jaeger, prometheus, api on :8000
curl -s localhost:8000/livez

# Dev path: fast unit and API tests in a virtualenv under $HOME.
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
make migrate       # needs postgres running (docker compose up -d postgres redis)
make test
```

Secrets for the cloud (used from Phase 3 onward) belong in Secret Manager, not in the
repo:

```bash
printf 's3cr3t' | gcloud secrets create cascade-jwt-secret --data-file=-
```

## 9. Connect GitHub to GCP with keyless CI (Workload Identity Federation)

This lets GitHub Actions authenticate to Google Cloud with short-lived tokens and no
stored keys. Run all of it from Cloud Shell.

### 9.1 Enable the required APIs

```bash
gcloud services enable \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  secretmanager.googleapis.com \
  run.googleapis.com
```

### 9.2 Create an Artifact Registry Docker repository (CI pushes images here)

```bash
gcloud artifacts repositories create "$REPO_NAME" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Cascade control plane images"
```

### 9.3 Create the Workload Identity Pool and GitHub OIDC provider

The attribute condition is the security boundary that decides which GitHub tokens are
even allowed into the pool. Restrict it to your account, then scope the IAM binding to
the exact repository in the next step.

```bash
gcloud iam workload-identity-pools create github \
  --location=global \
  --display-name="GitHub Actions Pool"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global \
  --workload-identity-pool=github \
  --display-name="GitHub provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner == '${GITHUB_USER}'"
```

### 9.4 Create a least-privilege service account for CI

```bash
gcloud iam service-accounts create "$SA_NAME" \
  --display-name="Cascade CI (GitHub Actions)"

export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Only what Phase 1 CI needs: push images to Artifact Registry.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/artifactregistry.writer"
```

### 9.5 Allow only this repository to impersonate the service account

```bash
export WIF_POOL_ID=$(gcloud iam workload-identity-pools describe github \
  --location=global --format='value(name)')

gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${WIF_POOL_ID}/attribute.repository/${GITHUB_USER}/${REPO_NAME}"
```

### 9.6 Capture the provider resource name

```bash
export WIF_PROVIDER=$(gcloud iam workload-identity-pools providers describe github-provider \
  --location=global --workload-identity-pool=github \
  --format='value(name)')
echo "$WIF_PROVIDER"
```

### 9.7 Store the wiring in GitHub

The provider name and service account email are identifiers, not secrets, but storing
them as Actions secrets is a clean, conventional choice.

```bash
gh secret set GCP_WIF_PROVIDER    --body "$WIF_PROVIDER"
gh secret set GCP_SERVICE_ACCOUNT --body "$SA_EMAIL"
gh variable set GCP_PROJECT_ID    --body "$PROJECT_ID"
gh variable set GCP_REGION        --body "$REGION"
gh variable set AR_REPO           --body "$REPO_NAME"
```

## 10. Add an image build-and-push job to CI

Append this job to `.github/workflows/ci.yml`. It runs only on `main`, authenticates
with WIF, and pushes an image tagged with the commit SHA. The `id-token: write`
permission is required for the OIDC exchange.

```yaml
  push-image:
    runs-on: ubuntu-latest
    needs: [quality, test]
    if: github.ref == 'refs/heads/main'
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v6
      - id: auth
        uses: google-github-actions/auth@v3
        with:
          project_id: ${{ vars.GCP_PROJECT_ID }}
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}
      - uses: google-github-actions/setup-gcloud@v3
      - name: Configure Docker for Artifact Registry
        run: gcloud auth configure-docker ${{ vars.GCP_REGION }}-docker.pkg.dev --quiet
      - name: Build and push
        run: |
          IMAGE="${{ vars.GCP_REGION }}-docker.pkg.dev/${{ vars.GCP_PROJECT_ID }}/${{ vars.AR_REPO }}/control-plane:${{ github.sha }}"
          docker build -t "$IMAGE" .
          docker push "$IMAGE"
```

Commit it on a branch and open a pull request:

```bash
git add .github/workflows/ci.yml docs/setup-github-gcp.md
git commit -m "ci: push image to Artifact Registry via workload identity federation"
git push -u origin HEAD
gh pr create --fill
```

Watch the run, then merge:

```bash
gh run watch
gh pr merge --squash --delete-branch
```

## 11. Everyday workflow (Phase 1)

1. Start from an updated main:
   ```bash
   git switch main && git pull
   git switch -c feature/<slug>
   ```
2. Work, then run checks locally before pushing:
   ```bash
   source .venv/bin/activate
   make fmt && make lint && make typecheck && make test
   ```
3. Commit using conventional commits (`feat`, `fix`, `chore`, `docs`, `test`,
   `refactor`, `ci`):
   ```bash
   git add -A
   git commit -m "feat(pipelines): add cursor-based listing"
   ```
4. Push and open a PR; CI runs `quality`, `test`, `integration`, and the image build:
   ```bash
   git push -u origin HEAD
   gh pr create --fill
   gh run watch
   ```
5. Merge when green and clean up:
   ```bash
   gh pr merge --squash --delete-branch
   ```
6. Tag each completed phase:
   ```bash
   git switch main && git pull
   git tag -a v0.1.0-phase1 -m "Phase 1: control plane foundation and pipeline slice"
   git push origin v0.1.0-phase1
   ```

## 12. Optional: enable pre-commit

```bash
source .venv/bin/activate
pip install pre-commit
pre-commit install
```

Now `ruff`, formatting, and `mypy` run automatically before each commit, catching
issues before CI does.
