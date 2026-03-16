"""
DAG: pipeline_health_check
Runs every hour.
Checks row counts in processed tables and logs a summary.
Useful for validating the pipeline is producing data.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

import psycopg2
from airflow import DAG
from airflow.operators.python import PythonOperator

log = logging.getLogger(__name__)

DB_CONFIG = {
    "host":     os.environ["RDS_HOST"],
    "port":     int(os.environ.get("RDS_PORT", 5432)),
    "dbname":   os.environ["RDS_DBNAME"],
    "user":     os.environ["RDS_USERNAME"],
    "password": os.environ["RDS_PASSWORD"],
}

default_args = {
    "owner": "data-team",
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}


def check_table_counts(**context):
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            tables = [
                "raw_users", "raw_orders",
                "processed_users", "processed_orders",
                "pipeline_runs",
            ]
            results = {}
            for table in tables:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                results[table] = cur.fetchone()[0]

            # Last 1h pipeline runs
            cur.execute(
                """
                SELECT COUNT(*), SUM(records_loaded)
                FROM pipeline_runs
                WHERE finished_at >= NOW() - INTERVAL '1 hour'
                """
            )
            row = cur.fetchone()
            results["runs_last_1h"]   = row[0]
            results["records_last_1h"] = row[1] or 0

    finally:
        conn.close()

    for k, v in results.items():
        log.info("  %-30s %d", k, v)

    # Raise alert if no runs in last hour
    if results["runs_last_1h"] == 0:
        raise ValueError(
            "ALERT: No pipeline runs in the last hour! "
            "Check the faker_data_pipeline DAG."
        )

    log.info("Health check passed.")


with DAG(
    dag_id="pipeline_health_check",
    description="Hourly check on pipeline row counts and run history",
    schedule_interval="@hourly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["monitoring", "health"],
) as dag:

    PythonOperator(
        task_id="check_counts",
        python_callable=check_table_counts,
    )
