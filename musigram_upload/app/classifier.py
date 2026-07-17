import os
import shutil
import unicodedata
import re
import subprocess
import urllib.request
import urllib.parse
import json
from tinytag import TinyTag
from app.config import get_config

def clean_text(text):
    if not text:
        return ""
    return text.lower().strip()

def match_genre_keywords(genre_str, categories):
    genre_cleaned = clean_text(genre_str)
    if not genre_cleaned:
        return None
        
    for category, keywords in categories.items():
        for kw in keywords:
            kw_cleaned = clean_text(kw)
            if kw_cleaned in genre_cleaned:
                return category
    return None

def match_text_keywords(text, categories):
    text_cleaned = clean_text(text)
    if not text_cleaned:
        return None
        
    for category, keywords in categories.items():
        for kw in keywords:
            kw_cleaned = clean_text(kw)
            if kw_cleaned in text_cleaned:
                return category
    return None

def clean_song_name(filename):
    name, _ = os.path.splitext(filename)
    # Remove brackets and parentheses content like [ugZ3DQYYaWQ] or (Official Video)
    name = re.sub(r'\[[^\]]+\]', '', name)
    name = re.sub(r'\([^\)]+\)', '', name)
    # Remove common words
    name = re.sub(r'(?i)\b(official video|official audio|lyric video|video oficial|audio oficial|lyrics|remix|feat|ft)\b', '', name)
    # Remove "iframe" prefix if it exists
    name = re.sub(r'(?i)\biframe\b', '', name)
    # Clean whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def query_itunes(song_name):
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode({
        'term': song_name,
        'media': 'music',
        'limit': 1
    })
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'MusiGram/1.0'}
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode('utf-8'))
            results = data.get('results', [])
            if results:
                track = results[0]
                return {
                    'genre': track.get('primaryGenreName', ''),
                    'artist': track.get('artistName', ''),
                    'title': track.get('trackName', '')
                }
    except Exception as e:
        print(f"Error consultando iTunes Search API para '{song_name}': {e}")
    return None

def query_wikipedia(song_name):
    url = "https://es.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        'action': 'query',
        'list': 'search',
        'srsearch': f"{song_name} genero musical",
        'format': 'json',
        'utf8': 1
    })
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'MusiGramClassifier/1.0 (joelgomez@example.com)'}
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode('utf-8'))
            search_results = data.get('query', {}).get('search', [])
            snippets = []
            for res in search_results:
                title = res.get('title', '')
                snippet = res.get('snippet', '')
                clean_snippet = re.sub(r'<[^>]+>', '', snippet)
                snippets.append(f"{title} {clean_snippet}")
            return snippets
    except Exception as e:
        print(f"Error consultando Wikipedia API para '{song_name}': {e}")
    return []

def classify_by_web_search(filename, categories):
    clean_name = clean_song_name(filename)
    if not clean_name:
        return None
        
    print(f"Buscando genero en la web para: '{clean_name}'...")
    
    # 1. Try iTunes Search API
    itunes_res = query_itunes(clean_name)
    if itunes_res:
        combined_itunes = f"{itunes_res['genre']} {itunes_res['title']} {itunes_res['artist']}"
        matched = match_text_keywords(combined_itunes, categories)
        if matched:
            print(f"Clasificado por iTunes ('{combined_itunes}') -> {matched}")
            return matched

    # 2. Try Wikipedia Search API as backup
    wikipedia_snippets = query_wikipedia(clean_name)
    if wikipedia_snippets:
        combined_wiki = " ".join(wikipedia_snippets)
        combined_cleaned = re.sub(r'[^a-z0-9áéíóúñ]', ' ', combined_wiki.lower())
        combined_cleaned = " " + " ".join(combined_cleaned.split()) + " "
        
        scores = {}
        for cat, keywords in categories.items():
            score = 0
            cat_cleaned = cat.lower().strip()
            if f" {cat_cleaned} " in combined_cleaned:
                score += combined_cleaned.count(f" {cat_cleaned} ") * 2
                
            for kw in keywords:
                kw_cleaned = kw.lower().strip()
                if f" {kw_cleaned} " in combined_cleaned:
                    score += combined_cleaned.count(f" {kw_cleaned} ")
                    
            if score > 0:
                scores[cat] = score
                
        if scores:
            winner = max(scores, key=scores.get)
            print(f"Clasificado por Wikipedia ({scores}) -> {winner}")
            return winner
            
    return None

