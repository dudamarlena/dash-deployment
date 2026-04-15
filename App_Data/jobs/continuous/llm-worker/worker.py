import json
import os
import time
import traceback
from datetime import datetime, timezone

from azure.storage.blob import BlobServiceClient

POLL_INTERVAL_SECONDS = int(os.environ.get("JOB_POLL_INTERVAL_SECONDS", "10"))
CONTAINER_NAME = os.environ.get("AZURE_STORAGE_CONTAINER", "jobs")
CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")

if not CONNECTION_STRING:
    raise RuntimeError("Missing AZURE_STORAGE_CONNECTION_STRING")

blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json_blob(blob_name: str) -> dict:
    blob_client = container_client.get_blob_client(blob_name)
    data = blob_client.download_blob().readall()
    return json.loads(data)


def write_json_blob(blob_name: str, payload: dict) -> None:
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(
        json.dumps(payload, ensure_ascii=False, indent=2),
        overwrite=True
    )


def delete_blob_if_exists(blob_name: str) -> None:
    blob_client = container_client.get_blob_client(blob_name)
    try:
        blob_client.delete_blob()
    except Exception:
        pass


def set_status(job_id: str, status: str, message: str = "", extra: dict | None = None) -> None:
    payload = {
        "jobId": job_id,
        "status": status,
        "updatedAt": utc_now_iso(),
        "message": message,
    }
    if extra:
        payload.update(extra)

    # zachowaj createdAt jeśli status już istnieje
    try:
        current = read_json_blob(f"status/{job_id}.json")
        payload["createdAt"] = current.get("createdAt", utc_now_iso())
    except Exception:
        payload["createdAt"] = utc_now_iso()

    write_json_blob(f"status/{job_id}.json", payload)


def run_llm(prompt: str) -> str:
    """
    Tutaj wstawisz swoje realne wywołanie LLM.
    Na start zostaw stub do testów.
    """
    time.sleep(5)
    return f"Wynik modelu dla promptu: {prompt[:200]}"


def process_one_job(blob_name: str) -> None:
    job_id = blob_name.split("/")[-1].replace(".json", "")

    try:
        set_status(job_id, "running", "Worker started processing the job.")

        input_payload = read_json_blob(blob_name)
        prompt = input_payload["prompt"]

        result = run_llm(prompt)

        output_payload = {
            "jobId": job_id,
            "result": result,
            "completedAt": utc_now_iso()
        }
        write_json_blob(f"output/{job_id}.json", output_payload)

        set_status(job_id, "completed", "Job finished successfully.")
        delete_blob_if_exists(blob_name)

    except Exception as exc:
        set_status(
            job_id,
            "failed",
            f"Worker failed: {str(exc)}",
            extra={"traceback": traceback.format_exc()}
        )


def get_pending_input_blobs() -> list[str]:
    blobs = container_client.list_blobs(name_starts_with="input/")
    names = [b.name for b in blobs if b.name.endswith(".json")]
    names.sort()
    return names


def main():
    print("Worker started.")
    while True:
        try:
            pending = get_pending_input_blobs()

            if not pending:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            first_job = pending[0]
            print(f"Processing {first_job}")
            process_one_job(first_job)

        except Exception as exc:
            print(f"Worker loop error: {exc}")
            print(traceback.format_exc())
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
    