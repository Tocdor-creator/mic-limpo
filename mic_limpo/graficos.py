"""Gráficos da "tela" da mesa: EQ com espectro, curva de dinâmica e jogo × chat.
Desenham no Canvas compartilhado e editam a config diretamente; avisam por callback.
"""

import math

import numpy as np

from .eq import TAXA, resposta_db
from .processador import ESPECTRO, TETO_DB, curva_dinamica
from .widgets import C, FONTE, _dica, escurecer, registrar_roda

CORES_BANDAS = ("#cbd5e1", C["laranja"], C["verde"], C["ciano"], C["roxo"])


def _hover(c, tag, dica):
    c.tag_bind(tag, "<Enter>", lambda _e: (_dica(c, dica), c.configure(cursor="hand2")))
    c.tag_bind(tag, "<Leave>", lambda _e: (_dica(c, ""), c.configure(cursor="")))


class GraficoEQ:
    FMIN, FMAX, DBMAX = 20.0, 20000.0, 18.0

    def __init__(self, c, x, y, w, h, cfg, ao_mudar):
        self.c, self.x, self.y, self.w, self.h = c, x, y, w, h
        self.cfg = cfg
        self.ao_mudar = ao_mudar
        self.sel = 2
        self._freqs = np.geomspace(self.FMIN, self.FMAX, 220)

        for f in (50, 100, 200, 500, 1000, 2000, 5000, 10000):
            xx = self.fx(f)
            c.create_line(xx, y, xx, y + h, fill=C["grade_forte"] if f in (100, 1000, 10000) else C["grade"])
            c.create_text(xx, y + h + 9, text=f"{f // 1000}k" if f >= 1000 else str(f), fill=C["fraco"], font=(FONTE, 7))
        for d in range(-18, 19, 6):
            yy = self.fy(d)
            c.create_line(x, yy, x + w, yy, fill=C["grade_forte"] if d == 0 else C["grade"])
            c.create_text(x - 4, yy, text=f"{d:+d}" if d else "0", anchor="e", fill=C["fraco"], font=(FONTE, 7))

        # analisador de espectro (barras atrás da curva)
        self._nb = 64
        bordas = np.geomspace(40, 16000, self._nb + 1)
        bins = np.fft.rfftfreq(ESPECTRO, 1 / TAXA)
        self._faixas = [(int(np.searchsorted(bins, a)), max(int(np.searchsorted(bins, b)), int(np.searchsorted(bins, a)) + 1))
                        for a, b in zip(bordas[:-1], bordas[1:])]
        self._janela = np.hanning(ESPECTRO).astype(np.float32)
        self._niveis = np.full(self._nb, -100.0)
        self._barras = []
        for a, b in zip(bordas[:-1], bordas[1:]):
            x1, x2 = self.fx(a) + 1, self.fx(b) - 1
            self._barras.append([c.create_rectangle(x1, y + h, x2, y + h, width=0, fill="#1f3a4d"), x1, x2, 0])

        self._area = c.create_polygon(0, 0, 0, 0, fill="#0f3b4f", outline="")
        self._curva = c.create_line(0, 0, 1, 1, fill=C["ciano"], width=2.2)
        self._nos = []
        for i, banda in enumerate(cfg.eq):
            tag = f"eqno{i}"
            circ = c.create_oval(0, 0, 1, 1, fill=escurecer(CORES_BANDAS[i], 0.35), outline=CORES_BANDAS[i], width=2, tags=tag)
            txt = c.create_text(0, 0, text=str(i + 1), fill=C["texto"], font=(FONTE, 7, "bold"), tags=tag)
            self._nos.append((circ, txt))
            self._ligar_no(i, tag)
        self._info = c.create_text(x + 8, y + 10, anchor="w", fill=C["texto"], font=(FONTE, 9, "bold"))
        self.desenhar()

    def fx(self, f):
        return self.x + self.w * math.log(f / self.FMIN) / math.log(self.FMAX / self.FMIN)

    def fy(self, d):
        return self.y + self.h / 2 - d / self.DBMAX * (self.h / 2)

    def _freq_em(self, xx):
        return self.FMIN * (self.FMAX / self.FMIN) ** ((xx - self.x) / self.w)

    def _ligar_no(self, i, tag):
        c = self.c
        tipo = self.cfg.eq[i]["tipo"]

        def pressionar(_e):
            self.sel = i
            self.desenhar()

        def arrastar(e):
            banda = self.cfg.eq[i]  # busca na hora: ZERAR troca as bandas
            banda["freq"] = float(min(max(self._freq_em(e.x), 20.0), 18000.0))
            if banda["tipo"] != "passa_alta":
                banda["ganho"] = float(min(max((self.y + self.h / 2 - e.y) / (self.h / 2) * self.DBMAX, -15.0), 15.0))
            self.desenhar()
            self.ao_mudar()

        def roda(e):
            banda = self.cfg.eq[i]
            if banda["tipo"] == "pico":
                banda["q"] = float(min(max(banda["q"] * (1.15 if e.delta > 0 else 1 / 1.15), 0.3), 8.0))
            else:
                banda["ganho"] = float(min(max(banda["ganho"] + (0.5 if e.delta > 0 else -0.5), -15.0), 15.0))
            self.sel = i
            self.desenhar()
            self.ao_mudar()

        def duplo(_e):
            banda = self.cfg.eq[i]
            if banda["tipo"] == "passa_alta":
                banda["freq"] = 80.0
            else:
                banda["ganho"] = 0.0
            self.desenhar()
            self.ao_mudar()

        c.tag_bind(tag, "<ButtonPress-1>", pressionar)
        c.tag_bind(tag, "<B1-Motion>", arrastar)
        registrar_roda(c, tag, roda)
        c.tag_bind(tag, "<Double-Button-1>", duplo)
        dica = ("Arraste: esquerda/direita muda a frequência do corte de graves. Duplo clique: 80 Hz."
                if tipo == "passa_alta" else
                "Arraste: lados = frequência, cima/baixo = volume. Roda: largura (Q). Duplo clique: zera.")
        _hover(c, tag, dica)

    def desenhar(self):
        c, cfg = self.c, self.cfg
        ativo = cfg.eq_ligado
        resp = np.clip(resposta_db(cfg.eq, self._freqs), -self.DBMAX, self.DBMAX)
        pts = []
        for f, d in zip(self._freqs, resp):
            pts += [self.fx(f), self.fy(d)]
        zero = self.fy(0)
        c.coords(self._curva, *pts)
        c.coords(self._area, self.x, zero, *pts, self.x + self.w, zero)
        c.itemconfigure(self._curva, fill=C["ciano"] if ativo else C["apagado"])
        c.itemconfigure(self._area, fill="#0f3b4f" if ativo else "#151a20")
        for i, (banda, (circ, txt)) in enumerate(zip(cfg.eq, self._nos)):
            xx = self.fx(banda["freq"])
            yy = self.fy(float(np.clip(resposta_db(cfg.eq, [banda["freq"]])[0], -self.DBMAX, self.DBMAX))
                         if banda["tipo"] == "passa_alta" else banda["ganho"])
            r = 9 if i == self.sel else 7
            c.coords(circ, xx - r, yy - r, xx + r, yy + r)
            c.coords(txt, xx, yy)
            cor = CORES_BANDAS[i] if ativo else C["apagado"]
            c.itemconfigure(circ, outline=cor, fill=escurecer(cor, 0.35), width=3 if i == self.sel else 2)
        b = cfg.eq[self.sel]
        texto = f"{b['nome']}   {b['freq']:.0f} Hz" if b["freq"] < 1000 else f"{b['nome']}   {b['freq'] / 1000:.1f} kHz"
        if b["tipo"] != "passa_alta":
            texto += f"   {b['ganho']:+.1f} dB"
        if b["tipo"] == "pico":
            texto += f"   Q {b['q']:.1f}"
        c.itemconfigure(self._info, text=texto if ativo else "EQ DESLIGADO", fill=CORES_BANDAS[self.sel] if ativo else C["fraco"])

    def espectro(self, amostras):
        mag = np.abs(np.fft.rfft(amostras * self._janela)) / (ESPECTRO / 4)
        dbs = np.array([20 * math.log10(float(mag[a:b].max()) + 1e-9) for a, b in self._faixas])
        self._niveis = np.maximum(dbs, self._niveis - 2.5)
        base = self.y + self.h
        for barra, nivel in zip(self._barras, self._niveis):
            altura = int(max(0.0, min(1.0, (nivel + 90) / 75)) * self.h)
            if abs(altura - barra[3]) >= 2:  # só redesenha o que mudou de verdade
                barra[3] = altura
                self.c.coords(barra[0], barra[1], base - altura, barra[2], base)


