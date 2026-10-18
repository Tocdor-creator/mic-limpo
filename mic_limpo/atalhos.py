"""Atalhos do Windows: iniciar com o sistema e ícone na área de trabalho."""

import os
import subprocess

PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHONW = os.path.join(PROJETO, ".venv", "Scripts", "pythonw.exe")
SCRIPT = os.path.join(PROJETO, "iniciar.pyw")
ICONE = os.path.join(PROJETO, "mic_limpo", "icone.ico")
INICIALIZAR = os.path.join(
    os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup", "Mic Limpo.lnk"
)


def _ps(texto):
    return "'" + texto.replace("'", "''") + "'"


def _criar(caminho_ps, argumentos=""):
    args = f'"{SCRIPT}" {argumentos}'.strip()
    comando = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({caminho_ps}); "
        f"$s.TargetPath = {_ps(PYTHONW)}; "
        f"$s.Arguments = {_ps(args)}; "
        f"$s.WorkingDirectory = {_ps(PROJETO)}; "
        f"$s.IconLocation = {_ps(ICONE)}; "
        "$s.Description = 'Mic Limpo: microfone sem ruído e com volume nivelado'; "
        "$s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", comando],
        check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )


def inicia_com_windows():
    return os.path.exists(INICIALIZAR)


def iniciar_com_windows(ativo):
    if ativo:
        _criar(_ps(INICIALIZAR), "--minimizado")
    elif os.path.exists(INICIALIZAR):
        os.remove(INICIALIZAR)


def criar_na_area_de_trabalho():
    _criar("(Join-Path ([Environment]::GetFolderPath('Desktop')) 'Mic Limpo.lnk')")


if __name__ == "__main__":
    criar_na_area_de_trabalho()
    print("Atalho criado na área de trabalho.")
