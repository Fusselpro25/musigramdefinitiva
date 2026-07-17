import os
import asyncio
import time
# pyrefly: ignore [missing-import]
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header, Depends, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from app.config import get_config, update_config, init_folders
from app.telegram_client import telegram_manager, downloads
import app.telegram_client as tc

app = FastAPI(title="Telegram Music Downloader")

# Websocket connections manager
class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                dead_connections.append(connection)
        for dead in dead_connections:
            self.disconnect(dead)

manager = ConnectionManager()

# Hook the telegram client updates to our websocket broadcast
async def send_ws_update():
    await manager.broadcast({
        "type": "downloads_update",
        "downloads": downloads
    })

tc.broadcast_callback = send_ws_update

# Pydantic models for API request validation
class LoginRequest(BaseModel):
    username: str
    password: str

async def check_admin_auth(authorization: str = Header(None)):
    from app.config import verify_admin_token
    if not verify_admin_token(authorization):
        raise HTTPException(status_code=401, detail="No autorizado. Inicie sesión para acceder a los ajustes.")

class SetupRequest(BaseModel):
    api_id: str
    api_hash: str
    phone: str
    bot_username: str

class VerifyRequest(BaseModel):
    code: str

class PasswordRequest(BaseModel):
    password: str

class DownloadRequest(BaseModel):
    request_text: str
    category: str = "Automático"

class ConfigUpdateRequest(BaseModel):
    base_path: str
    bot_username: str
    categories: dict

class CancelRequest(BaseModel):
    download_id: str

class RcloneConfigRequest(BaseModel):
    content: str


# Startup event
@app.on_event("startup")
async def startup_event():
    # 1. Initialize folders
    created, failed = init_folders()
    print(f"Directorios inicializados. Creados: {len(created)}, Fallidos: {len(failed)}")
    
    # 2. Try to connect Telegram client if credentials exist
    asyncio.create_task(telegram_manager.init_client())
    
    # 3. Synchronize categories and existing files from drive on startup
    from app.classifier import sync_categories_from_drive, scan_existing_files
    asyncio.create_task(asyncio.to_thread(sync_categories_from_drive))
    asyncio.create_task(asyncio.to_thread(scan_existing_files))

# Routes
last_sync_time = 0

@app.get("/api/status")
async def get_status():
    global last_sync_time
    now = time.time()
    if now - last_sync_time > 30:
        last_sync_time = now
        from app.classifier import sync_categories_from_drive
        asyncio.create_task(asyncio.to_thread(sync_categories_from_drive))
        
    tg_status = await telegram_manager.check_status()
    cfg = get_config()
    
    # Check if Google Drive path exists (or if using rclone)
    base_path = cfg["storage"]["base_path"]
    if base_path.startswith("rclone:"):
        drive_exists = True  # rclone mode, assume connected
    else:
        drive_exists = os.path.exists(base_path)
    
    return {
        "telegram_status": tg_status,
        "bot_username": cfg["telegram"]["bot_username"],
        "drive_path": cfg["storage"]["base_path"],
        "drive_status": "connected" if drive_exists else "disconnected",
        "categories": list(cfg["storage"]["categories"].keys()) + [cfg["storage"]["default_folder"]],
        "downloads_count": len(downloads)
    }

@app.post("/api/login")
async def admin_login(req: LoginRequest):
    cfg = get_config()
    admin = cfg.get("admin", {"username": "admin", "password": "admin"})
    if req.username == admin.get("username") and req.password == admin.get("password"):
        from app.config import get_admin_token
        return {"status": "success", "token": get_admin_token()}
    raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

@app.post("/api/setup", dependencies=[Depends(check_admin_auth)])
async def setup_telegram(req: SetupRequest):
    # Save the configs
    update_config({
        "telegram": {
            "api_id": req.api_id.strip(),
            "api_hash": req.api_hash.strip(),
            "phone": req.phone.strip(),
            "bot_username": req.bot_username.strip()
        }
    })
    
    # Reinitialize client and send code
    res = await telegram_manager.send_code(req.phone.strip())
    return res

@app.post("/api/verify", dependencies=[Depends(check_admin_auth)])
async def verify_code(req: VerifyRequest):
    res = await telegram_manager.verify_code(req.code.strip())
    return res

@app.post("/api/verify-password", dependencies=[Depends(check_admin_auth)])
async def verify_password(req: PasswordRequest):
    res = await telegram_manager.verify_password(req.password.strip())
    return res