def determine_category(file_path, user_selected_category=None):
    """
    Determines the target folder/category for a file based on:
    1. User's explicit choice (if provided)
    2. ID3 tag 'genre'
    3. Filename/Title/Artist keywords
    """
    cfg = get_config()
    categories = cfg["storage"]["categories"]
    default_folder = cfg["storage"]["default_folder"]
    
    # 1. User manual override
    if user_selected_category and user_selected_category in categories:
        return user_selected_category
    if user_selected_category == default_folder:
        return default_folder

    filename = os.path.basename(file_path)
    title = ""
    artist = ""
    genre = ""
    
    # Read tags
    try:
        if TinyTag.is_supported(file_path):
            tag = TinyTag.get(file_path)
            title = tag.title or ""
            artist = tag.artist or ""
            genre = tag.genre or ""
    except Exception as e:
        print(f"Error al leer etiquetas ID3 de {filename}: {e}")

    # 2. Match by Genre tag
    if genre:
        matched_cat = match_genre_keywords(genre, categories)
        if matched_cat:
            print(f"Clasificado por género ID3 '{genre}' -> {matched_cat}")
            return matched_cat
            
    # 3. Match by Title/Artist
    if title or artist:
        combined_meta = f"{title} {artist}"
        matched_cat = match_text_keywords(combined_meta, categories)
        if matched_cat:
            print(f"Clasificado por título/artista '{combined_meta}' -> {matched_cat}")
            return matched_cat

    # 4. Match by Filename
    matched_cat = match_text_keywords(filename, categories)
    if matched_cat:
        print(f"Clasificado por nombre de archivo '{filename}' -> {matched_cat}")
        return matched_cat

    # 5. Try Web Search Classification (iTunes + Wikipedia)
    web_matched = classify_by_web_search(filename, categories)
    if web_matched:
        print(f"Clasificado por busqueda web '{filename}' -> {web_matched}")
        return web_matched

    # 6. Default fallback
    print(f"No se pudo clasificar '{filename}'. Usando carpeta por defecto: {default_folder}")
    return default_folder

def sanitize_filename(filename):
    # Remove characters that are invalid in Windows filenames: < > : " / \ | ? *
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    return sanitized.strip()

