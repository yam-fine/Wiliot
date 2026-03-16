# Helm Deployment Guide — Airflow + Faker API on EKS

## Architecture

```
Apache Airflow (EKS)
  └── DAG: every 15 min
        ├── 1. Call faker-api  →  generates dummy JSON data
        ├── 2. Transform data  →  clean / enrich records
        └── 3. Insert into RDS PostgreSQL
```

Open-source app used: **faker-api** (https://github.com/joolfe/faker-api)
- REST API that generates realistic dummy data (users, orders, products)
- Has an official Helm chart
- Perfect for Airflow-triggered ingestion simulation

---

## Prerequisites (run once)

```powershell
# 1. Connect kubectl to your EKS cluster
aws eks update-kubeconfig --region us-east-1 --name yam-eks-cluster --profile sandbox

# 2. Add required Helm repos
helm repo add apache-airflow https://airflow.apache.org
helm repo add faker-api     https://joolfe.github.io/faker-api
helm repo update

# 3. Create the kubernetes namespace
kubectl create namespace data-pipeline
```

---

## Step 1 — Create Kubernetes Secrets

```powershell
# RDS credentials (replace with your actual RDS endpoint from terraform output)
kubectl create secret generic rds-credentials `
  --namespace data-pipeline `
  --from-literal=host="yam-postgres.xxxxxxxxx.us-east-1.rds.amazonaws.com" `
  --from-literal=port="5432" `
  --from-literal=dbname="appdb" `
  --from-literal=username="dbadmin" `
  --from-literal=password="Sandbox2025!Secure"

# Airflow fernet key (used to encrypt DAG connections)
# Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
kubectl create secret generic airflow-fernet-key `
  --namespace data-pipeline `
  --from-literal=fernet-key="YOUR_GENERATED_FERNET_KEY"
```

---

## Step 2 — Deploy faker-api

```powershell
helm upgrade --install faker-api faker-api/faker-api `
  --namespace data-pipeline `
  --values helm/faker-api/values.yaml
```

Verify:
```powershell
kubectl get pods -n data-pipeline
kubectl get svc  -n data-pipeline
# Test locally:
kubectl port-forward svc/faker-api 3000:3000 -n data-pipeline
# Then open: http://localhost:3000/api/users
```

---

## Step 3 — Create RDS Schema

```powershell
# Port-forward to RDS via a temporary pod
kubectl run psql-client --rm -it --image=postgres:15 --namespace data-pipeline -- `
  psql "postgresql://dbadmin:Sandbox2025!Secure@<RDS_ENDPOINT>:5432/appdb" `
  -f /sql/schema.sql
```

Or copy the schema.sql contents and run directly in your SQL client.

---

## Step 4 — Deploy Airflow DAGs via ConfigMap

```powershell
# Package all DAGs into a ConfigMap
kubectl create configmap airflow-dags `
  --namespace data-pipeline `
  --from-file=dags/ingest_faker_data.py `
  --from-file=dags/transform_and_load.py `
  --dry-run=client -o yaml | kubectl apply -f -
```

---

## Step 5 — Deploy Airflow

```powershell
helm upgrade --install airflow apache-airflow/airflow `
  --namespace data-pipeline `
  --values helm/airflow/values.yaml `
  --timeout 10m
```

Monitor rollout:
```powershell
kubectl get pods -n data-pipeline -w
# Wait for all pods Running (scheduler, webserver, triggerer, workers)
```

---

## Step 6 — Access Airflow UI

```powershell
kubectl port-forward svc/airflow-webserver 8080:8080 -n data-pipeline
```
Open: http://localhost:8080
Login: admin / admin

Enable the DAG **"faker_data_pipeline"** — it will run every 15 minutes automatically.

---

## Verify Data is Flowing

```powershell
# Watch DAG runs
kubectl port-forward svc/airflow-webserver 8080:8080 -n data-pipeline

# Check RDS directly via psql pod
kubectl run psql-check --rm -it --image=postgres:15 --namespace data-pipeline -- \
  psql "postgresql://dbadmin:Sandbox2025!Secure@<RDS_ENDPOINT>:5432/appdb" \
  -c "SELECT COUNT(*) FROM raw_users; SELECT COUNT(*) FROM processed_orders;"
```

---

## Cleanup

```powershell
helm uninstall airflow   -n data-pipeline
helm uninstall faker-api -n data-pipeline
kubectl delete namespace data-pipeline
```
