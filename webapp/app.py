import os
import json
import uuid
import base64
from datetime import datetime, timezone

from dash import Dash, html, dcc, Input, Output, State, callback
from azure.storage.queue import QueueClient, TextBase64EncodePolicy
from azure.data.tables import TableClient
from azure.core.exceptions import ResourceNotFoundError
from dash import no_update
from azure.storage.blob import BlobServiceClient

app = Dash(__name__)
server = app.server


def get_storage_connection_string():
    conn = os.getenv("APP_STORAGE_CONNECTION_STRING")
    if not conn:
        raise RuntimeError("Missing APP_STORAGE_CONNECTION_STRING")
    return conn


def get_queue_client():
    return QueueClient.from_connection_string(
        conn_str=get_storage_connection_string(),
        queue_name=os.getenv("JOB_QUEUE_NAME", "llm-jobs"),
        message_encode_policy=TextBase64EncodePolicy(),
    )

def send_job_to_queue(prompt: str):
    job_id = str(uuid.uuid4())

    payload = {
        "job_id": job_id,
        "prompt": prompt,
    }

    queue_client = get_queue_client()
    queue_client.send_message(json.dumps(payload))

    return job_id

def get_table_client():
    return TableClient.from_connection_string(
        conn_str=get_storage_connection_string(),
        table_name=os.getenv("JOB_STATUS_TABLE", "llmjobs"),
    )


def get_job_status(job_id: str):
    table_client = get_table_client()
    return table_client.get_entity(partition_key="jobs", row_key=job_id)

app.layout = html.Div(
    [
        html.H2("LLM async demo"),
        dcc.Textarea(
            id="prompt-input",
            placeholder="Wpisz prompt...",
            style={"width": "100%", "height": "180px"},
        ),
        html.Br(),
        html.Button("Generate", id="generate-btn", n_clicks=0),
        html.Div(id="submit-status", style={"marginTop": "16px"}),
        html.Div(id="job-status", style={"marginTop": "12px"}),
        dcc.Store(id="job-store"),
        html.Div(id="elapsed-time", style={"marginTop": "8px"}),
        dcc.Interval(id="poll-interval", interval=5000, n_intervals=0, disabled=True),
        html.Pre(id="result-output", style={"whiteSpace": "pre-wrap", "marginTop": "16px"})
    ],
    style={"maxWidth": "900px", "margin": "40px auto"},
)

def get_blob_service_client():
    return BlobServiceClient.from_connection_string(
        conn_str=get_storage_connection_string()
    )


def get_job_result(blob_name: str) -> str:
    blob_service = get_blob_service_client()
    container_name = os.getenv("RESULTS_CONTAINER", "llm-results")

    blob_client = blob_service.get_blob_client(
        container=container_name,
        blob=blob_name,
    )

    blob_content = blob_client.download_blob().readall().decode("utf-8")
    result_json = json.loads(blob_content)

    return result_json.get("result", "")

@callback(
    Output("job-status", "children"),
    Output("result-output", "children"),
    Output("poll-interval", "disabled"),
    Output("elapsed-time", "children"),
    Input("poll-interval", "n_intervals"),
    State("job-store", "data"),
    prevent_initial_call=True,
    )
def poll_job_status(n_intervals, job_data):
        if not job_data or "job_id" not in job_data:
            return no_update, no_update, True, ""

        job_id = job_data["job_id"]
        started_at_raw = job_data.get("started_at")

        elapsed_text = ""
        if started_at_raw:
            started_at = datetime.fromisoformat(started_at_raw)
            now = datetime.now(timezone.utc)
            elapsed_seconds = int((now - started_at).total_seconds())
            minutes = elapsed_seconds // 60
            seconds = elapsed_seconds % 60
            elapsed_text = f"Czas od wysłania: {minutes:02d}:{seconds:02d}"

        try:
            entity = get_job_status(job_id)
        except ResourceNotFoundError:
            return f"Job {job_id}: status jeszcze niedostępny", no_update, False, elapsed_text
        except Exception as e:
            return f"Job {job_id}: błąd odczytu statusu: {str(e)}", no_update, False, elapsed_text

        status = entity.get("status", "unknown")

        if status in ["queued", "running"]:
            return f"Job {job_id}: {status}", no_update, False, elapsed_text

        if status == "done":
            blob_name = entity.get("result_blob_name")
            if not blob_name:
                return f"Job {job_id}: done, ale brak result_blob_name", no_update, True, elapsed_text

            try:
                result_text = get_job_result(blob_name)
                return f"Job {job_id}: done", result_text, True, elapsed_text
            except Exception as e:
                return f"Job {job_id}: done, ale błąd pobrania wyniku: {str(e)}", no_update, True, elapsed_text

        if status == "error":
            error_message = entity.get("error_message", "Unknown error")
            return f"Job {job_id}: error", error_message, True, elapsed_text

        return f"Job {job_id}: {status}", no_update, False, elapsed_text

@callback(
    Output("submit-status", "children"),
    Output("job-store", "data"),
    Output("poll-interval", "disabled"),
    Output("job-status", "children"),
    Output("result-output", "children"),
    Output("elapsed-time", "children"),
    Input("generate-btn", "n_clicks"),
    State("prompt-input", "value"),
    prevent_initial_call=True,
)
def submit_job(n_clicks, prompt):
    if not prompt or not prompt.strip():
        return "Wpisz prompt.", None, True, "", "", ""

    try:
        job_id = send_job_to_queue(prompt)
        started_at = datetime.now(timezone.utc).isoformat()

        return (
            f"Job wysłany. job_id={job_id}",
            {"job_id": job_id, "started_at": started_at},
            False,
            "Job uruchomiony...",
            "",
            "Czas od wysłania: 00:00",
        )
    except Exception as e:
        return f"Błąd przy wysyłaniu joba: {str(e)}", None, True, "", "", ""



if __name__ == "__main__":
    app.run(debug=True)