def classify_and_move(temp_file_path, user_selected_category=None):
    """
    Classifies the downloaded file and moves it to the appropriate Google Drive directory.
    Returns: (success_boolean, destination_path, matched_category)
    """
    if not os.path.exists(temp_file_path):
        return False, f"El archivo temporal no existe: {temp_file_path}", None
        
    cfg = get_config()
    base_path = cfg["storage"]["base_path"]
    
    # Determine folder
    category = determine_category(temp_file_path, user_selected_category)
    filename = os.path.basename(temp_file_path)
    clean_name = sanitize_filename(filename)

    # 1. Rclone Direct Upload Support (For cloud hosting without FUSE mount)
    if base_path.startswith("rclone:"):
        remote_base = base_path[7:]  # Remove "rclone:" prefix
        if category:
            remote_dest = f"{remote_base}/{category}"
        else:
            remote_dest = remote_base
            
        print(f"Subiendo vía rclone CLI a: {remote_dest}/{clean_name}...")
        
        # Use local rclone binary if present, otherwise fall back to system rclone
        rclone_bin = "rclone"
        if os.path.exists("./rclone"):
            rclone_bin = "./rclone"
            try:
                # Ensure it has execute permissions on Linux
                os.chmod("./rclone", 0o755)
            except Exception as chmod_err:
                print(f"No se pudo hacer chmod a ./rclone: {chmod_err}")
                
        rclone_cmd = [rclone_bin, "move", temp_file_path, remote_dest]
        if os.path.exists("rclone.conf"):
            rclone_cmd += ["--config", "rclone.conf"]
            
        try:
            # Rclone move will copy the file to the remote and delete the local temp file
            subprocess.run(rclone_cmd, capture_output=True, text=True, check=True)
            print(f"Subido con éxito vía rclone CLI.")
            return True, f"{remote_dest}/{clean_name} (Nube)", category
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr or e.stdout or str(e)
            print(f"Error al ejecutar rclone (codigo {e.returncode}): {err_msg}")
            return False, f"Error de rclone (codigo {e.returncode}): {err_msg.strip()}", category
        except Exception as e:
            print(f"Error inesperado al subir con rclone: {e}")
            return False, f"Error inesperado de rclone: {e}", category

    # 2. Local File System Support (PC / Mounted Drive)
    dest_dir = os.path.join(base_path, category)
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except Exception as e:
        return False, f"No se pudo crear el directorio de destino {dest_dir}: {e}", category
        
    dest_file_path = os.path.join(dest_dir, clean_name)
    
    # Handle filename collision
    base_name, ext = os.path.splitext(clean_name)
    counter = 1
    while os.path.exists(dest_file_path):
        dest_file_path = os.path.join(dest_dir, f"{base_name} ({counter}){ext}")
        counter += 1
        
    try:
        # Move file (using shutil.move which handles cross-device moves e.g. from C: temp to G: Drive)
        shutil.move(temp_file_path, dest_file_path)
        print(f"Archivo movido con éxito: {temp_file_path} -> {dest_file_path}")
        return True, dest_file_path, category
    except Exception as e:
        # Fallback to copy and delete if move fails (e.g. permission or locked file)
        try:
            shutil.copy2(temp_file_path, dest_file_path)
            os.remove(temp_file_path)
            print(f"Archivo copiado/borrado con éxito (fallback): {temp_file_path} -> {dest_file_path}")
            return True, dest_file_path, category
        except Exception as copy_err:
            return False, f"Error al mover archivo a {dest_file_path}: {copy_err}", category

def sync_categories_from_drive():
    """
    Scans the base_path directory (either locally or via rclone) for subfolders,
    and automatically registers any new ones as categories in the config.
    """
    try:
        cfg = get_config()
        base_path = cfg["storage"]["base_path"]
        categories = cfg["storage"]["categories"]
        default_folder = cfg["storage"]["default_folder"]
        existing_keys = set(categories.keys())
        
        found_folders = []
        
        if base_path.startswith("rclone:"):
            remote_base = base_path[7:] # Remove "rclone:" prefix
            # Determine rclone binary
            rclone_bin = "rclone"
            if os.path.exists("./rclone"):
                rclone_bin = "./rclone"
            elif os.path.exists("rclone"):
                rclone_bin = "rclone"
                
            rclone_cmd = [rclone_bin, "lsd", remote_base]
            if os.path.exists("rclone.conf"):
                rclone_cmd += ["--config", "rclone.conf"]
                
            try:
                res = subprocess.run(rclone_cmd, capture_output=True, text=True, check=True)
                for line in res.stdout.strip().splitlines():
                    # Format: "          -1 2026-06-24 01:23:45        -1 Pop"
                    parts = line.strip().split(maxsplit=4)
                    if len(parts) >= 5:
                        folder_name = parts[4].strip()
                        if folder_name:
                            found_folders.append(folder_name)
            except Exception as e:
                print(f"Error al ejecutar rclone lsd para sincronizar categorias: {e}")
        else:
            if os.path.exists(base_path):
                try:
                    for entry in os.listdir(base_path):
                        entry_path = os.path.join(base_path, entry)
                        if os.path.isdir(entry_path):
                            found_folders.append(entry)
                except Exception as e:
                    print(f"Error al listar base_path local para sincronizar categorias: {e}")
                    
        # Check for new folders
        new_folders = [f for f in found_folders if f not in existing_keys and f != default_folder]
        if new_folders:
            updated_categories = dict(categories)
            for folder in new_folders:
                updated_categories[folder] = []
                
            # Update configuration
            from app.config import update_config
            update_config({
                "storage": {
                    "categories": updated_categories
                }
            })
            print(f"Nuevas categorias sincronizadas desde almacenamiento: {new_folders}")
            return new_folders
    except Exception as ex:
        print(f"Error al sincronizar categorias: {ex}")
    return []

