# CD pipeline (GitHub Actions → ECR → EC2, with manual approval)

Workflow: [`.github/workflows/cd.yml`](../.github/workflows/cd.yml)

```
push to main (or "Run workflow")
  → build   docker build, smoke test GET /health, push to ECR as get-well-ocr:<commit-sha7>
  → deploy  waits for approval in the "production" environment
            → SSM runs deploy/remote-deploy.sh on the instance:
              pull, switch, check /health, roll back automatically if the new version does not come up
```

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
- **Logs on the instance**: `sudo docker logs -f gwo-api` or `sudo journalctl -u gwo -f`.
