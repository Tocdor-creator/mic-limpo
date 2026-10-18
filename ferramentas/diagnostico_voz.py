"""Espera você falar, guarda 12 s do microfone só na memória e passa pelo
Processador com a sua config, mostrando a cada 100 ms: nível do mic,
probabilidade de voz do RNNoise, se o silenciador abriu e o nível de saída.
    .venv\\Scripts\\python ferramentas\\diagnostico_voz.py [segundos_de_espera]
"""

import os
import sys

import numpy as np
import sounddevice as sd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mic_limpo import config, dispositivos  # noqa: E402
from mic_limpo.processador import QUADRO, TAXA, Processador, limiar_da_sensibilidade, rms_db  # noqa: E402

ESPERA = float(sys.argv[1]) if len(sys.argv) > 1 else 240
MEDIR = 12
BLOCO = TAXA // 10

cfg = config.carregar()
mic = cfg.entrada or dispositivos.microfone_sugerido()
print(f"Esperando você falar no {mic} (até {ESPERA:.0f} s)...", flush=True)
with sd.InputStream(device=dispositivos.indice(mic, "entrada"), samplerate=TAXA, channels=1, dtype="float32",
                    blocksize=BLOCO, extra_settings=sd.WasapiSettings(auto_convert=True)) as s:
    seguidos, esperado = 0, 0.0
    antes = []
    while seguidos < 3:
        x, _ = s.read(BLOCO)
        antes = (antes + [x[:, 0].copy()])[-10:]  # guarda 1 s antes do gatilho
        seguidos = seguidos + 1 if rms_db(x[:, 0]) > -50 else 0
        esperado += 0.1
        if esperado > ESPERA:
            print("Ninguém falou no tempo de espera.")
            sys.exit(1)
    resto, _ = s.read(TAXA * MEDIR)
audio = np.concatenate(antes + [resto[:, 0]]).astype(np.float32)

limiar = limiar_da_sensibilidade(cfg.sensibilidade)
p = Processador(cfg)
linhas = []
for i in range(0, len(audio) // BLOCO * BLOCO, BLOCO):
    probs, abertos, saidas = [], [], []
    for j in range(i, i + BLOCO, QUADRO):
        y = p.processar(audio[j:j + QUADRO].copy())
        probs.append(p.prob_voz)
        abertos.append(p.falando)
        saidas.append(y)
    linhas.append((rms_db(audio[i:i + BLOCO]), max(probs), np.mean(abertos), p.ganho_db, rms_db(np.concatenate(saidas))))
p.fechar()

print(f"limiar de voz (sensibilidade {cfg.sensibilidade:.0f}%): {limiar:.2f}")
print("  mic dB | voz% máx | aberto | ganho | saída dB")
for mic_db, prob, aberto, ganho, out_db in linhas:
    if mic_db > -58 or aberto > 0:
        print(f"  {mic_db:6.1f} | {prob * 100:7.0f}% | {aberto * 100:5.0f}% | {ganho:+5.1f} | {out_db:7.1f}")
v = np.array(linhas)
com_som = v[:, 0] > -55
print(f"\nblocos com som no mic: {com_som.sum()} | desses, com voz reconhecida (≥ limiar): "
      f"{(v[com_som, 1] >= limiar).sum()} | prob. de voz mediana nesses blocos: {np.median(v[com_som, 1]) * 100 if com_som.any() else 0:.0f}%")
