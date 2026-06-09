import re

with open('app.py', 'r') as f:
    content = f.read()

# Make sure we load the config inside create_ui
create_ui_start = content.find("def create_ui():")
insert_point = content.find("with gr.Blocks", create_ui_start)

config_load = "    config = load_config()\n    init_query = config.get('query', DEFAULT_QUERY)\n    init_key1 = config.get('key1', '')\n    init_key2 = config.get('key2', '')\n\n    "
content = content[:insert_point] + config_load + content[insert_point:]

# Update the Textbox definitions
content = content.replace("value=DEFAULT_QUERY", "value=init_query")
content = content.replace("value=DEFAULT_KEY_1", "value=init_key1")
content = content.replace("value=DEFAULT_KEY_2", "value=init_key2")
content = content.replace("highlight_query(DEFAULT_QUERY)", "highlight_query(init_query)")

# Update process_ui to save the config
process_ui_start = content.find("def process_ui(")
insert_point2 = content.find("yield", process_ui_start)

save_logic = "    save_config({'query': query, 'key1': key1, 'key2': key2})\n    "
content = content[:insert_point2] + save_logic + content[insert_point2:]

with open('app.py', 'w') as f:
    f.write(content)
