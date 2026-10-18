"""Janela do Mic Limpo no estilo mesa de som: uma "tela" com EQ, dinâmica e
jogo × chat em cima e a superfície de controle (knobs, fader, botões acesos,
LEDs) embaixo. Tudo desenhado num único Canvas.
"""

import ctypes
import os
import sys
import threading
import time
import tkinter as tk
import traceback
from tkinter import ttk

from . import atalhos, config, dispositivos
from .eq import bandas_padrao
from .graficos import GraficoDin, GraficoEQ, GraficoMix
from .motor import Motor
from .widgets import C, FONTE, BotaoLed, Fader, Knob, MedidorLed, escurecer, ret_arredondado

TITULO = "Mic Limpo"
ICONE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icone.ico")
LOG = os.path.join(config.PASTA, "erro.log")
LARGURA, ALTURA = 1180, 712
DICA_PADRAO = "Arraste os controles  ·  roda do mouse = passo fino  ·  Shift = mais fino  ·  duplo clique = valor padrão"


def registrar_erro(texto):
    os.makedirs(config.PASTA, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + texto + "\n")


def _secao(c, x1, x2, titulo):
    c.create_text((x1 + x2) / 2, 368, text=titulo, fill=C["fraco"], font=(FONTE, 8, "bold"))
    largura = len(titulo) * 3.6 + 12
    c.create_line(x1 + 12, 368, (x1 + x2) / 2 - largura, 368, fill=C["linha"])
    c.create_line((x1 + x2) / 2 + largura, 368, x2 - 12, 368, fill=C["linha"])