class GraficoDin:
    MIN = -60.0

    def __init__(self, c, x, y, w, h, cfg, ao_mudar):
        self.c, self.x, self.y, self.w, self.h = c, x, y, w, h
        self.cfg = cfg
        self.ao_mudar = ao_mudar
        for d in range(-60, 1, 10):
            xx, yy = self.fx(d), self.fy(d)
            c.create_line(xx, y, xx, y + h, fill=C["grade"])
            c.create_line(x, yy, x + w, yy, fill=C["grade"])
            if d > -60:
                c.create_text(xx, y + h + 9, text=str(d), fill=C["fraco"], font=(FONTE, 7))
                c.create_text(x - 4, yy, text=str(d), anchor="e", fill=C["fraco"], font=(FONTE, 7))
        c.create_line(x, y + h, x + w, y, fill=C["grade_forte"], dash=(3, 3))
        c.create_text(x + w / 2, y + h + 20, text="ENTRADA (dB)", fill=C["fraco"], font=(FONTE, 7))
        c.create_line(self.fx(-60), self.fy(TETO_DB), self.fx(0), self.fy(TETO_DB), fill=escurecer(C["vermelho"], 0.6), dash=(2, 2))
        self._curva = c.create_line(0, 0, 1, 1, fill=C["verde"], width=2.2)
        self._gr = c.create_rectangle(x + w + 6, y, x + w + 12, y, fill=C["laranja"], width=0)
        c.create_rectangle(x + w + 6, y, x + w + 12, y + h, outline=C["grade_forte"])
        c.create_text(x + w + 9, y - 7, text="GR", fill=C["fraco"], font=(FONTE, 7))
        self._rastro = [c.create_oval(0, 0, 0, 0, fill=escurecer("#ffffff", 0.2 + 0.12 * i), width=0, state="hidden")
                        for i in range(6)]
        self._ponto = c.create_oval(0, 0, 0, 0, fill="#ffffff", outline=C["verde"], width=2, state="hidden")
        self._hist = []
        self._alca_portao = self._alca("dinportao", C["laranja"],
                                       "Portão: arraste para os lados. Abaixo deste nível o microfone fica mudo.",
                                       self._arrastar_portao)
        self._alca_limiar = self._alca("dinlimiar", C["ciano"],
                                       "Compressor: arraste para os lados para mudar o limiar.", self._arrastar_limiar)
        self._alca_razao = self._alca("dinrazao", C["ciano"],
                                      "Razão: arraste para cima/baixo. Mais baixo = segura mais os gritos.", self._arrastar_razao)
        # canto de baixo à direita: a curva nunca passa ali (saída baixa com entrada alta)
        self._info = c.create_text(x + w - 6, y + h - 5, anchor="se", justify="right", fill=C["texto"],
                                   font=(FONTE, 8, "bold"))
        self.desenhar()

    def fx(self, d):
        return self.x + (d - self.MIN) / -self.MIN * self.w

    def fy(self, d):
        return self.y + self.h - (d - self.MIN) / -self.MIN * self.h

    def _db_x(self, xx):
        return self.MIN + (xx - self.x) / self.w * -self.MIN

    def _db_y(self, yy):
        return self.MIN + (self.y + self.h - yy) / self.h * -self.MIN

    def _alca(self, tag, cor, dica, arrastar):
        item = self.c.create_oval(0, 0, 1, 1, fill=escurecer(cor, 0.35), outline=cor, width=2, tags=tag)
        self.c.tag_bind(tag, "<B1-Motion>", lambda e: (arrastar(e), self.desenhar(), self.ao_mudar()))
        _hover(self.c, tag, dica)
        return item

    def _arrastar_portao(self, e):
        self.cfg.portao_limiar_db = float(min(max(self._db_x(e.x), -60.0), self.cfg.comp_limiar_db - 3))

    def _arrastar_limiar(self, e):
        self.cfg.comp_limiar_db = float(min(max(self._db_x(e.x), max(-50.0, self.cfg.portao_limiar_db + 3)), -3.0))

    def _arrastar_razao(self, e):
        thr = self.cfg.comp_limiar_db
        y0 = min(max(self._db_y(e.y), thr + 0.01), 0.0)
        self.cfg.comp_razao = float(min(max(-thr / (y0 - thr), 1.0), 20.0))

    def _por(self, item, xx, yy, r=6):
        self.c.coords(item, xx - r, yy - r, xx + r, yy + r)

    def desenhar(self):
        cfg = self.cfg
        xs = np.linspace(self.MIN, 0, 241)
        ys = np.maximum(curva_dinamica(cfg, xs), self.MIN)
        pts = []
        for a, b in zip(xs, ys):
            pts += [self.fx(a), self.fy(b)]
        self.c.coords(self._curva, *pts)
        thr = cfg.comp_limiar_db
        self._por(self._alca_portao, self.fx(cfg.portao_limiar_db), self.fy(cfg.portao_limiar_db))
        self._por(self._alca_limiar, self.fx(thr), self.fy(thr))
        self._por(self._alca_razao, self.fx(0), self.fy(thr + (0 - thr) / cfg.comp_razao), 5)
        self.c.itemconfigure(self._alca_portao, state="normal" if cfg.silenciar_pausas else "hidden")
        estado = "normal" if cfg.comp_ligado else "hidden"
        self.c.itemconfigure(self._alca_limiar, state=estado)
        self.c.itemconfigure(self._alca_razao, state=estado)
        partes = []
        if cfg.silenciar_pausas:
            partes.append(f"PORTÃO {cfg.portao_limiar_db:.0f} dB")
        razao = f"{cfg.comp_razao:.0f}" if cfg.comp_razao == int(cfg.comp_razao) else f"{cfg.comp_razao:.1f}"
        partes.append(f"COMP {thr:.0f} dB  {razao}:1" if cfg.comp_ligado else "COMP OFF")
        self.c.itemconfigure(self._info, text="\n".join(partes))

    def atualizar(self, proc):
        if proc is None or not proc.falando:
            if self._hist:  # esconde uma vez só (repetir custa redesenho)
                self.c.itemconfigure(self._ponto, state="hidden")
                for r in self._rastro:
                    self.c.itemconfigure(r, state="hidden")
                self._hist.clear()
            reducao = 0.0
        else:
            xin = min(max(proc.din_entrada_db, self.MIN), 0)
            yout = min(max(proc.din_saida_db, self.MIN), 0)
            self._hist = (self._hist + [(xin, yout)])[-7:]
            for item, (a, b) in zip(self._rastro, self._hist[:-1]):
                self.c.itemconfigure(item, state="normal")
                self._por(item, self.fx(a), self.fy(b), 2.5)
            self.c.itemconfigure(self._ponto, state="normal")
            self._por(self._ponto, self.fx(xin), self.fy(yout), 5)
            reducao = proc.compressor_db + proc.limitador_db
        altura = int(min(1.0, -reducao / 20) * self.h)
        if altura != getattr(self, "_gr_altura", -1):
            self._gr_altura = altura
            self.c.coords(self._gr, self.x + self.w + 6, self.y, self.x + self.w + 12, self.y + altura)


