"""Teste da interface: abre a mesa sem áudio, sem mixer e sem salvar nada,
simula arrastos, cliques e roda do mouse e confere se a config e os outros
controles acompanham.

Rodar com: .venv\\Scripts\\python.exe testes\\teste_janela.py
"""

import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mic_limpo.janela as janela  # noqa: E402
from mic_limpo import config  # noqa: E402

# Isola o teste: config própria, nada é salvo, mixer e microfone não são usados
cfg_teste = config.Config(ligar_ao_abrir=False, mixer_ligado=False)
janela.config.carregar = lambda: cfg_teste
janela.config.salvar = lambda _cfg: None


class SemMixer:
    def __init__(self):
        raise OSError("mixer desligado no teste")


import mic_limpo.mixer  # noqa: E402

mic_limpo.mixer.Mixer = SemMixer

falhas = []


def conferir(nome, ok, detalhe):
    print(f"[{'OK ' if ok else 'FALHOU'}] {nome}: {detalhe}")
    if not ok:
        falhas.append(nome)


raiz = tk.Tk()
raiz.tk.call("tk", "scaling", 96 / 72)
j = janela.Janela(raiz)
raiz.update()
c = j.c


def arrastar(x1, y1, x2, y2, passos=6):
    c.event_generate("<Motion>", x=x1, y=y1)
    c.event_generate("<ButtonPress-1>", x=x1, y=y1)
    for i in range(1, passos + 1):
        c.event_generate("<B1-Motion>", x=x1 + (x2 - x1) * i / passos, y=y1 + (y2 - y1) * i / passos, state=0x100)
    c.event_generate("<ButtonRelease-1>", x=x2, y=y2)
    raiz.update()


def clicar(x, y):
    c.event_generate("<Motion>", x=x, y=y)
    c.event_generate("<ButtonPress-1>", x=x, y=y)
    c.event_generate("<ButtonRelease-1>", x=x, y=y)
    raiz.update()


def roda(x, y, delta=120):
    c.event_generate("<Motion>", x=x, y=y)
    c.event_generate("<MouseWheel>", x=x, y=y, delta=delta)
    raiz.update()


# EQ: arrastar o ponto MÉDIO para cima mexe no ganho e no knob
g = j.g_eq
x0, y0 = g.fx(cfg_teste.eq[2]["freq"]), g.fy(0)
arrastar(x0, y0, x0 + 40, y0 - 40)
ganho = cfg_teste.eq[2]["ganho"]
conferir("arrastar ponto do EQ", ganho > 3 and cfg_teste.eq[2]["freq"] > 800,
         f"MÉDIO foi para {cfg_teste.eq[2]['freq']:.0f} Hz {ganho:+.1f} dB")
conferir("knob acompanha o gráfico", abs(j.k_eq[1].valor - round(ganho * 2) / 2) < 0.51,
         f"knob MÉDIO = {j.k_eq[1].valor:+.1f}")

# Knob do EQ: roda do mouse sobe 0,5 dB e o gráfico acompanha
antes = cfg_teste.eq[4]["ganho"]
roda(j.k_eq[3].x, j.k_eq[3].y)
conferir("roda do mouse no knob", abs(cfg_teste.eq[4]["ganho"] - (antes + 0.5)) < 1e-6,
         f"AGUDO {antes:+.1f} -> {cfg_teste.eq[4]['ganho']:+.1f}")

# ZERAR volta tudo e o arraste continua funcionando depois (bandas trocadas)
j._zerar_eq()
raiz.update()
x0, y0 = g.fx(cfg_teste.eq[1]["freq"]), g.fy(0)
arrastar(x0, y0, x0, y0 - 30)
conferir("arrastar depois do ZERAR", cfg_teste.eq[1]["ganho"] > 2, f"GRAVE {cfg_teste.eq[1]['ganho']:+.1f} dB")

# Botão EQ desliga
clicar(430, 560)
conferir("botão EQ", cfg_teste.eq_ligado is False, f"eq_ligado = {cfg_teste.eq_ligado}")
clicar(430, 560)

# Knob LIMIAR (arrastar para cima) e o gráfico de dinâmica acompanha
antes = cfg_teste.comp_limiar_db
arrastar(j.k_limiar.x, j.k_limiar.y, j.k_limiar.x, j.k_limiar.y - 40)
d = j.g_din
alca = c.coords(d._alca_limiar)
centro_x = (alca[0] + alca[2]) / 2
conferir("knob LIMIAR", cfg_teste.comp_limiar_db > antes, f"{antes:.0f} -> {cfg_teste.comp_limiar_db:.1f} dB")
conferir("alça do gráfico acompanha", abs(centro_x - d.fx(cfg_teste.comp_limiar_db)) < 1, f"alça em x={centro_x:.0f}")

# Arrastar a alça de razão no gráfico muda o knob RAZÃO
thr = cfg_teste.comp_limiar_db
xr, yr = d.fx(0), d.fy(thr + (0 - thr) / cfg_teste.comp_razao)
arrastar(xr, yr, xr, d.fy(thr + 1))
conferir("alça de razão no gráfico", cfg_teste.comp_razao > 5 and abs(j.k_razao.valor - cfg_teste.comp_razao) < 0.6,
         f"razão {cfg_teste.comp_razao:.1f}:1, knob {j.k_razao.valor:.1f}")

# Fader VOZ: arrastar a tampa para cima aumenta o alvo
f = j.f_voz
arrastar(f.x, f._y(f.valor), f.x, f._y(f.valor) - 60)
conferir("fader VOZ", cfg_teste.alvo_db > -24, f"alvo {cfg_teste.alvo_db:.1f} dB")

# NIVEL desligado habilita o knob GANHO e desabilita o fader
clicar(197, 662)
conferir("NIVEL desliga e troca controles", not cfg_teste.nivelar and j.k_manual.ativo and not j.f_voz.ativo,
         f"nivelar={cfg_teste.nivelar}, ganho manual ativo={j.k_manual.ativo}")
clicar(197, 662)

# Crossfader do jogo × chat (mixer desligado no teste: só confere a config)
cfg_teste.mixer_ligado = True
m = j.g_mix
arrastar(m._bx(0), m.y + m.hc / 2, m._bx(0.5), m.y + m.hc / 2)
conferir("crossfader para o jogo", cfg_teste.vol_jogo == 100 and 45 < cfg_teste.vol_chat < 55 and
         abs(j.k_chat.valor - cfg_teste.vol_chat) < 0.01, f"chat {cfg_teste.vol_chat:.0f}% jogo {cfg_teste.vol_jogo:.0f}%")

# MUDO acende
clicar(266, 662)
conferir("botão MUDO", cfg_teste.mudo is True, f"mudo = {cfg_teste.mudo}")

raiz.destroy()
print()
print("TUDO CERTO" if not falhas else f"{len(falhas)} falha(s): {', '.join(falhas)}")
sys.exit(1 if falhas else 0)
