import re

with open('app.py', 'r') as f:
    content = f.read()

# Replace config functions
old_config = """def load_saved_cv_path():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                path = data.get("cv_path")
                if path and os.path.exists(path):
                    return path
    except:
        pass
    return None

def save_cv_path(file_obj):
    if not file_obj:
        return
    # Gradio gr.File returns a temp file object or path string
    path = file_obj.name if hasattr(file_obj, "name") else str(file_obj)
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"cv_path": path}, f)
    except Exception as e:
        logging.warning(f"Could not save CV config: {e}")"""

new_config = """def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_config(updates):
    config = load_config()
    config.update(updates)
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except Exception as e:
        logging.warning(f"Could not save config: {e}")

def load_saved_cv_path():
    path = load_config().get("cv_path")
    if path and os.path.exists(path):
        return path
    return None

def save_cv_path(file_obj):
    if not file_obj:
        return
    path = file_obj.name if hasattr(file_obj, "name") else str(file_obj)
    save_config({"cv_path": path})"""

content = content.replace(old_config, new_config)

# Remove keys
content = re.sub(r'DEFAULT_KEY_1\s*=\s*".*?"\n', '', content)
content = re.sub(r'DEFAULT_KEY_2\s*=\s*".*?"\n', '', content)

with open('app.py', 'w') as f:
    f.write(content)
