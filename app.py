from dash import Dash, html, dcc, Input, Output, State, callback, no_update
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from azure.storage.blob import BlobServiceClient

app = Dash(__name__)
server = app.server



CONNECTION_STRING = os.getenv("APP_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER", "llm-jobs")


def get_blob_service_client() -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(CONNECTION_STRING)


def get_container_client():
    service = get_blob_service_client()
    return service.get_container_client(CONTAINER_NAME)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def upload_json_blob(blob_name: str, payload: dict) -> None:
    container = get_container_client()
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    blob_client = container.get_blob_client(blob_name)
    blob_client.upload_blob(data, overwrite=True)


def create_job(prompt: str, user_id: str | None = None) -> str:
    job_id = str(uuid4())

    status_payload = {
        "jobId": job_id,
        "status": "pending",
        "createdAt": utc_now_iso(),
        "updatedAt": utc_now_iso(),
        "message": "Job created and waiting for worker."
    }

    input_payload = {
        "jobId": job_id,
        "prompt": prompt,
        "userId": user_id,
        "createdAt": utc_now_iso()
    }

    # Najpierw status, potem input
    upload_json_blob(f"status/{job_id}.json", status_payload)
    upload_json_blob(f"input/{job_id}.json", input_payload)

    return job_id






app.layout = html.Div([
    dcc.Textarea(id="prompt-input", style={"width": "100%", "height": "200px"}),
    html.Button("Generate", id="generate-btn"),
    html.Div(id="job-result"),
    dcc.Store(id="current-job-id")
])

@callback(
    Output("job-result", "children"),
    Output("current-job-id", "data"),
    Input("generate-btn", "n_clicks"),
    State("prompt-input", "value"),
    prevent_initial_call=True
)
def submit_prompt(n_clicks, prompt):
    if not prompt or not prompt.strip():
        return "Prompt is empty.", no_update

    job_id = create_job(prompt.strip())

    return f"Job created: {job_id}", job_id