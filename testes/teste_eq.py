"""Confere o EQ: o áudio filtrado tem que bater com a curva desenhada.

Rodar com: .venv\\Scripts\\python.exe testes\\teste_eq.py
"""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mic_limpo.eq import TAXA, Equalizador, bandas_padrao, resposta_db  # noqa: E402

falhas = []


def conferir(nome, ok, detalhe):
    print(f"[{'OK ' if ok else 'FALHOU'}] {nome}: {detalhe}")
    if not ok:
        falhas.append(nome)


def ganho_medido(bandas, freq):
    eq = Equalizador(bandas)
    t = np.arange(TAXA) / TAXA
    x = (0.1 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    y = np.concatenate([eq.processar(x[i:i + 480]) for i in range(0, len(x), 480)])
    return 20 * np.log10(np.std(y[TAXA // 2:]) / np.std(x[TAXA // 2:]))


bandas = bandas_padrao()
bandas[0]["freq"] = 20.0
conferir("plano não muda o som", abs(ganho_medido(bandas, 1000)) < 0.3, f"{ganho_medido(bandas, 1000):+.2f} dB em 1 kHz")

bandas = bandas_padrao()
bandas[2].update(freq=1000.0, ganho=10.0)
teorico = resposta_db(bandas, [1000])[0]
medido = ganho_medido(bandas, 1000)
conferir("médio +10 dB em 1 kHz", abs(medido - teorico) < 0.5, f"curva {teorico:+.1f} dB, áudio {medido:+.1f} dB")

for freq in (60, 200, 3000, 12000):
    bandas = bandas_padrao()
    bandas[1]["ganho"], bandas[3]["ganho"], bandas[4]["ganho"] = 6.0, -8.0, 5.0
    teorico = resposta_db(bandas, [freq])[0]
    medido = ganho_medido(bandas, freq)
    conferir(f"curva = áudio em {freq} Hz", abs(medido - teorico) < 1.0, f"curva {teorico:+.1f} dB, áudio {medido:+.1f} dB")

bandas = bandas_padrao()
conferir("corte de 80 Hz tira ronco de 30 Hz", ganho_medido(bandas, 30) < -12, f"{ganho_medido(bandas, 30):+.1f} dB em 30 Hz")

# Atraso: pico da resposta ao impulso com uma banda de presença
bandas = bandas_padrao()
bandas[3]["ganho"] = 6.0
eq = Equalizador(bandas)
impulso = np.zeros(4800, dtype=np.float32)
impulso[0] = 1
resp = np.concatenate([eq.processar(impulso[i:i + 480]) for i in range(0, 4800, 480)])
atraso_ms = np.argmax(np.abs(resp)) / TAXA * 1000
conferir("quase sem atraso (fase mínima)", atraso_ms < 1.5, f"pico da resposta em {atraso_ms:.2f} ms")

eq = Equalizador(bandas_padrao())
x = np.random.default_rng(0).standard_normal(480).astype(np.float32)
inicio = time.perf_counter()
for _ in range(1000):
    eq.processar(x)
gasto = (time.perf_counter() - inicio)
conferir("rápido", gasto < 0.5, f"{gasto:.3f} ms por quadro de 10 ms")

inicio = time.perf_counter()
eq.atualizar(bandas)
conferir("recalcular ao arrastar é rápido", time.perf_counter() - inicio < 0.05,
         f"{(time.perf_counter() - inicio) * 1000:.1f} ms para recalcular o filtro")

print()
print("TUDO CERTO" if not falhas else f"{len(falhas)} falha(s): {', '.join(falhas)}")
sys.exit(1 if falhas else 0)
