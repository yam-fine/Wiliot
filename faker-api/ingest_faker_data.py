"""
DAG: faker_data_pipeline
Runs every 15 minutes.

Steps:
  1. fetch_users  — call faker-api, get 50 users, store raw in RDS
  2. fetch_orders — call faker-api, get 50 orders, store raw in RDS
  3. transform_and_load — enrich raw records, upsert into processed tables
  4. log_run      — record pipeline audit entry
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

import psycopg2
import requests
from airflow import DAG
from airflow.operators.python import PythonOperator

log = logging.getLogger(__name__)

# ── Connection details from env (injected by Helm via Kubernetes secret) ──────
DB_CONFIG = {
    "host":     os.environ["RDS_HOST"],
    "port":     int(os.environ.get("RDS_PORT", 5432)),
    "dbname":   os.environ["RDS_DBNAME"],
    "user":     os.environ["RDS_USERNAME"],
    "password": os.environ["RDS_PASSWORD"],
}

# faker-api runs as a ClusterIP service inside the same namespace
FAKER_API_BASE = "http://faker-api.data-pipeline.svc.cluster.local:3000"
BATCH_SIZE = 50

# ── Default DAG args ──────────────────────────────────────────────────────────
default_args = {
    "owner": "data-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "email_on_failure": False,
}


# ── Task functions ────────────────────────────────────────────────────────────

def fetch_and_store_users(**context):
    """Fetch users from faker-api and insert into raw_users."""
    url = f"{FAKER_API_BASE}/users?_limit={BATCH_SIZE}"
    log.info("Fetching users from %s", url)

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()

    # faker-api returns {"status": "OK", "code": 200, "data": [...]}
    users = data if isinstance(data, list) else data.get("data", [])
    log.info("Fetched %d users", len(users))

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            for user in users:
                cur.execute(
                    """
                    INSERT INTO raw_users
                        (external_id, firstname, lastname, email, phone, address)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(user.get("id", "")),
                        user.get("firstname", ""),
                        user.get("lastname", ""),
                        user.get("email", ""),
                        user.get("phone", ""),
                        json.dumps(user.get("address", {})),
                    ),
                )
        conn.commit()
        log.info("Inserted %d raw users", len(users))
    finally:
        conn.close()

    # Pass count to XCom for audit log
    context["ti"].xcom_push(key="users_fetched", value=len(users))


