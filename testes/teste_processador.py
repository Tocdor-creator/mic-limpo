"""Teste sem microfone: sinal sintético passando pelo Processador.

Rodar com: .venv\\Scripts\\python.exe testes\\teste_processador.py
"""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mic_limpo.config import Config  # noqa: E402
from mic_limpo.processador import QUADRO, TAXA, Processador, curva_dinamica, rms_db  # noqa: E402

rng = np.random.default_rng(1)


def voz(segundos, nivel_db):
    """Tom com harmônicos modulado a 4 Hz (sílabas), normalizado para nivel_db RMS."""
    t = np.arange(int(segundos * TAXA)) / TAXA
    s = sum(np.sin(2 * np.pi * 150 * k * t) / k for k in range(1, 8))
    s *= 0.55 + 0.45 * np.sin(2 * np.pi * 4 * t)
    s /= np.sqrt(np.mean(s ** 2))
    return (s * 10 ** (nivel_db / 20)).astype(np.float32)


def ruido(segundos, nivel_db):
    return (rng.standard_normal(int(segundos * TAXA)) * 10 ** (nivel_db / 20)).astype(np.float32)


def rodar(proc, sinal, prob):
    saida = np.empty_like(sinal)
    for i in range(0, len(sinal), QUADRO):
        saida[i:i + QUADRO] = proc.processar(sinal[i:i + QUADRO].copy(), prob_forcada=prob)
    return saida


def ultimo_segundo_db(x):
    return rms_db(x[-TAXA:])


falhas = []


def conferir(nome, ok, detalhe):
    print(f"[{'OK ' if ok else 'FALHOU'}] {nome}: {detalhe}")
    if not ok:
        falhas.append(nome)


# 1) Nivelador: fala baixa sobe, fala alta desce, silêncio não mexe no ganho
cfg = Config(remover_ruido=False, silenciar_pausas=False, nivelar=True, alvo_db=-24, ganho_max_db=24)
p = Processador(cfg)
baixa = rodar(p, voz(4, -42) + ruido(4, -70), 0.9)
conferir("fala baixa sobe até o alvo", abs(ultimo_segundo_db(baixa) - cfg.alvo_db) < 3,
         f"entrada -42 dB -> saída {ultimo_segundo_db(baixa):.1f} dB (alvo {cfg.alvo_db}), ganho {p.ganho_db:+.1f} dB")
ganho_antes = p.ganho_db
rodar(p, ruido(2, -70), 0.02)
conferir("ganho parado no silêncio", abs(p.ganho_db - ganho_antes) < 0.01,
         f"{ganho_antes:+.2f} -> {p.ganho_db:+.2f} dB")
alta = rodar(p, voz(3, -8), 0.9)
conferir("fala alta desce até o alvo", abs(ultimo_segundo_db(alta) - cfg.alvo_db) < 3,
         f"entrada -8 dB -> saída {ultimo_segundo_db(alta):.1f} dB, ganho {p.ganho_db:+.1f} dB")
conferir("grito sem estourar", float(np.max(np.abs(alta))) <= 0.9,
         f"pico {float(np.max(np.abs(alta))):.3f}")
