import gradio as gr
def echo(t): return t
with gr.Blocks() as demo:
    c = gr.Code(language="sql", value='"CEO" OR "Vice President" AND "Manager"', label="Query")
demo.launch(server_port=7861)