def lei_balanco(b):
    """Posição do crossfader (-1 = só chat, +1 = só jogo) -> volumes (chat, jogo) em %."""
    return (100.0 if b <= 0 else 100.0 * (1 - b)), (100.0 if b >= 0 else 100.0 * (1 + b))


def balanco_de(chat, jogo):
    if chat >= 99.5 and jogo < 99.5:
        return -(1 - jogo / 100)
    if jogo >= 99.5 and chat < 99.5:
        return 1 - chat / 100
    return (jogo - chat) / 100


class GraficoMix:
    def __init__(self, c, x, y, w, h, cfg, ao_mudar):
        self.c, self.x, self.y, self.w, self.h = c, x, y, w, h
        self.cfg = cfg
        self.ao_mudar = ao_mudar
        hc = h * 0.52
        self.hc = hc
        # área de arrasto: precisa de cor (retângulo vazio só recebe clique na borda)
        self._zona = c.create_rectangle(x, y, x + w, y + hc, fill=C["tela"], outline="", tags="mixzona")
        for i in range(5):
            xx = x + w * i / 4
            c.create_line(xx, y, xx, y + hc, fill=C["grade_forte"] if i == 2 else C["grade"], tags="mixzona")
        for i in range(3):
            c.create_line(x, y + hc * i / 2, x + w, y + hc * i / 2, fill=C["grade"], tags="mixzona")
        c.create_text(x + 2, y + hc + 9, text="◀ CHAT", anchor="w", fill=C["roxo"], font=(FONTE, 7, "bold"))
        c.create_text(x + w - 2, y + hc + 9, text="JOGO ▶", anchor="e", fill=C["verde"], font=(FONTE, 7, "bold"))
        bs = np.linspace(-1, 1, 81)
        pc, pj = [], []
        for b in bs:
            vc, vj = lei_balanco(b)
            pc += [self._bx(b), y + hc * (1 - vc / 100)]
            pj += [self._bx(b), y + hc * (1 - vj / 100)]
        c.create_line(*pc, fill=escurecer(C["roxo"], 0.75), width=2, tags="mixzona")
        c.create_line(*pj, fill=escurecer(C["verde"], 0.75), width=2, tags="mixzona")
        self._marca = c.create_line(0, y, 0, y + hc, fill="#ffffff", width=1, dash=(3, 2), tags="mixzona")
        self._tampa = c.create_rectangle(0, 0, 1, 1, fill="#c9cdd2", outline="#16181b", tags="mixtampa")
        for tag in ("mixzona", "mixtampa"):
            c.tag_bind(tag, "<B1-Motion>", self._arrastar)
            c.tag_bind(tag, "<ButtonPress-1>", self._arrastar)
            c.tag_bind(tag, "<Double-Button-1>", lambda _e: self._definir(0))
            _hover(c, tag, "Arraste para os lados: equilíbrio entre o chat (Discord) e o jogo. Duplo clique: meio.")
        self._linhas = {}
        for i, (grupo, cor) in enumerate((("chat", C["roxo"]), ("jogo", C["verde"]))):
            yy = y + hc + 26 + i * 30
            c.create_text(x, yy, text=grupo.upper(), anchor="w", fill=cor, font=(FONTE, 8, "bold"))
            bx = x + 42
            c.create_rectangle(bx, yy - 5, x + w, yy + 5, fill="#101820", outline=C["grade_forte"])
            vol = c.create_rectangle(bx, yy - 5, bx, yy + 5, fill=escurecer(cor, 0.45), width=0)
            pico = c.create_rectangle(bx, yy - 2, bx, yy + 2, fill=cor, width=0)
            texto = c.create_text(bx, yy + 13, anchor="w", fill=C["fraco"], font=(FONTE, 7))
            self._linhas[grupo] = (bx, yy, vol, pico, texto)
        self._aviso = c.create_text(x + w / 2, y + hc / 2, text="", fill=C["fraco"], font=(FONTE, 8, "bold"),
                                    tags="mixzona")
        self.desenhar()

    def _bx(self, b):
        return self.x + (b + 1) / 2 * self.w

    def _arrastar(self, e):
        self._definir(min(max((e.x - self.x) / self.w * 2 - 1, -1.0), 1.0))

    def _definir(self, b):
        self.cfg.vol_chat, self.cfg.vol_jogo = lei_balanco(b)
        self.desenhar()
        self.ao_mudar()

    def desenhar(self):
        b = balanco_de(self.cfg.vol_chat, self.cfg.vol_jogo)
        xx = self._bx(b)
        self.c.coords(self._marca, xx, self.y, xx, self.y + self.hc)
        self.c.coords(self._tampa, xx - 8, self.y + self.hc - 12, xx + 8, self.y + self.hc + 2)
        ligado = self.cfg.mixer_ligado
        self.c.itemconfigure(self._aviso, text="" if ligado else "MIXER DESLIGADO")
        for grupo, vol in (("chat", self.cfg.vol_chat), ("jogo", self.cfg.vol_jogo)):
            bx, yy, item, _, _ = self._linhas[grupo]
            self.c.coords(item, bx, yy - 5, bx + (self.x + self.w - bx) * vol / 100, yy + 5)

    def atualizar(self, picos, apps_chat, apps_jogo):
        if not hasattr(self, "_ultimo"):
            self._ultimo = {}
        for grupo, pico, apps in (("chat", picos[0], apps_chat), ("jogo", picos[1], apps_jogo)):
            bx, yy, _, item, texto = self._linhas[grupo]
            vol = self.cfg.vol_chat if grupo == "chat" else self.cfg.vol_jogo
            largura = int((self.x + self.w - bx) * min(pico, 1.0))
            nomes = ", ".join(apps[:3]) + ("…" if len(apps) > 3 else "") if apps else "nenhum app tocando"
            rotulo = f"{vol:.0f}%  ·  {nomes}"
            antes = self._ultimo.get(grupo, (None, None))
            if largura != antes[0]:  # só redesenha o que mudou
                self.c.coords(item, bx, yy - 2, bx + largura, yy + 2)
            if rotulo != antes[1]:
                self.c.itemconfigure(texto, text=rotulo)
            self._ultimo[grupo] = (largura, rotulo)
