# CD pipeline (GitHub Actions → ECR → EC2, with manual approval)

Workflow: [`.github/workflows/cd.yml`](../.github/workflows/cd.yml)

```
push to main (or "Run workflow")
  → build   docker build, smoke test (API /health, Streamlit /_stcore/health), push to ECR as get-well-ocr:<commit-sha7>
  → deploy  waits for approval in the "production" environment
            → SSM runs deploy/remote-deploy.sh on the instance:
              pull, switch API and Streamlit app, check both, roll back automatically if one does not come up
```

After a deploy the instance runs:

| What | Container | Port | Health |
|---|---|---|---|
| API | `gwo-api` (or the `gwo` systemd service) | 8000 | `/health` |
| Streamlit app with login | `gwo-app` | 8501 | `/_stcore/health` |

No AWS keys are stored in GitHub (OIDC), and port 22 does not need to be open (SSM).

## One-time setup

### 1. EC2 instance: allow SSM

Add the managed policy **`AmazonSSMManagedInstanceCore`** to the instance role (it already needs
`AmazonEC2ContainerRegistryReadOnly`). The SSM agent is preinstalled on Amazon Linux 2023.
Check after a minute or two (the instance must show up):

```powershell
aws ssm describe-instance-information --region eu-north-1 --query "InstanceInformationList[].InstanceId"
```

The instance can run either the `gwo` systemd service from `ec2-user-data.sh` or a plain `gwo-api`
container; `remote-deploy.sh` handles both.

### 1b. EC2 instance: settings and app login

The Streamlit app only opens with a login, from `APP_USERNAME` / `APP_PASSWORD`. Put them (and any other
settings) into `/etc/gwo/env` on the instance; the deploy script passes this file to both containers:

```bash
sudo mkdir -p /etc/gwo && sudo touch /etc/gwo/env && sudo chmod 600 /etc/gwo/env
sudo nano /etc/gwo/env
```

```
APP_USERNAME=<choose>
APP_PASSWORD=<choose>
OCR_ENGINE=tesseract
```

Changes take effect with the next deploy (or restart the containers by hand).
Open port **8501** (and 8000 for the API) in the instance's security group, source *My IP*.
The app is then at `http://<public-ip>:8501`. It is plain HTTP; for anything beyond a demo use an SSH tunnel
(`ssh -L 8501:localhost:8501 ec2-user@<public-ip>`) or put HTTPS in front.

### 2. AWS: let GitHub log in (OIDC provider, once per account)

```powershell
aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com --client-id-list sts.amazonaws.com
```

### 3. AWS: role for the workflow

In [`iam/github-deploy-policy.json`](iam/github-deploy-policy.json) replace `INSTANCE_ID_HERE` with the instance ID, then:

```powershell
aws iam create-role --role-name gwo-github-deploy --assume-role-policy-document file://deploy/iam/github-trust-policy.json
aws iam put-role-policy --role-name gwo-github-deploy --policy-name gwo-deploy --policy-document file://deploy/iam/github-deploy-policy.json
```

The trust policy only accepts `main` (build job) and the `production` environment (deploy job) of
`uromi06/get_well_OCR`. If the repo is renamed or moved, update it.

### 4. GitHub: approval

Repo **Settings → Environments → New environment** `production`:

- **Required reviewers**: add the people who may approve deployments
- **Deployment branches and tags**: *Selected branches* → `main`

> Required reviewers work on **public** repos on every plan. On **private** repos they need GitHub Enterprise;
> otherwise the deploy job runs without waiting.

### 5. GitHub: variables

Repo **Settings → Secrets and variables → Actions → Variables**:

| Name | Value |
|---|---|
| `AWS_ROLE_ARN` | `arn:aws:iam::363183905530:role/gwo-github-deploy` |
| `EC2_INSTANCE_ID` | `i-...` |
| `AWS_REGION` | optional, default `eu-north-1` |
| `ECR_REPOSITORY` | optional, default `get-well-ocr` |

## Daily use

- **Deploy**: merge/push to `main` → *Actions* → run → **Review deployments** → *Approve and deploy*.
- **Deploy without a push**: *Actions → CD → Run workflow*.
- **Roll back**: open an older successful run and **Re-run** its *Deploy to EC2* job (it deploys that run's image).
- **Logs on the instance**: `sudo docker logs -f gwo-api` (API, or `sudo journalctl -u gwo -f`) and `sudo docker logs -f gwo-app` (Streamlit).
