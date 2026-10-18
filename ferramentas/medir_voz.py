"""Espera você começar a falar e mede 12 s do microfone e do CABLE Output juntos.

Mostra, a cada 100 ms, quanto chegou no mic e quanto passou para o Discord.
Nada é gravado em disco.
    .venv\\Scripts\\python ferramentas\\medir_voz.py [segundos_de_espera]
"""

import os
import sys
import threading
import time

import numpy as np
import sounddevice as sd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mic_limpo import dispositivos  # noqa: E402

TAXA = 48000
BLOCO = TAXA // 10
ESPERA = float(sys.argv[1]) if len(sys.argv) > 1 else 240
MEDIR = 12
GATILHO_DB = -50  # 3 blocos seguidos acima disso = começou a falar

W = sd.WasapiSettings(auto_convert=True)
mic = dispositivos.microfone_sugerido()
blocos = {"mic": [], "cabo": []}
gravando = threading.Event()
fim = threading.Event()


def db(x):
    return 10 * np.log10(float(np.mean(x * x)) + 1e-12)


def ler(nome, chave):
    with sd.InputStream(device=dispositivos.indice(nome, "entrada"), samplerate=TAXA, channels=1,
                        dtype="float32", blocksize=BLOCO, extra_settings=W) as s:
        seguidos = 0
        while not fim.is_set():
            x, _ = s.read(BLOCO)
            nivel = db(x[:, 0])
            if chave == "mic" and not gravando.is_set():
                seguidos = seguidos + 1 if nivel > GATILHO_DB else 0
                if seguidos >= 3:
                    gravando.set()
            if gravando.is_set():
                blocos[chave].append(nivel)


threads = [threading.Thread(target=ler, args=(mic, "mic"), daemon=True),
           threading.Thread(target=ler, args=("CABLE Output (VB-Audio Virtual Cable)", "cabo"), daemon=True)]
for t in threads:
    t.start()
print(f"Esperando você falar no {mic} (até {ESPERA:.0f} s)...", flush=True)
if not gravando.wait(ESPERA):
    fim.set()
    print("Ninguém falou no tempo de espera.")
    sys.exit(1)
time.sleep(MEDIR)
fim.set()
for t in threads:
    t.join(timeout=2)


def barra(v):
    return "█" if v > -30 else "▆" if v > -40 else "▃" if v > -55 else "·"


print("cada caractere = 100 ms   █ forte (>-30)  ▆ voz (>-40)  ▃ baixo (>-55)  · silêncio")
for chave in ("mic", "cabo"):
    v = np.array(blocos[chave])
    fala = v[v > -55]
    print(f"{chave:5}", "".join(barra(x) for x in v))
    media = 10 * np.log10(np.mean(10 ** (fala / 10))) if len(fala) else float("nan")
    print(f"      com som {len(fala) / max(len(v), 1) * 100:.0f}% do tempo | média da voz {media:.1f} dB | "
          f"máximo {v.max():.1f} dB | silêncio {np.median(v[v <= -55]) if (v <= -55).any() else float('nan'):.0f} dB")
