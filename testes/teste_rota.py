"""Teste de ponta a ponta: liga o motor (mic real -> CABLE Input) e grava o
CABLE Output por alguns segundos para conferir se o som chega do outro lado.
Nada é salvo; só mede níveis.

Rodar com: .venv\\Scripts\\python.exe testes\\teste_rota.py
"""

import os
import sys
import time

import numpy as np
import sounddevice as sd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mic_limpo import dispositivos  # noqa: E402
from mic_limpo.config import Config  # noqa: E402
from mic_limpo.motor import Motor  # noqa: E402
from mic_limpo.processador import TAXA, rms_db  # noqa: E402

SEGUNDOS = 4

# Sem efeitos que zeram o silêncio, para o chiado de fundo do mic passar e dar para medir
cfg = Config(remover_ruido=False, silenciar_pausas=False, nivelar=False, ganho_manual_db=0)
motor = Motor(cfg)
motor.ligar()
print("microfone:", motor.entrada_nome, "| saída:", dispositivos.cabo_sugerido())
print("atraso estimado:", motor.latencia_ms(), "ms")

idx = dispositivos.indice("CABLE Output (VB-Audio Virtual Cable)", "entrada")
entradas_db = []
with sd.InputStream(device=idx, samplerate=TAXA, channels=1, dtype="float32",
                    extra_settings=sd.WasapiSettings(auto_convert=True)) as gravador:
    gravado = []
    fim = time.monotonic() + SEGUNDOS
    while time.monotonic() < fim:
        bloco, _ = gravador.read(TAXA // 10)
        gravado.append(bloco[:, 0].copy())
        entradas_db.append(motor.proc.entrada_db)

saudavel = motor.saudavel()
faltas, descartes = motor._cabo.faltas, motor._cabo.descartes
motor.desligar()

gravado = np.concatenate(gravado)[TAXA // 2:]  # ignora o primeiro meio segundo
nivel_mic = float(np.median(entradas_db))
nivel_cabo = rms_db(gravado)
print(f"nível no microfone: {nivel_mic:.1f} dB  |  nível chegando no CABLE Output: {nivel_cabo:.1f} dB")
print(f"faltas: {faltas}  descartes: {descartes}  motor saudável: {saudavel}  erro: {motor.erro}")
ok = saudavel and nivel_cabo > -100 and abs(nivel_cabo - nivel_mic) < 6
print("ROTA OK" if ok else "ROTA COM PROBLEMA")
sys.exit(0 if ok else 1)