def fetch_and_store_orders(**context):
    """Fetch orders from faker-api and insert into raw_orders."""
    url = f"{FAKER_API_BASE}/orders?_limit={BATCH_SIZE}"
    log.info("Fetching orders from %s", url)

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()

    products = data if isinstance(data, list) else data.get("data", [])
    log.info("Fetched %d products/orders", len(products))

    import random
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            for product in products:
                quantity   = random.randint(1, 10)
                unit_price = float(product.get("price", 0))
                cur.execute(
                    """
                    INSERT INTO raw_orders
                        (external_id, user_id, product, quantity, unit_price,
                         total_price, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(product.get("id", "")),
                        str(random.randint(1, 1000)),   # simulated user ref
                        product.get("name", ""),
                        quantity,
                        unit_price,
                        round(unit_price * quantity, 2),
                        random.choice(["pending", "shipped", "delivered", "cancelled"]),
                    ),
                )
        conn.commit()
        log.info("Inserted %d raw orders", len(products))
    finally:
        conn.close()

    context["ti"].xcom_push(key="orders_fetched", value=len(products))


def transform_and_load(**context):
    """
    Read unprocessed raw records, enrich them, upsert into processed tables.
    Only processes records from the last 30 minutes to avoid reprocessing.
    """
    conn = psycopg2.connect(**DB_CONFIG)
    users_loaded = 0
    orders_loaded = 0

    try:
        with conn.cursor() as cur:

            # ── Process users ────────────────────────────────────────────────
            cur.execute(
                """
                SELECT external_id, firstname, lastname, email, phone, address
                FROM raw_users
                WHERE ingested_at >= NOW() - INTERVAL '30 minutes'
                """
            )
            raw_users = cur.fetchall()

            for row in raw_users:
                ext_id, first, last, email, phone, address = row
                full_name    = f"{first} {last}".strip()
                email_domain = email.split("@")[-1] if "@" in (email or "") else ""
                city    = address.get("city", "")    if isinstance(address, dict) else ""
                country = address.get("country", "") if isinstance(address, dict) else ""

                cur.execute(
                    """
                    INSERT INTO processed_users
                        (external_id, full_name, email, email_domain,
                         phone, city, country)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (external_id) DO UPDATE SET
                        full_name    = EXCLUDED.full_name,
                        email        = EXCLUDED.email,
                        email_domain = EXCLUDED.email_domain,
                        processed_at = NOW()
                    """,
                    (ext_id, full_name, email, email_domain, phone, city, country),
                )
                users_loaded += 1

            # ── Process orders ────────────────────────────────────────────────
            cur.execute(
                """
                SELECT external_id, user_id, product, quantity,
                       unit_price, total_price, status
                FROM raw_orders
                WHERE ingested_at >= NOW() - INTERVAL '30 minutes'
                """
            )
            raw_orders = cur.fetchall()

            for row in raw_orders:
                ext_id, user_id, product, qty, unit_price, total_price, status = row
                if total_price < 50:
                    band = "LOW"
                elif total_price < 200:
                    band = "MEDIUM"
                else:
                    band = "HIGH"

                cur.execute(
                    """
                    INSERT INTO processed_orders
                        (external_id, user_id, product, quantity,
                         unit_price, total_price, revenue_band, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (external_id) DO UPDATE SET
                        revenue_band = EXCLUDED.revenue_band,
                        status       = EXCLUDED.status,
                        processed_at = NOW()
                    """,
                    (ext_id, user_id, product, qty,
                     unit_price, total_price, band, status),
                )
                orders_loaded += 1

        conn.commit()
        log.info("Processed %d users, %d orders", users_loaded, orders_loaded)
    finally:
        conn.close()

    context["ti"].xcom_push(key="users_loaded",  value=users_loaded)
    context["ti"].xcom_push(key="orders_loaded", value=orders_loaded)


def log_pipeline_run(**context):
    """Write audit record to pipeline_runs table."""
    ti = context["ti"]
    run_id = context["run_id"]
    dag_id = context["dag"].dag_id

    users_fetched  = (ti.xcom_pull(key="users_fetched",  task_ids="fetch_users")  or 0)
    orders_fetched = (ti.xcom_pull(key="orders_fetched", task_ids="fetch_orders") or 0)
    users_loaded   = (ti.xcom_pull(key="users_loaded",   task_ids="transform_and_load") or 0)
    orders_loaded  = (ti.xcom_pull(key="orders_loaded",  task_ids="transform_and_load") or 0)

    total_fetched = users_fetched + orders_fetched
    total_loaded  = users_loaded  + orders_loaded

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pipeline_runs
                    (dag_id, run_id, records_fetched, records_loaded,
                     status, started_at)
                VALUES (%s, %s, %s, %s, 'success', NOW() - INTERVAL '15 minutes')
                """,
                (dag_id, run_id, total_fetched, total_loaded),
            )
        conn.commit()
    finally:
        conn.close()

    log.info(
        "Pipeline run logged — fetched: %d, loaded: %d",
        total_fetched, total_loaded,
    )


# ── DAG definition ────────────────────────────────────────────────────────────
with DAG(
    dag_id="faker_data_pipeline",
    description="Fetch dummy data from faker-api, transform, load into RDS",
    schedule_interval="*/15 * * * *",   # every 15 minutes
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["ingestion", "faker", "postgres"],
) as dag:

    t_fetch_users = PythonOperator(
        task_id="fetch_users",
        python_callable=fetch_and_store_users,
    )

    t_fetch_orders = PythonOperator(
        task_id="fetch_orders",
        python_callable=fetch_and_store_orders,
    )

    t_transform = PythonOperator(
        task_id="transform_and_load",
        python_callable=transform_and_load,
    )

    t_log = PythonOperator(
        task_id="log_run",
        python_callable=log_pipeline_run,
    )

    # fetch_users  ─┐
    #               ├──► transform_and_load ──► log_run
    # fetch_orders ─┘
    [t_fetch_users, t_fetch_orders] >> t_transform >> t_log
