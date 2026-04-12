import json
import logging
import os
import time
from datetime import datetime, timezone

import azure.functions as func
from azure.data.tables import TableServiceClient
from azure.storage.blob import BlobServiceClient

app = func.FunctionApp()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_storage_connection_string() -> str:
    conn = os.getenv("AzureWebJobsStorage")
    if not conn:
        raise RuntimeError("Missing AzureWebJobsStorage setting.")
    return conn


def get_table_client():
    conn = get_storage_connection_string()
    table_name = os.getenv("JOB_STATUS_TABLE", "llmjobs")
    service = TableServiceClient.from_connection_string(conn_str=conn)
    logging.info("Using table service URL: %s", service.url)
    logging.info("Using table name: %s", table_name)
    service.create_table_if_not_exists(table_name=table_name)
    return service.get_table_client(table_name=table_name)


def get_blob_container_client():
    conn = get_storage_connection_string()
    container_name = os.getenv("RESULTS_CONTAINER", "llm-results")
    service = BlobServiceClient.from_connection_string(conn_str=conn)
    container = service.get_container_client(container_name)
    try:
        container.create_container()
    except Exception:
        pass
    return container


def upsert_job_status(job_id: str, status: str, **extra_fields):
    table = get_table_client()
    entity = {
        "PartitionKey": "jobs",
        "RowKey": job_id,
        "job_id": job_id,
        "status": status,
        "updated_at": utc_now_iso(),
    }
    entity.update(extra_fields)
    table.upsert_entity(entity)


def run_llm(payload: dict) -> str:
    prompt = payload.get("prompt", "")
    time.sleep(300)
    return f"Generated response for prompt: {prompt}"


@app.function_name(name="ProcessLlmJob")
@app.queue_trigger(
    arg_name="msg",
    queue_name="llm-jobs",
    connection="AzureWebJobsStorage",
)
def process_llm_job(msg: func.QueueMessage) -> None:
    raw = msg.get_body().decode("utf-8")
    logging.info("Queue message received: %s", raw)

    payload = json.loads(raw)
    job_id = payload["job_id"]

    upsert_job_status(
        job_id=job_id,
        status="running",
        started_at=utc_now_iso(),   
    )

    try:
        result_text = run_llm(payload)

        blob_name = f"{job_id}.json"
        blob_payload = {
            "job_id": job_id,
            "status": "done",
            "result": result_text,
            "finished_at": utc_now_iso(),
        }

        container = get_blob_container_client()
        container.upload_blob(
            name=blob_name,
            data=json.dumps(blob_payload, ensure_ascii=False),
            overwrite=True,
        )

        upsert_job_status(
            job_id=job_id,
            status="done",
            finished_at=utc_now_iso(),
            result_blob_name=blob_name,
        )

        logging.info("Job %s finished successfully.", job_id)

    except Exception as exc:
        logging.exception("Job %s failed.", job_id)
        upsert_job_status(
            job_id=job_id,
            status="error",
            finished_at=utc_now_iso(),
            error_message=str(exc),
        )
        raise
    
    