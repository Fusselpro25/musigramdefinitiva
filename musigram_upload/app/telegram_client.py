import os
import asyncio
import time
import uuid
from telethon import TelegramClient, events, types
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
from app.config import get_config
from app.classifier import classify_and_move, is_song_duplicate, add_song_to_db

# Global list of downloads
downloads = []
# Callback to notify FastAPI about updates
broadcast_callback = None

# Custom exception for user cancellations
class DownloadCancelled(Exception):
    pass

# Set of download IDs requested to cancel
cancelled_downloads = set()


class TelegramManager:
    def __init__(self):
        self.client = None
        self.phone_code_hash = None
        self.phone = None
        self.is_connecting = False
        
    async def get_client(self):
        if self.client:
            return self.client
            
        cfg = get_config()
        api_id = cfg["telegram"]["api_id"]
        api_hash = cfg["telegram"]["api_hash"]
        
        if not api_id or not api_hash:
            return None
            
        self.client = TelegramClient('telegram_user_session', int(api_id), api_hash)
        return self.client

    async def init_client(self):
        client = await self.get_client()
        if not client:
            return False
            
        try:
            if not client.is_connected():
                await client.connect()
                
            if await client.is_user_authorized():
                self.register_handlers()
                return True
        except Exception as e:
            print(f"Error inicializando cliente de Telegram: {e}")
        return False

    def register_handlers(self):
        if not self.client:
            return
            
        # Remove existing handlers to avoid duplicates
        self.client.remove_event_handler(self.handle_new_message)
        
        cfg = get_config()
        bot_username = cfg["telegram"]["bot_username"]
        if not bot_username:
            print("Bot de música no configurado, no se registra el manejador.")
            return
            
        clean_bot = bot_username.lstrip('@')
        
        @self.client.on(events.NewMessage(chats=clean_bot))
        async def handle_incoming(event):
            await self.handle_new_message(event)
            
        print(f"Manejador registrado correctamente para el bot: @{clean_bot}")

    async def handle_new_message(self, event):
        message = event.message
        if not message:
            return
            
        is_audio = False
        filename = "unknown_song.mp3"
        size = 0
        
        if message.file:
            mime = message.file.mime_type or ""
            ext = (message.file.ext or "").lower()
            # Accept audio MIME types or typical audio file extensions
            if mime.startswith("audio/") or ext in ['.mp3', '.m4a', '.flac', '.wav', '.ogg']:
                is_audio = True
                filename = message.file.name or f"cancion_{int(time.time())}{ext}"
                size = message.file.size or 0
                
        if not is_audio:
            # We ignore non-audio messages (e.g. search listings, buttons, text instructions)
            return

        # Check if song is a duplicate
        if is_song_duplicate(filename):
            download_id = str(uuid.uuid4())
            download_item = {
                "id": download_id,
                "filename": filename,
                "size": size,
                "progress": 100,
                "status": "skipped",
                "error": "Canción duplicada (ya existe en la biblioteca).",
                "category": "Duplicado",
                "destination": "",
                "timestamp": time.strftime("%H:%M:%S")
            }
            # Link this download with the most recent 'requested' item if applicable
            for dl in list(downloads):
                if dl["status"] == "requested":
                    download_item["id"] = dl["id"]
                    download_item["timestamp"] = dl["timestamp"]
                    downloads.remove(dl)
                    break
            downloads.insert(0, download_item)
            if broadcast_callback:
                await broadcast_callback()
            print(f"Omitiendo descarga duplicada: {filename}")
            return

        download_id = str(uuid.uuid4())
        download_item = {
            "id": download_id,
            "filename": filename,
            "size": size,
            "progress": 0,
            "status": "downloading",
            "error": "",
            "category": "Detectando...",
            "destination": "",
            "timestamp": time.strftime("%H:%M:%S")
        }
        
        # Link this download with the most recent 'requested' item if applicable
        selected_category = None
        for dl in list(downloads):
            if dl["status"] == "requested":
                selected_category = dl["category"]
                download_item["id"] = dl["id"]
                download_item["timestamp"] = dl["timestamp"]
                downloads.remove(dl)
                break
        
        downloads.insert(0, download_item)
        if broadcast_callback:
            await broadcast_callback()
            
        temp_dir = "temp_downloads"
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, filename)
        
        last_pct = -1
        async def progress_update(received, total):
            nonlocal last_pct
            if download_item["id"] in cancelled_downloads:
                raise DownloadCancelled("Descarga cancelada por el usuario")
            if not total:
                return
            pct = int(received * 100 / total)
            if pct != last_pct:
                last_pct = pct
                download_item["progress"] = pct
                if broadcast_callback:
                    await broadcast_callback()
                    
        try:
            print(f"Descargando archivo: {filename} ({size} bytes)...")
            await message.download_media(file=temp_path, progress_callback=progress_update)
            
            # Check for cancellation right after download before classifying
            if download_item["id"] in cancelled_downloads:
                raise DownloadCancelled("Descarga cancelada por el usuario")
                
            download_item["status"] = "classifying"
            download_item["progress"] = 100
            if broadcast_callback:
                await broadcast_callback()
                
            loop = asyncio.get_event_loop()
            success, dest_path, category = await loop.run_in_executor(
                None, classify_and_move, temp_path, selected_category
            )
            
            if success:
                download_item["status"] = "completed"
                download_item["destination"] = dest_path
                download_item["category"] = category
                add_song_to_db(filename)
            else:
                download_item["status"] = "failed"
                download_item["error"] = dest_path
                download_item["category"] = category or "Desconocido"
                
        except DownloadCancelled:
            download_item["status"] = "cancelled"
            download_item["error"] = "Descarga cancelada por el usuario."
            print(f"Descarga cancelada por el usuario: {filename}")
            if download_item["id"] in cancelled_downloads:
                try:
                    cancelled_downloads.remove(download_item["id"])
                except KeyError:
                    pass
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
        except Exception as e:
            if download_item["id"] in cancelled_downloads:
                download_item["status"] = "cancelled"
                download_item["error"] = "Descarga cancelada por el usuario."
                try:
                    cancelled_downloads.remove(download_item["id"])
                except KeyError:
                    pass
            else:
                download_item["status"] = "failed"
                download_item["error"] = str(e)
            print(f"Error al descargar {filename}: {e}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
                    
        if broadcast_callback:
            await broadcast_callback()

    async def send_code(self, phone):
        client = await self.get_client()
        if not client:
            return {"status": "error", "message": "Telegram API ID y Hash no configurados."}
            
        try:
            if not client.is_connected():
                await client.connect()
                
            self.phone = phone
            sent_code = await client.send_code_request(phone)
            self.phone_code_hash = sent_code.phone_code_hash
            return {"status": "code_sent"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def verify_code(self, code):
        client = await self.get_client()
        if not client or not self.phone or not self.phone_code_hash:
            return {"status": "error", "message": "Flujo de inicio de sesión no válido o incompleto."}
            
        try:
            await client.sign_in(self.phone, code, phone_code_hash=self.phone_code_hash)
            self.register_handlers()
            return {"status": "authorized"}
        except SessionPasswordNeededError:
            return {"status": "password_required"}
        except (PhoneCodeInvalidError, PhoneCodeExpiredError):
            return {"status": "error", "message": "Código de verificación no válido o expirado."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def verify_password(self, password):
        client = await self.get_client()
        if not client:
            return {"status": "error", "message": "Cliente no iniciado."}
            
        try:
            await client.sign_in(password=password)
            self.register_handlers()
            return {"status": "authorized"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def send_request_to_bot(self, request_text, category="Automático"):
        client = await self.get_client()
        if not client or not await client.is_user_authorized():
            return False, "Cliente de Telegram no autorizado. Por favor inicia sesión."
            
        cfg = get_config()
        bot_username = cfg["telegram"]["bot_username"]
        if not bot_username:
            return False, "Bot de Telegram no configurado."
            
        download_id = str(uuid.uuid4())
        downloads.insert(0, {
            "id": download_id,
            "filename": f"Solicitado: {request_text}",
            "size": 0,
            "progress": 0,
            "status": "requested",
            "error": "",
            "category": category,
            "destination": "",
            "timestamp": time.strftime("%H:%M:%S")
        })
        
        if broadcast_callback:
            await broadcast_callback()
            
        try:
            clean_bot = bot_username.lstrip('@')
            await client.send_message(clean_bot, request_text)
            return True, "Petición enviada al bot."
        except Exception as e:
            # Update item status to failed
            for dl in downloads:
                if dl["id"] == download_id:
                    dl["status"] = "failed"
                    dl["error"] = str(e)
                    break
            if broadcast_callback:
                await broadcast_callback()
            return False, f"Error al enviar mensaje: {e}"

    async def cancel_download(self, download_id):
        # Find the download item
        item = None
        for dl in downloads:
            if dl["id"] == download_id:
                item = dl
                break
                
        if not item:
            return False, "Descarga no encontrada."
            
        if item["status"] == "completed":
            return False, "La descarga ya está completada."
            
        if item["status"] == "cancelled":
            return True, "La descarga ya estaba cancelada."
            
        if item["status"] == "requested":
            item["status"] = "cancelled"
            item["error"] = "Cancelado por el usuario."
            if broadcast_callback:
                await broadcast_callback()
            return True, "Petición cancelada."
            
        if item["status"] in ["downloading", "classifying"]:
            cancelled_downloads.add(download_id)
            item["status"] = "cancelled"
            item["error"] = "Cancelando..."
            if broadcast_callback:
                await broadcast_callback()
            return True, "Descarga en proceso de cancelación."
            
        return False, f"No se puede cancelar en el estado actual ({item['status']})."

    async def check_status(self):
        client = await self.get_client()
        if not client:
            return "unconfigured"
        try:
            if not client.is_connected():
                await client.connect()
            if await client.is_user_authorized():
                return "authorized"
            return "connected"
        except Exception as e:
            print(f"Error comprobando estado de Telegram: {e}")
            return "disconnected"

telegram_manager = TelegramManager()
