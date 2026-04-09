import azure.functions as func

app = func.FunctionApp()

@app.function_name(name="ProcessLlmJob")
@app.queue_trigger(
    arg_name="msg",
    queue_name="llm-jobs",
    connection="AzureWebJobsStorage",
)
def process_llm_job(msg: func.QueueMessage) -> None:
    return