class Janela:
    def __init__(self, raiz, minimizado=False):
        self.r = raiz
        self.cfg = config.carregar()
        self.motor = Motor(self.cfg)
        self.quer_ligado = False
        self.erro = None
        self._proxima_tentativa = 0.0
        self._salvar_id = None
        self._eq_id = None
        self._tiques = 0
        self._mexeu_volume = 0.0
        try:
            from .mixer import Mixer
            self.mixer = Mixer()
        except Exception as e:  # sem Core Audio o resto funciona igual
            registrar_erro(f"mixer: {e}")
            self.mixer = None

        raiz.title(TITULO)
        raiz.configure(bg=C["fundo"])
        raiz.resizable(False, False)
        if os.path.exists(ICONE):
            raiz.iconbitmap(ICONE)
        self._estilo_ttk()
        self.c = tk.Canvas(raiz, width=LARGURA, height=ALTURA, bg=C["fundo"], highlightthickness=0)
        self.c.pack()
        self.c.dica = self._mostrar_dica
        self._montar()

        raiz.protocol("WM_DELETE_WINDOW", self.fechar)
        if self.cfg.ligar_ao_abrir:
            self.ligar()
        self._mostrar_status()
        self._mixer_periodico()
        raiz.after(50, self._tique)
        if minimizado:
            raiz.iconify()

    # ================= montagem =================

    def _montar(self):
        c, cfg = self.c, self.cfg

        # ---- barra de cima ----
        c.create_text(24, 25, text="MIC LIMPO", anchor="w", fill=C["texto"], font=(FONTE, 16, "bold"))
        c.create_text(150, 27, text="CONSOLE DE VOZ", anchor="w", fill=C["fraco"], font=(FONTE, 8, "bold"))
        self._status = c.create_text(290, 26, text="", anchor="w", fill=C["fraco"], font=(FONTE, 9))
        self._relogio = c.create_text(1004, 26, text=time.strftime("%H:%M"), anchor="e", fill=C["fraco"],
                                      font=(FONTE, 9))
        self._botao_texto(1052, 26, "AJUSTES", self._abrir_ajustes)
        self._power = self._botao_power(1138, 26)

        # ---- tela ----
        ret_arredondado(c, 12, 50, 1168, 344, 12, fill=C["tela_borda"])
        ret_arredondado(c, 22, 58, 1158, 336, 6, fill=C["tela"])
        c.create_rectangle(22, 62, 1158, 86, fill="#0d1620", width=0)
        ret_arredondado(c, 32, 66, 82, 82, 3, fill=escurecer(C["verde"], 0.4))
        c.create_text(57, 74, text="CH 1", fill=C["verde"], font=(FONTE, 8, "bold"))
        c.create_text(92, 74, text="MIC", anchor="w", fill=C["texto"], font=(FONTE, 9, "bold"))
        self._nome_mic = c.create_text(126, 74, text="", anchor="w", fill=C["fraco"], font=(FONTE, 8))
        self._voz = c.create_text(820, 74, text="● VOZ", anchor="w", fill=C["apagado"], font=(FONTE, 8, "bold"))
        self._leitura = c.create_text(880, 74, text="", anchor="w", fill=C["fraco"], font=(FONTE, 8))
        self._aba(62, 98, "EQ", lambda: cfg.eq_ligado, C["ciano"])
        self._aba(690, 98, "DINÂMICA", lambda: cfg.comp_ligado or cfg.silenciar_pausas, C["verde"])
        self._aba(920, 98, "JOGO × CHAT", lambda: cfg.mixer_ligado, C["roxo"])
        self.g_eq = GraficoEQ(c, 62, 112, 558, 184, cfg, self._eq_mudou)
        self.g_din = GraficoDin(c, 690, 112, 176, 176, cfg, self._din_mudou)
        self.g_mix = GraficoMix(c, 920, 112, 220, 184, cfg, self._mix_mudou)

        # ---- superfície ----
        ret_arredondado(c, 10, 352, 1170, 686, 10, fill=C["painel"], outline="#25292f")
        for x in (160, 300, 560, 800, 990):
            c.create_line(x, 360, x, 676, fill="#121417", width=2)
            c.create_line(x + 2, 360, x + 2, 676, fill="#262a31")
        for x1, x2, titulo in ((10, 160, "ENTRADA"), (160, 300, "CANAL"), (300, 560, "EQUALIZADOR"),
                               (560, 800, "DINÂMICA"), (800, 990, "JOGO × CHAT"), (990, 1170, "MASTER")):
            _secao(c, x1, x2, titulo)

        # ENTRADA
        self.k_sens = Knob(c, 85, 425, "SENSIBILIDADE", 0, 100, cfg.sensibilidade,
                           lambda v: self._definir("sensibilidade", v), lambda v: f"{v:.0f}%", padrao=50,
                           dica="Quão fácil o portão abre com a sua voz. Cortando começo das frases? Aumente.")
        self.b_ruido = BotaoLed(c, 85, 500, "RUÍDO", cfg.remover_ruido, lambda v: self._definir("remover_ruido", v),
                                dica="Remove ruído com IA (ventilador, teclado, chiado).")
        self.b_portao = BotaoLed(c, 85, 534, "PORTÃO", cfg.silenciar_pausas, self._portao_mudou,
                                 dica="Silencia o microfone quando você não está falando.")
        self.k_portao = Knob(c, 85, 600, "PORTÃO dB", -60, -10, cfg.portao_limiar_db, self._knob_portao,
                             lambda v: f"{v:.0f}", padrao=-60, raio=16,
                             dica="Nível mínimo para o portão abrir (bom contra TV e vozes distantes).")

        # CANAL
        self.m_in = MedidorLed(c, 174, 408, 205, rotulo="IN")
        self.m_out = MedidorLed(c, 278, 408, 205, rotulo="OUT")
        self.f_voz = Fader(c, 232, 408, 205, "VOZ", -36, -12, cfg.alvo_db, lambda v: self._definir("alvo_db", v),
                           marcas=(-12, -18, -24, -30, -36), formato=lambda v: f"{v:.0f} dB", padrao=-24,
                           dica="Volume da sua voz que o nivelador busca (a linha branca no gráfico de dinâmica).")
        self.b_nivel = BotaoLed(c, 197, 662, "NIVEL", cfg.nivelar, self._nivel_mudou, largura=58,
                                dica="Nivelador automático: sobe a voz baixa, abaixa a alta.")
        self.b_mudo = BotaoLed(c, 266, 662, "MUDO", cfg.mudo, lambda v: self._definir("mudo", v),
                               cor=C["vermelho"], largura=58, dica="Corta o microfone (ninguém te ouve).")

        # EQUALIZADOR
        self.k_eq = []
        for i, x in zip(range(1, 5), (336, 399, 462, 525)):
            banda = cfg.eq[i]
            self.k_eq.append(Knob(c, x, 425, banda["nome"], -15, 15, banda["ganho"],
                                  lambda v, i=i: self._knob_eq(i, v), lambda v: f"{v:+.1f}", padrao=0,
                                  cor=("#cbd5e1", C["laranja"], C["verde"], C["ciano"], C["roxo"])[i], bipolar=True,
                                  passo=0.5, dica=f"{banda['nome'].capitalize()}: volume desta faixa de frequência."))
        self.k_corte = Knob(c, 345, 560, "CORTE", 20, 300, cfg.eq[0]["freq"], lambda v: self._knob_eq(0, v),
                            lambda v: f"{v:.0f} Hz", padrao=80, raio=16, passo=5,
                            dica="Corta graves abaixo desta frequência (ronco, batida na mesa).")
        self.b_eq = BotaoLed(c, 430, 560, "EQ", cfg.eq_ligado, self._eq_ligado, cor=C["ciano"])
        self._botao_texto(515, 560, "ZERAR", self._zerar_eq, largura=58)

        # DINÂMICA
        self.k_limiar = Knob(c, 612, 425, "LIMIAR", -50, -3, cfg.comp_limiar_db, self._knob_limiar,
                             lambda v: f"{v:.0f} dB", padrao=-18, cor=C["verde"],
                             dica="Compressor: acima deste nível a voz começa a ser segurada.")
        self.k_razao = Knob(c, 680, 425, "RAZÃO", 1, 20, cfg.comp_razao, self._knob_razao,
                            lambda v: f"{v:.1f}:1", padrao=3, cor=C["verde"], passo=0.5,
                            dica="Quanto o compressor segura: 3:1 = cada 3 dB a mais viram 1.")
        self.k_max = Knob(c, 748, 425, "AUMENTO MÁX", 0, 36, cfg.ganho_max_db, lambda v: self._definir("ganho_max_db", v),
                          lambda v: f"+{v:.0f} dB", padrao=36, cor=C["laranja"],
                          dica="Quanto o nivelador pode aumentar a sua voz no máximo.")
        self.b_comp = BotaoLed(c, 630, 560, "COMP", cfg.comp_ligado, self._comp_ligado,
                               dica="Liga o compressor (segura gritos de forma suave).")
        self.k_manual = Knob(c, 735, 560, "GANHO", -20, 30, cfg.ganho_manual_db, lambda v: self._definir("ganho_manual_db", v),
                             lambda v: f"{v:+.0f} dB", padrao=0, raio=16, cor=C["laranja"],
                             dica="Ganho fixo, usado só com o NIVEL desligado.")

        # JOGO × CHAT
        self.k_chat = Knob(c, 850, 440, "CHAT", 0, 100, cfg.vol_chat, lambda v: self._knob_mix("vol_chat", v),
                           lambda v: f"{v:.0f}%", padrao=100, raio=24, cor=C["roxo"],
                           dica="Volume dos apps de chat (Discord, Teams...).")
        self.k_jogo = Knob(c, 940, 440, "JOGO", 0, 100, cfg.vol_jogo, lambda v: self._knob_mix("vol_jogo", v),
                           lambda v: f"{v:.0f}%", padrao=100, raio=24, cor=C["verde"],
                           dica="Volume de todo o resto (jogo, navegador, música).")
        self.b_mixer = BotaoLed(c, 895, 560, "MIXER", cfg.mixer_ligado, self._mixer_ligado, cor=C["roxo"],
                                dica="Liga o controle de volume por aplicativo. Desligado = volumes originais.")
        if self.mixer is None:
            c.create_text(895, 600, text="mixer indisponível", fill=C["vermelho"], font=(FONTE, 7))

        # MASTER
        self.k_volume = Knob(c, 1080, 462, "VOLUME", 0, 100, 50, self._knob_volume, lambda v: f"{v:.0f}%",
                             raio=40, cor=C["azul"], anel_led=True,
                             dica="Volume geral do Windows (saída padrão).")
        self._saida_nome = c.create_text(1080, 560, text="", fill=C["fraco"], font=(FONTE, 7))
        self.b_ouvir = BotaoLed(c, 1080, 600, "OUVIR", cfg.ouvir, self._ouvir_mudou, cor=C["laranja"],
                                dica="Toca o seu microfone (já tratado) nos alto-falantes, com ~80 ms de atraso.")
        self._ler_volume_geral()

        # rodapé
        self._dica = c.create_text(24, 699, text=DICA_PADRAO, anchor="w", fill=C["fraco"], font=(FONTE, 8))
        c.create_text(1156, 699, text="No Discord, use “CABLE Output” como microfone", anchor="e",
                      fill=escurecer(C["fraco"], 0.8), font=(FONTE, 8))

        self._sincronizar_habilitados()

    def _aba(self, x, y, texto, ligado, cor):
        largura = len(texto) * 6.5 + 18
        fundo = ret_arredondado(self.c, x, y - 8, x + largura, y + 8, 3, fill="", outline="")
        rot = self.c.create_text(x + largura / 2, y, text=texto, font=(FONTE, 8, "bold"))
        self._abas = getattr(self, "_abas", [])
        self._abas.append((fundo, rot, ligado, cor))

    def _pintar_abas(self):
        for fundo, rot, ligado, cor in self._abas:
            on = ligado()
            self.c.itemconfigure(fundo, fill=escurecer(cor, 0.3) if on else "#151b22")
            self.c.itemconfigure(rot, fill=cor if on else C["fraco"])

    def _botao_texto(self, x, y, texto, acao, largura=78):
        tag = f"bt{texto}"
        ret_arredondado(self.c, x - largura / 2, y - 12, x + largura / 2, y + 12, 5, fill="#2b2f36",
                        outline="#101114", tags=tag)
        self.c.create_text(x, y, text=texto, fill=C["texto"], font=(FONTE, 8, "bold"), tags=tag)
        self.c.tag_bind(tag, "<ButtonRelease-1>", lambda _e: acao())
        self.c.tag_bind(tag, "<Enter>", lambda _e: self.c.configure(cursor="hand2"))
        self.c.tag_bind(tag, "<Leave>", lambda _e: self.c.configure(cursor=""))

    def _botao_power(self, x, y):
        c = self.c
        tag = "power"
        c.create_oval(x - 17, y - 15, x + 17, y + 19, fill="#07080a", width=0, tags=tag)
        corpo = c.create_oval(x - 17, y - 17, x + 17, y + 17, fill="#2b2f36", outline="#101114", width=2, tags=tag)
        arco = c.create_arc(x - 8, y - 8, x + 8, y + 8, start=120, extent=300, style="arc", width=2.5, tags=tag)
        haste = c.create_line(x, y - 11, x, y - 1, width=2.5, capstyle="round", tags=tag)
        c.tag_bind(tag, "<ButtonRelease-1>", lambda _e: self._alternar())
        c.tag_bind(tag, "<Enter>", lambda _e: (self._mostrar_dica("Liga/desliga o microfone tratado."), c.configure(cursor="hand2")))
        c.tag_bind(tag, "<Leave>", lambda _e: (self._mostrar_dica(""), c.configure(cursor="")))
        return corpo, arco, haste

    def _mostrar_dica(self, texto):
        self.c.itemconfigure(self._dica, text=texto or DICA_PADRAO, fill=C["texto"] if texto else C["fraco"])

    def _estilo_ttk(self):
        s = ttk.Style(self.r)
        s.theme_use("clam")
        s.configure(".", background=C["painel"], foreground=C["texto"], font=(FONTE, 10),
                    bordercolor=C["linha"], lightcolor=C["linha"], darkcolor=C["linha"])
        s.configure("TFrame", background=C["painel"])
        s.configure("TLabel", background=C["painel"], foreground=C["texto"])
        s.configure("Fraco.TLabel", foreground=C["fraco"])
        s.configure("TCheckbutton", background=C["painel"], indicatorbackground=C["fundo"],
                    indicatorforeground="#0b0d10", indicatormargin=(0, 0, 8, 0))
        s.map("TCheckbutton", background=[("active", C["painel"])],
              indicatorbackground=[("selected", C["verde"]), ("active", C["linha"])])
        s.configure("TCombobox", fieldbackground=C["fundo"], background=C["painel"], foreground=C["texto"],
                    arrowcolor=C["texto"], padding=4)
        s.map("TCombobox", fieldbackground=[("readonly", C["fundo"])], foreground=[("readonly", C["texto"])],
              selectbackground=[("readonly", C["fundo"])], selectforeground=[("readonly", C["texto"])])
        self.r.option_add("*TCombobox*Listbox.background", C["painel"])
        self.r.option_add("*TCombobox*Listbox.foreground", C["texto"])
        self.r.option_add("*TCombobox*Listbox.selectBackground", C["verde"])
        self.r.option_add("*TCombobox*Listbox.selectForeground", "#0b0d10")
        s.configure("TButton", background=C["linha"], foreground=C["texto"], borderwidth=0, padding=(12, 5))
        s.map("TButton", background=[("active", "#3a3f4b")])

    # ================= ligação controles <-> config =================

    def _agendar_salvar(self):
        if self._salvar_id:
            self.r.after_cancel(self._salvar_id)
        self._salvar_id = self.r.after(600, lambda: config.salvar(self.cfg))

    def _definir(self, campo, valor):
        setattr(self.cfg, campo, valor)
        self._agendar_salvar()
        self._sincronizar_habilitados()

    def _sincronizar_habilitados(self):
        cfg = self.cfg
        self.f_voz.habilitar(cfg.nivelar)
        self.k_max.habilitar(cfg.nivelar)
        self.k_manual.habilitar(not cfg.nivelar)
        self.k_sens.habilitar(cfg.silenciar_pausas)
        self.k_portao.habilitar(cfg.silenciar_pausas)
        for k in self.k_eq + [self.k_corte]:
            k.habilitar(cfg.eq_ligado)
        self.k_limiar.habilitar(cfg.comp_ligado)
        self.k_razao.habilitar(cfg.comp_ligado)
        for k in (self.k_chat, self.k_jogo):
            k.habilitar(cfg.mixer_ligado and self.mixer is not None)
        self._pintar_abas()

    def _portao_mudou(self, v):
        self._definir("silenciar_pausas", v)
        self.g_din.desenhar()

    def _nivel_mudou(self, v):
        self._definir("nivelar", v)

    def _knob_portao(self, v):
        self.cfg.portao_limiar_db = min(v, self.cfg.comp_limiar_db - 3)
        self._agendar_salvar()
        self.g_din.desenhar()

    def _knob_limiar(self, v):
        self.cfg.comp_limiar_db = max(v, self.cfg.portao_limiar_db + 3)
        self._agendar_salvar()
        self.g_din.desenhar()

    def _knob_razao(self, v):
        self.cfg.comp_razao = v
        self._agendar_salvar()
        self.g_din.desenhar()

    def _comp_ligado(self, v):
        self._definir("comp_ligado", v)
        self.g_din.desenhar()

    def _din_mudou(self):  # arrastou no gráfico de dinâmica
        self.k_portao.definir(self.cfg.portao_limiar_db)
        self.k_limiar.definir(self.cfg.comp_limiar_db)
        self.k_razao.definir(self.cfg.comp_razao)
        self._agendar_salvar()

    def _knob_eq(self, i, v):
        self.cfg.eq[i]["freq" if i == 0 else "ganho"] = float(v)
        self.g_eq.sel = i
        self.g_eq.desenhar()
        self._eq_mudou(do_grafico=False)

    def _eq_mudou(self, do_grafico=True):
        if do_grafico:  # arrastou no gráfico: atualiza os knobs
            self.k_corte.definir(self.cfg.eq[0]["freq"])
            for i, k in enumerate(self.k_eq, start=1):
                k.definir(self.cfg.eq[i]["ganho"])
        if self._eq_id is None:  # recalcula o filtro no máximo ~30x por segundo
            self._eq_id = self.r.after(30, self._aplicar_eq)
        self._agendar_salvar()

    def _aplicar_eq(self):
        self._eq_id = None
        if self.motor.proc is not None:
            self.motor.proc.atualizar_eq()

    def _eq_ligado(self, v):
        self._definir("eq_ligado", v)
        self.g_eq.desenhar()

    def _zerar_eq(self):
        self.cfg.eq[:] = bandas_padrao()
        self.g_eq.desenhar()
        self._eq_mudou()

    def _knob_mix(self, campo, v):
        setattr(self.cfg, campo, v)
        self.g_mix.desenhar()
        self._mix_mudou(do_grafico=False)

    def _mix_mudou(self, do_grafico=True):
        if do_grafico:
            self.k_chat.definir(self.cfg.vol_chat)
            self.k_jogo.definir(self.cfg.vol_jogo)
        self._aplicar_mixer()
        self._agendar_salvar()

    def _mixer_ligado(self, v):
        self._definir("mixer_ligado", v)
        self.g_mix.desenhar()
        if self.mixer is not None:
            if v:
                self._aplicar_mixer()
            else:
                self.mixer.restaurar()

    def _aplicar_mixer(self):
        if self.mixer is not None and self.cfg.mixer_ligado:
            try:
                self.mixer.aplicar(self.cfg.vol_chat / 100, self.cfg.vol_jogo / 100)
            except OSError as e:
                registrar_erro(f"mixer aplicar: {e}")

    def _mixer_periodico(self):
        if self.mixer is not None:
            try:
                self.mixer.atualizar()
                self._aplicar_mixer()
                if time.monotonic() - self._mexeu_volume > 3:
                    self._ler_volume_geral()
            except OSError as e:
                registrar_erro(f"mixer: {e}")
        self.r.after(2000, self._mixer_periodico)

    def _knob_volume(self, v):
        self._mexeu_volume = time.monotonic()
        if self.mixer is not None:
            try:
                self.mixer.definir_volume_geral(v / 100)
            except OSError as e:
                registrar_erro(f"volume geral: {e}")

    def _ler_volume_geral(self):
        if self.mixer is None:
            return
        try:
            nome, vol = self.mixer.volume_geral()
        except OSError:
            return
        self.k_volume.definir(round(vol * 100))
        curto = nome.split("(")[-1].rstrip(")") if "(" in nome else nome
        cabo = "CABLE" in nome
        self.c.itemconfigure(self._saida_nome, text=("⚠ saída do Windows é o cabo!" if cabo else curto)[:34],
                             fill=C["vermelho"] if cabo else C["fraco"])

    def _ouvir_mudou(self, v):
        self._definir("ouvir", v)
        try:
            self.motor.definir_ouvir(v)
        except Exception as e:
            self.erro = f"Não deu para tocar nos alto-falantes: {e}"
            self._mostrar_status()

    # ================= janela de ajustes =================

    def _abrir_ajustes(self):
        if getattr(self, "_ajustes", None) is not None and self._ajustes.winfo_exists():
            self._ajustes.lift()
            return
        t = tk.Toplevel(self.r)
        self._ajustes = t
        t.title("Ajustes")
        t.configure(bg=C["painel"])
        t.resizable(False, False)
        t.transient(self.r)
        if os.path.exists(ICONE):
            t.iconbitmap(ICONE)
        f = ttk.Frame(t, padding=18)
        f.pack(fill="both")
        combos = {}

        def linha(rotulo, chave, valores, atual, ao_mudar):
            ttk.Label(f, text=rotulo).grid(row=len(combos), column=0, sticky="w", pady=4, padx=(0, 10))
            v = tk.StringVar(value=atual)
            cb = ttk.Combobox(f, textvariable=v, values=valores, state="readonly", width=44)
            cb.grid(row=len(combos), column=1, sticky="we", pady=4)
            cb.bind("<<ComboboxSelected>>", lambda _e: ao_mudar(v.get()))
            combos[chave] = (cb, v)

        def preencher():
            entradas = [n for n in dispositivos.entradas() if "CABLE" not in n]
            cabos = [n for n in dispositivos.saidas() if "CABLE" in n] or ["(VB-CABLE não encontrado)"]
            falantes = [n for n in dispositivos.saidas() if not dispositivos.virtual(n)]
            for chave, valores, atual in (
                    ("entrada", entradas, self.cfg.entrada or dispositivos.microfone_sugerido()),
                    ("saida", cabos, self.cfg.saida or dispositivos.cabo_sugerido()),
                    ("ouvir", falantes, self.cfg.saida_ouvir or dispositivos.alto_falante_sugerido())):
                cb, v = combos[chave]
                cb["values"] = valores
                v.set(atual)

        linha("Microfone", "entrada", [], "", self._mudar_entrada)
        linha("Enviar para", "saida", [], "", self._mudar_saida)
        linha("Ouvir em", "ouvir", [], "", self._mudar_saida_ouvir)
        preencher()
        ttk.Label(f, text="No Discord, escolha “CABLE Output (VB-Audio Virtual Cable)” como microfone.",
                  style="Fraco.TLabel").grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 10))

        v_win = tk.BooleanVar(value=atalhos.inicia_com_windows())
        v_win.trace_add("write", lambda *_: self._mudar_windows(v_win.get()))
        ttk.Checkbutton(f, text="Iniciar com o Windows", variable=v_win).grid(row=4, column=0, columnspan=2, sticky="w")
        v_abrir = tk.BooleanVar(value=self.cfg.ligar_ao_abrir)
        v_abrir.trace_add("write", lambda *_: self._definir("ligar_ao_abrir", v_abrir.get()))
        ttk.Checkbutton(f, text="Ligar o microfone ao abrir", variable=v_abrir).grid(row=5, column=0, columnspan=2,
                                                                                    sticky="w", pady=(4, 0))
        botoes = ttk.Frame(f)
        botoes.grid(row=6, column=0, columnspan=2, sticky="e", pady=(14, 0))

        def atualizar():
            self._atualizar_dispositivos()
            preencher()

        ttk.Button(botoes, text="Atualizar lista", command=atualizar).pack(side="left", padx=(0, 8))
        ttk.Button(botoes, text="Fechar", command=t.destroy).pack(side="left")

    def _reiniciar_se_ligado(self):
        if self.quer_ligado:
            self.ligar()

    def _mudar_entrada(self, nome):
        self._definir("entrada", nome)
        self._reiniciar_se_ligado()

    def _mudar_saida(self, nome):
        if "CABLE" in nome:
            self._definir("saida", nome)
            self._reiniciar_se_ligado()

    def _mudar_saida_ouvir(self, nome):
        self._definir("saida_ouvir", nome)
        if self.cfg.ouvir and self.motor.ativo:
            self.motor.definir_ouvir(False)
            self._ouvir_mudou(True)

    def _atualizar_dispositivos(self):
        estava = self.quer_ligado
        self.motor.desligar()
        dispositivos.recarregar()
        if estava:
            self.ligar()

    def _mudar_windows(self, ativo):
        def trabalho():
            try:
                atalhos.iniciar_com_windows(ativo)
            except Exception as e:
                registrar_erro(f"atalho de inicialização: {e}")

        threading.Thread(target=trabalho, daemon=True).start()

    # ================= ligar / desligar =================

    def ligar(self):
        self.quer_ligado = True
        try:
            self.motor.ligar()
            self.erro = None
        except Exception as e:
            self.erro = str(e)
        self._mostrar_status()

    def desligar(self):
        self.quer_ligado = False
        self.motor.desligar()
        self.erro = None
        self._mostrar_status()

    def _alternar(self):
        if self.quer_ligado:
            self.desligar()
        else:
            self.ligar()

    def _mostrar_status(self):
        corpo, arco, haste = self._power
        cor = C["azul"] if self.quer_ligado and not self.erro else C["vermelho"] if self.erro else C["fraco"]
        self.c.itemconfigure(corpo, fill=escurecer(cor, 0.3) if self.quer_ligado else "#2b2f36",
                             outline=cor if self.quer_ligado else "#101114")
        self.c.itemconfigure(arco, outline=cor)
        self.c.itemconfigure(haste, fill=cor)
        if self.erro:
            texto, cor_txt = f"●  {self.erro}", C["vermelho"]
        elif self.motor.ativo:
            texto, cor_txt = f"●  LIGADO  ·  atraso ≈ {self.motor.latencia_ms()} ms", C["verde"]
        else:
            texto, cor_txt = "●  DESLIGADO: o Discord não recebe sua voz", C["fraco"]
        self.c.itemconfigure(self._status, text=texto[:90], fill=cor_txt)
        self.c.itemconfigure(self._nome_mic, text=self.motor.entrada_nome if self.motor.ativo else "")

    # ================= atualização periódica =================

    def _mudar(self, item, **opcoes):
        """itemconfigure só quando muda: cada repintura no Tk custa CPU."""
        cache = self.__dict__.setdefault("_cache_itens", {})
        if cache.get(item) != opcoes:
            cache[item] = opcoes
            self.c.itemconfigure(item, **opcoes)

    def _tique(self):
        self._tiques += 1
        m = self.motor
        p = m.proc
        if m.ativo and p is not None:
            self.m_in.mostrar(p.entrada_db)
            self.m_out.mostrar(p.saida_db)
            self._mudar(self._voz, fill=C["verde"] if p.falando else C["apagado"])
            texto = f"GANHO {p.ganho_db:+.1f} dB"
            reducao = p.compressor_db + p.limitador_db
            if reducao < -0.5:
                texto += f"   GR {reducao:.0f} dB"
            if self.cfg.mudo:
                texto += "   MUDO"
            self._mudar(self._leitura, text=texto, fill=C["vermelho"] if self.cfg.mudo else C["fraco"])
            if self._tiques % 2 == 0:
                self.g_eq.espectro(p.espectro.copy())
        else:
            self.m_in.mostrar(-100)
            self.m_out.mostrar(-100)
            self._mudar(self._voz, fill=C["apagado"])
            self._mudar(self._leitura, text="")
        self.g_din.atualizar(p if m.ativo else None)
        if self.mixer is not None and self.cfg.mixer_ligado:
            try:
                self.g_mix.atualizar(self.mixer.picos(), self.mixer.apps_chat, self.mixer.apps_jogo)
            except OSError:
                pass
        if self._tiques % 25 == 0:
            self.c.itemconfigure(self._relogio, text=time.strftime("%H:%M"))

        # Guarda o ganho aprendido de vez em quando (sobrevive a reinício e desligamento)
        if p is not None and self.cfg.nivelar and abs(p.ganho_db - self.cfg.ganho_aprendido_db) >= 1:
            self.cfg.ganho_aprendido_db = round(p.ganho_db, 1)
            self._agendar_salvar()

        # Se o mic foi desplugado ou o áudio do Windows reiniciou, tenta voltar sozinho
        agora = time.monotonic()
        if self.quer_ligado and agora >= self._proxima_tentativa and (not m.ativo or not m.saudavel()):
            self._proxima_tentativa = agora + 3
            if m.erro:
                registrar_erro(f"motor: {m.erro}")
            m.desligar()
            try:
                dispositivos.recarregar()
            except Exception as e:
                registrar_erro(f"recarregar: {e}")
            self.ligar()
        self.r.after(50, self._tique)

    def fechar(self):
        if self.motor.proc is not None and self.cfg.nivelar:
            self.cfg.ganho_aprendido_db = round(self.motor.proc.ganho_db, 1)
        self.motor.desligar()
        if self.mixer is not None:
            self.mixer.restaurar()
        config.salvar(self.cfg)
        self.r.destroy()


def _trazer_para_frente():
    u = ctypes.windll.user32
    hwnd = u.FindWindowW(None, TITULO)
    if hwnd:
        u.ShowWindow(hwnd, 9)  # SW_RESTORE
        u.SetForegroundWindow(hwnd)


def main():
    minimizado = "--minimizado" in sys.argv
    # A mesa é desenhada em pixels fixos: só fica nítida em 100% de escala.
    # Em telas com zoom, deixa o Windows ampliar (fica um pouco borrado, mas no lugar certo).
    try:
        if ctypes.windll.user32.GetDpiForSystem() <= 96:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MicLimpo")

    # Só uma cópia por vez: duas mandariam a voz em dobro para o cabo
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\MicLimpo")  # noqa: F841
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        _trazer_para_frente()
        return

    raiz = tk.Tk()
    raiz.tk.call("tk", "scaling", 96 / 72)
    raiz.report_callback_exception = lambda *exc: registrar_erro("".join(traceback.format_exception(*exc)))
    try:
        Janela(raiz, minimizado)
        raiz.mainloop()
    except Exception:
        registrar_erro(traceback.format_exc())
        raise