primeiros_50ms = alta[: TAXA // 20]
conferir("limitador segura o começo do grito", float(np.max(np.abs(primeiros_50ms))) <= 0.9,
         f"pico nos primeiros 50 ms {float(np.max(np.abs(primeiros_50ms))):.3f}")
p.fechar()

# 1b) Voz distante (TV, alguém na sala) não pode fazer o ganho disparar
cfg = Config(remover_ruido=False, silenciar_pausas=False, nivelar=True, alvo_db=-24, ganho_max_db=24)
p = Processador(cfg)
rodar(p, voz(4, -60), 0.9)
conferir("voz distante não aumenta o ganho", p.ganho_db < 1, f"ganho {p.ganho_db:+.1f} dB com voz a -60 dB")
p.fechar()

# 1c) Mic fraco de verdade (voz a -50 dB, como o ME6S mediu) com os padrões chega ao alvo
cfg = Config(remover_ruido=False, silenciar_pausas=False, nivelar=True)
p = Processador(cfg)
fraca = rodar(p, voz(6, -50) + ruido(6, -70), 0.9)
conferir("voz bem baixa (-50 dB) chega ao alvo", abs(ultimo_segundo_db(fraca) - cfg.alvo_db) < 3,
         f"saída {ultimo_segundo_db(fraca):.1f} dB, ganho {p.ganho_db:+.1f} dB (máx {cfg.ganho_max_db:+.0f})")
p.fechar()

# 1d) Começa do ganho aprendido na última vez
p = Processador(Config(ganho_aprendido_db=20))
conferir("começa do ganho aprendido", abs(p.ganho_db - 20) < 0.01, f"ganho inicial {p.ganho_db:+.1f} dB")
p.fechar()

# 1e) Compressor: o áudio tem que bater com a curva desenhada no gráfico
cfg = Config(remover_ruido=False, silenciar_pausas=False, nivelar=False, eq_ligado=False,
             comp_ligado=True, comp_limiar_db=-18, comp_razao=3)
p = Processador(cfg)
comprimido = rodar(p, voz(3, -10), 0.9)
esperado = float(curva_dinamica(cfg, [-10])[0])
conferir("compressor segue a curva", abs(ultimo_segundo_db(comprimido) - esperado) < 1.5,
         f"entrada -10 dB -> saída {ultimo_segundo_db(comprimido):.1f} dB (curva diz {esperado:.1f})")
p.fechar()

# 1f) Portão por nível: voz reconhecida mas abaixo do limiar não passa
cfg = Config(remover_ruido=False, silenciar_pausas=True, nivelar=False, eq_ligado=False,
             comp_ligado=False, portao_limiar_db=-30)
p = Processador(cfg)
baixa = rodar(p, voz(2, -40), 0.9)
conferir("voz abaixo do limiar do portão fica muda", ultimo_segundo_db(baixa) < -80,
         f"voz -40 dB com limiar -30 -> {ultimo_segundo_db(baixa):.1f} dB")
alta = rodar(p, voz(2, -20), 0.9)
conferir("voz acima do limiar passa", ultimo_segundo_db(alta) > -25, f"voz -20 dB -> {ultimo_segundo_db(alta):.1f} dB")
p.fechar()

# 1g) Mudo
cfg = Config(mudo=True)
p = Processador(cfg)
muda = rodar(p, voz(1, -20), 0.9)
conferir("mudo zera a saída", float(np.max(np.abs(muda))) == 0.0 and p.din_saida_db > -60,
         f"pico {float(np.max(np.abs(muda)))}, mas medidor interno vê {p.din_saida_db:.1f} dB")
p.fechar()

# 2) Silenciador: abaixa o ruído entre falas
cfg = Config(remover_ruido=False, silenciar_pausas=True, nivelar=False)
p = Processador(cfg)
rodar(p, voz(1, -24), 0.9)
pausa = rodar(p, ruido(2, -45), 0.02)
conferir("pausa silenciada", ultimo_segundo_db(pausa) < -85,
         f"ruído -45 dB -> {ultimo_segundo_db(pausa):.1f} dB")
p.fechar()

# 3) RNNoise de verdade (sem probabilidade forçada) tira chiado constante
cfg = Config(remover_ruido=True, silenciar_pausas=False, nivelar=False)
p = Processador(cfg)
chiado = ruido(3, -40)
saida = np.empty_like(chiado)
inicio = time.perf_counter()
for i in range(0, len(chiado), QUADRO):
    saida[i:i + QUADRO] = p.processar(chiado[i:i + QUADRO].copy())
gasto = (time.perf_counter() - inicio) / (len(chiado) / QUADRO) * 1000
conferir("RNNoise reduz chiado", ultimo_segundo_db(saida) < ultimo_segundo_db(chiado) - 15,
         f"{ultimo_segundo_db(chiado):.1f} dB -> {ultimo_segundo_db(saida):.1f} dB")
conferir("rápido o bastante", gasto < 3, f"{gasto:.2f} ms de CPU por quadro de 10 ms")
conferir("sem NaN", not np.isnan(saida).any(), "ok")
p.fechar()

print()
print("TUDO CERTO" if not falhas else f"{len(falhas)} falha(s): {', '.join(falhas)}")
sys.exit(1 if falhas else 0)