def normalize_song_name(name):
    # Remove extension
    name, _ = os.path.splitext(name)
    name = name.lower().strip()
    # Remove accents/diacritics
    name = "".join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn')
    # Remove non-alphanumeric characters except spaces
    name = re.sub(r'[^a-z0-9\s]', '', name)
    # Clean multiple spaces
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def is_song_duplicate(filename):
    db_file = "downloaded_songs.json"
    if not os.path.exists(db_file):
        return False
    try:
        with open(db_file, "r", encoding="utf-8") as f:
            db = json.load(f)
        normalized_new = normalize_song_name(filename)
        for db_item in db:
            if normalize_song_name(db_item) == normalized_new:
                return True
    except Exception as e:
        print(f"Error checking duplicates: {e}")
    return False

def add_song_to_db(filename):
    db_file = "downloaded_songs.json"
    db = []
    if os.path.exists(db_file):
        try:
            with open(db_file, "r", encoding="utf-8") as f:
                db = json.load(f)
        except Exception as e:
            print(f"Error loading songs db: {e}")
    if filename not in db:
        db.append(filename)
        try:
            with open(db_file, "w", encoding="utf-8") as f:
                json.dump(db, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error updating songs db: {e}")

def scan_existing_files():
    """
    Scans the entire storage directory (locally or via rclone) for music files,
    and populates the downloaded_songs.json database.
    """
    cfg = get_config()
    base_path = cfg["storage"]["base_path"]
    found_files = []
    
    if base_path.startswith("rclone:"):
        remote_base = base_path[7:] # Remove "rclone:" prefix
        rclone_bin = "rclone"
        if os.path.exists("./rclone"):
            rclone_bin = "./rclone"
        elif os.path.exists("rclone"):
            rclone_bin = "rclone"
            
        rclone_cmd = [rclone_bin, "lsf", "-R", "--files-only", remote_base]
        if os.path.exists("rclone.conf"):
            rclone_cmd += ["--config", "rclone.conf"]
            
        try:
            res = subprocess.run(rclone_cmd, capture_output=True, text=True, check=True)
            for line in res.stdout.strip().splitlines():
                filename = os.path.basename(line.strip())
                if filename and filename.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.ogg')):
                    found_files.append(filename)
        except Exception as e:
            print(f"Error scanning rclone drive: {e}")
    else:
        if os.path.exists(base_path):
            try:
                for root, dirs, files in os.walk(base_path):
                    for file in files:
                        if file.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.ogg')):
                            found_files.append(file)
            except Exception as e:
                print(f"Error walking local base_path: {e}")
                
    db_file = "downloaded_songs.json"
    unique_files = list(set(found_files))
    try:
        with open(db_file, "w", encoding="utf-8") as f:
            json.dump(unique_files, f, indent=4, ensure_ascii=False)
        print(f"Biblioteca sincronizada: {len(unique_files)} canciones registradas.")
        return len(unique_files)
    except Exception as e:
        print(f"Error guardando base de datos de canciones: {e}")
        return 0
