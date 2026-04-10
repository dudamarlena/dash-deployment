import os
import json
import uuid
import base64

from dash import Dash, html, dcc, Input, Output, State, callback
from azure.storage.queue import QueueClient

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
    )


def send_job_to_queue(prompt: str):
    job_id = str(uuid.uuid4())

    payload = {
        "job_id": job_id,
        "prompt": prompt,
    }
    message = json.dumps(payload).encode("utf-8")
    encoded_message = base64.b64encode(message).decode("utf-8")

    queue_client = get_queue_client()
    queue_client.send_message(json.dumps(encoded_message))

    return job_id


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
    ],
    style={"maxWidth": "900px", "margin": "40px auto"},
)


@callback(
    Output("submit-status", "children"),
    Input("generate-btn", "n_clicks"),
    State("prompt-input", "value"),
    prevent_initial_call=True,
)
def submit_job(n_clicks, prompt):
    if not prompt or not prompt.strip():
        return "Wpisz prompt."

    try:
        job_id = send_job_to_queue(prompt)
        return f"Job wysłany. job_id={job_id}"
    except Exception as e:
        return f"Błąd przy wysyłaniu joba: {str(e)}"


if __name__ == "__main__":
    app.run(debug=True)