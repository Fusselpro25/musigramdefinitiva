import os
import sys
import subprocess

def run_cmd(args):
    try:
        subprocess.run(args, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"\nError al ejecutar: {' '.join(args)}. Código de salida: {e.returncode}")
        return False

def main():
    print("====================================================")
    print("   Iniciador del Descargador de Música de Telegram   ")
    print("====================================================")
    print()

    # 1. Check if .venv exists
    venv_dir = ".venv"
    if not os.path.exists(venv_dir):
        print("Creando el entorno virtual de Python (.venv)...")
        # Use current Python executable to create venv
        if not run_cmd([sys.executable, "-m", "venv", venv_dir]):
            print("ERROR: No se pudo crear el entorno virtual. Verifica tu instalación de Python.")
            input("Presiona Enter para salir...")
            sys.exit(1)

    # 2. Get path to virtual environment python and pip
    if sys.platform == "win32":
        venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
        venv_pip = os.path.join(venv_dir, "Scripts", "pip.exe")
    else:
        venv_python = os.path.join(venv_dir, "bin", "python")
        venv_pip = os.path.join(venv_dir, "bin", "pip")

    # 3. Upgrade pip and install requirements
    print("Actualizando pip en el entorno virtual...")
    run_cmd([venv_python, "-m", "pip", "install", "--upgrade", "pip"])

    print("Verificando e instalar dependencias (requirements.txt)...")
    if not run_cmd([venv_python, "-m", "pip", "install", "-r", "requirements.txt"]):
        print("ERROR: No se pudieron instalar las dependencias.")
        input("Presiona Enter para salir...")
        sys.exit(1)

    print()
    print("====================================================")
    print("   Iniciando el Servidor Web en http://localhost:8000")
    print("   Puedes acceder desde tu móvil usando la IP de tu PC")
    print("====================================================")
    print()

    # 4. Start uvicorn server
    try:
        subprocess.run([venv_python, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"])
    except KeyboardInterrupt:
        print("\nServidor detenido por el usuario.")

if __name__ == "__main__":
    main()