def process_playlist_download(playlist_url: str, category: str, loop):
    import yt_dlp
    import time
    
    ydl_opts = {
        'extract_flat': True,
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            if not info:
                print(f"No se pudo extraer informacion de la playlist: {playlist_url}")
                return
            
            entries = info.get('entries', [])
            print(f"Playlist extraida: {len(entries)} canciones encontradas.")
            
            for entry in entries:
                if not entry:
                    continue
                
                # Get URL
                video_id = entry.get('id')
                url_val = entry.get('url')
                if url_val and not url_val.startswith('http'):
                    url_val = f"https://www.youtube.com/watch?v={url_val}"
                elif not url_val and video_id:
                    url_val = f"https://www.youtube.com/watch?v={video_id}"
                
                title = entry.get('title') or "Video sin titulo"
                
                if url_val:
                    print(f"Encolando desde playlist: {title} ({url_val})")
                    asyncio.run_coroutine_threadsafe(
                        telegram_manager.send_request_to_bot(url_val, category),
                        loop
                    )
                    # Delay to avoid rate limit
                    time.sleep(2.5)
    except Exception as e:
        print(f"Error procesando playlist: {e}")

@app.post("/api/download")
async def request_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    # Check if client is authorized
    status = await telegram_manager.check_status()
    if status != "authorized":
        raise HTTPException(status_code=400, detail="El cliente de Telegram no está autorizado. Inicia sesión en la pestaña de ajustes.")
        
    if not req.request_text.strip():
        raise HTTPException(status_code=400, detail="La solicitud no puede estar vacía.")
        
    request_text = req.request_text.strip()
    
    # Check if this is a YouTube playlist link
    if "youtube.com/playlist" in request_text or "youtu.be/playlist" in request_text:
        loop = asyncio.get_running_loop()
        background_tasks.add_task(process_playlist_download, request_text, req.category, loop)
        return {"status": "success", "message": "Enlace de lista de reproducción de YouTube detectado. Las canciones se irán encolando en segundo plano."}
        
    success, msg = await telegram_manager.send_request_to_bot(request_text, req.category)
    if not success:
        raise HTTPException(status_code=500, detail=msg)
        
    return {"status": "success", "message": msg}

@app.post("/api/library/sync", dependencies=[Depends(check_admin_auth)])
async def sync_library():
    from app.classifier import scan_existing_files
    count = await asyncio.to_thread(scan_existing_files)
    return {"status": "success", "message": f"Biblioteca sincronizada con éxito. {count} canciones registradas.", "count": count}

@app.get("/api/config", dependencies=[Depends(check_admin_auth)])
async def get_current_config():
    cfg = get_config()
    # Mask API credentials for security
    api_id = cfg["telegram"]["api_id"]
    api_hash = cfg["telegram"]["api_hash"]
    
    masked_config = {
        "telegram": {
            "api_id": api_id,
            "api_hash": "*" * len(api_hash) if api_hash else "",
            "phone": cfg["telegram"]["phone"],
            "bot_username": cfg["telegram"]["bot_username"]
        },
        "storage": cfg["storage"]
    }
    return masked_config

@app.post("/api/config", dependencies=[Depends(check_admin_auth)])
async def update_current_config(req: ConfigUpdateRequest):
    # Verify categories dictionary structure
    if not isinstance(req.categories, dict):
        raise HTTPException(status_code=400, detail="Formato de categorías no válido.")
        
    # Get current config
    cfg = get_config()
    
    # Update config.json (preserving current API secrets if not changed/masked in UI)
    update_data = {
        "storage": {
            "base_path": req.base_path.strip(),
            "default_folder": cfg["storage"].get("default_folder", "General"),
            "categories": req.categories
        },
        "telegram": {
            "bot_username": req.bot_username.strip()
        }
    }
    
    update_config(update_data)
    
    # Create/Verify new directories
    init_folders()
    
    # Re-register telegram listener in case bot username changed
    tg_status = await telegram_manager.check_status()
    if tg_status == "authorized":
        telegram_manager.register_handlers()
        
    return {"status": "success", "message": "Configuración actualizada correctamente y carpetas creadas."}

@app.post("/api/downloads/clear")
async def clear_downloads():
    # Keep only in-progress/downloading items
    to_keep = [dl for dl in downloads if dl["status"] in ["downloading", "classifying", "requested"]]
    downloads.clear()
    downloads.extend(to_keep)
    await send_ws_update()
    return {"status": "success", "message": "Descargas finalizadas borradas de la lista."}

@app.post("/api/downloads/cancel")
async def cancel_download(req: CancelRequest):
    success, msg = await telegram_manager.cancel_download(req.download_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "success", "message": msg}

@app.get("/api/config/rclone", dependencies=[Depends(check_admin_auth)])
async def get_rclone_config():
    if os.path.exists("rclone.conf"):
        try:
            with open("rclone.conf", "r", encoding="utf-8") as f:
                return {"status": "success", "content": f.read()}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"No se pudo leer rclone.conf: {e}")
    return {"status": "success", "content": ""}

@app.post("/api/config/rclone", dependencies=[Depends(check_admin_auth)])
async def update_rclone_config(req: RcloneConfigRequest):
    try:
        with open("rclone.conf", "w", encoding="utf-8") as f:
            f.write(req.content)
        return {"status": "success", "message": "Configuración de rclone.conf guardada correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo escribir rclone.conf: {e}")

# WebSockets endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Immediately push current downloads
        await websocket.send_json({
            "type": "downloads_update",
            "downloads": downloads
        })
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Serve static directory
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get_index():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return HTMLResponse("<h1>Servidor de Música de Telegram Iniciado.</h1><p>Coloque la interfaz web en la carpeta 'static/index.html'.</p>")
