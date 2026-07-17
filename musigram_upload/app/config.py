import os
import json
import hashlib

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "telegram": {
        "api_id": "",
        "api_hash": "",
        "phone": "",
        "bot_username": "deezload2bot"
    },
    "storage": {
        "base_path": "G:\\Mi unidad\\musica",
        "default_folder": "",
        "categories": {
            "Reggeton": ["reggaeton", "dembow", "trap latino", "urbano", "latino", "salsa", "bachata", "reggeton"],
            "Pop": ["pop", "indie", "alternative", "acoustic"],
            "Comercial": ["comercial", "top", "hits", "radio", "commercial"],
            "Techno": ["techno", "minimal", "tech house", "house", "electro", "acid", "trance", "electronic", "dance", "edm"],
            "Mesclas ya echas": ["mix", "sesion", "session", "mezcla", "mashup", "set", "dj set"],
            "rock": ["rock", "metal", "punk", "grunge", "hard rock"],
            "chill": ["chill", "lofi", "ambient", "relax", "chillout", "relaxed"],
            "canta juegos": ["canta juegos", "infantil", "kids", "cantar", "canciones infantiles"],
            "Canticos": ["canticos", "himno", "futbol"],
            "Asantomera": ["asantomera"]
        }
    },
    "admin": {
        "username": "admin",
        "password": "admin"
    }
}

def get_admin_token():
    cfg = get_config()
    admin = cfg.get("admin", {"username": "admin", "password": "admin"})
    return hashlib.sha256(f"{admin.get('username')}:{admin.get('password')}:secret_salt_12345".encode()).hexdigest()

def verify_admin_token(token):
    if not token:
        return False
    # If token starts with Bearer, remove it
    if token.startswith("Bearer "):
        token = token[7:]
    return token == get_admin_token()

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            # Ensure all keys exist by merging with default
            merged = merge_configs(DEFAULT_CONFIG, config)
            return merged
    except Exception as e:
        print(f"Error cargando config.json, usando valores por defecto: {e}")
        return DEFAULT_CONFIG

def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error guardando config.json: {e}")
        return False

def merge_configs(default, current):
    """Recursively merges current config into default config to ensure no missing keys."""
    merged = default.copy()
    for key, value in current.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_configs(merged[key], value)
        else:
            merged[key] = value
    return merged

# Load config once initially
config_data = load_config()

def get_config():
    global config_data
    return config_data

def update_config(new_config):
    global config_data
    config_data = merge_configs(config_data, new_config)
    save_config(config_data)
    return config_data

def init_folders():
    """Create the Google Drive base folder and subfolders if they do not exist."""
    cfg = get_config()
    base = cfg["storage"]["base_path"]
    
    # Bypass folder creation for rclone cloud remote paths
    if base.startswith("rclone:"):
        return [], []
        
    folders_to_create = [cfg["storage"]["default_folder"]] + list(cfg["storage"]["categories"].keys())
    
    # Try to create directories
    created = []
    failed = []
    
    # If base path doesn't exist, we try to create it, but we handle permissions
    try:
        if not os.path.exists(base):
            os.makedirs(base, exist_ok=True)
            created.append(base)
    except Exception as e:
        print(f"Error creando directorio base: {base}. Detalle: {e}")
        failed.append(base)
        return created, failed

    for folder in folders_to_create:
        if not folder:  # Skip empty strings (e.g. if default_folder is "")
            continue
        folder_path = os.path.join(base, folder)
        try:
            if not os.path.exists(folder_path):
                os.makedirs(folder_path, exist_ok=True)
                created.append(folder_path)
        except Exception as e:
            print(f"Error creando directorio de categoría: {folder_path}. Detalle: {e}")
            failed.append(folder_path)
            
    return created, failed
