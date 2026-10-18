"""Controles de mesa de som desenhados num Canvas: knob, fader, botão aceso e
medidor de LED. Todos desenham no mesmo Canvas (com uma tag própria) e avisam
mudanças por callback.

Interação comum: arrastar ajusta, roda do mouse dá passos finos e duplo clique
volta ao valor padrão.
"""

import itertools
import math

C = {
    "fundo": "#15171b",
    "painel": "#1c1f24",
    "linha": "#2a2e35",
    "texto": "#dfe2e7",
    "fraco": "#7d8490",
    "apagado": "#3a3f47",
    "tela_borda": "#060709",
    "tela": "#0a0f15",
    "grade": "#16212c",
    "grade_forte": "#22313f",
    "ciano": "#38bdf8",
    "verde": "#22c55e",
    "laranja": "#f59e0b",
    "vermelho": "#ef4444",
    "roxo": "#a78bfa",
    "azul": "#3b82f6",
}
FONTE = "Segoe UI"
_ids = itertools.count()


def escurecer(cor, fator):
    r, g, b = (int(cor[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (int(r * fator), int(g * fator), int(b * fator))


def _dica(canvas, texto):
    """Mostra a dica na barra de baixo (a janela define canvas.dica)."""
    getattr(canvas, "dica", lambda _t: None)(texto)


def registrar_roda(canvas, tag, funcao):
    """O Tk não deixa ligar a roda do mouse a itens do Canvas: guardamos aqui e a
    janela repassa o evento para o item que estiver embaixo do cursor."""
    if not hasattr(canvas, "rodas"):
        canvas.rodas = {}

        def despachar(e):
            for t in canvas.gettags("current"):
                if t in canvas.rodas:
                    canvas.rodas[t](e)
                    return

        canvas.bind("<MouseWheel>", despachar)
    canvas.rodas[tag] = funcao


def ret_arredondado(c, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
           x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


class _Controle:
    """Base: valor numérico com faixa, padrão, callback e dica."""

    def __init__(self, canvas, de, ate, valor, padrao, ao_mudar, formato, dica, passo):
        self.c = canvas
        self.de, self.ate = de, ate
        self.padrao = padrao
        self.ao_mudar = ao_mudar
        self.formato = formato
        self.dica = dica
        self.passo = passo
        self.tag = f"w{next(_ids)}"
        self.valor = min(max(valor, de), ate)
        self.ativo = True

    def _fracao(self):
        return (self.valor - self.de) / (self.ate - self.de)

    def definir(self, valor, avisar=False):
        valor = min(max(valor, self.de), self.ate)
        if self.passo:
            valor = round(valor / self.passo) * self.passo
        if valor == self.valor:
            return
        self.valor = valor
        self.desenhar()
        if avisar and self.ao_mudar:
            self.ao_mudar(valor)

    def _ligar_eventos(self, alvo, vertical=True, escala_px=200):
        estado = {}

        def inicio(e):
            estado.update(y=e.y, x=e.x, v=self.valor)

        def arrastar(e):
            if not self.ativo or "v" not in estado:
                return
            delta = (estado["y"] - e.y) if vertical else (e.x - estado["x"])
            fino = 0.25 if e.state & 0x0001 else 1.0  # Shift = ajuste fino
            self.definir(estado["v"] + delta / escala_px * (self.ate - self.de) * fino, avisar=True)

        def roda(e):
            if self.ativo:
                p = self.passo or (self.ate - self.de) / 100
                self.definir(self.valor + (p if e.delta > 0 else -p), avisar=True)

        def duplo(_e):
            if self.ativo and self.padrao is not None:
                self.definir(self.padrao, avisar=True)

        self.c.tag_bind(alvo, "<ButtonPress-1>", inicio)
        self.c.tag_bind(alvo, "<B1-Motion>", arrastar)
        registrar_roda(self.c, alvo, roda)
        self.c.tag_bind(alvo, "<Double-Button-1>", duplo)
        if self.dica:
            self.c.tag_bind(alvo, "<Enter>", lambda _e: _dica(self.c, self.dica))
            self.c.tag_bind(alvo, "<Leave>", lambda _e: _dica(self.c, ""))
        self.c.tag_bind(alvo, "<Enter>", lambda _e: self.c.configure(cursor="hand2"), add="+")
        self.c.tag_bind(alvo, "<Leave>", lambda _e: self.c.configure(cursor=""), add="+")


class Knob(_Controle):
    def __init__(self, canvas, x, y, rotulo, de, ate, valor, ao_mudar, formato=lambda v: f"{v:.0f}",
                 padrao=None, raio=19, cor=None, bipolar=False, anel_led=False, dica="", passo=None):
        super().__init__(canvas, de, ate, valor, padrao, ao_mudar, formato, dica, passo)
        self.x, self.y, self.r = x, y, raio
        self.cor = cor or C["ciano"]
        self.bipolar = bipolar
        self.anel_led = anel_led
        c, t, r = canvas, self.tag, raio
        if anel_led:
            self._leds = []
            for i in range(25):
                a = math.radians(225 - 270 * i / 24)
                rr = r + 13
                px, py = x + rr * math.cos(a), y - rr * math.sin(a)
                self._leds.append(c.create_oval(px - 2.6, py - 2.6, px + 2.6, py + 2.6, fill=C["apagado"], width=0, tags=t))
        else:
            c.create_arc(x - r - 7, y - r - 7, x + r + 7, y + r + 7, start=225, extent=-270, style="arc",
                         outline=C["apagado"], width=3, tags=t)
            self._arco = c.create_arc(x - r - 7, y - r - 7, x + r + 7, y + r + 7, start=225, extent=0,
                                      style="arc", outline=self.cor, width=3, tags=t)
        c.create_oval(x - r - 2, y - r + 1, x + r + 2, y + r + 4, fill="#08090b", width=0, tags=t)  # sombra
        c.create_oval(x - r, y - r, x + r, y + r, fill="#2b2e34", outline="#0e0f12", width=1, tags=t)
        if anel_led:  # serrilhado do knob grande
            for i in range(36):
                a = math.radians(i * 10)
                c.create_line(x + (r - 1) * math.cos(a), y + (r - 1) * math.sin(a),
                              x + (r - 6) * math.cos(a), y + (r - 6) * math.sin(a), fill="#1c1e22", tags=t)
        ri = r * 0.78
        c.create_oval(x - ri, y - ri, x + ri, y + ri, fill="#35393f", outline="#41454c", tags=t)
        self._ponteiro = c.create_line(x, y, x, y - ri, fill="#f1f3f5", width=2.5 if r < 30 else 4,
                                       capstyle="round", tags=t)
        self._rotulo = c.create_text(x, y + r + (22 if anel_led else 15), text=rotulo, fill=C["fraco"],
                                     font=(FONTE, 8, "bold"), tags=t)
        self._texto = c.create_text(x, y + r + (36 if anel_led else 28), text="", fill=C["texto"],
                                    font=(FONTE, 8), tags=t)
        self._ligar_eventos(t)
        self.desenhar()

    def desenhar(self):
        f = self._fracao()
        a = math.radians(225 - 270 * f)
        ri = self.r * 0.78
        self.c.coords(self._ponteiro, self.x + ri * 0.3 * math.cos(a), self.y - ri * 0.3 * math.sin(a),
                      self.x + ri * 0.92 * math.cos(a), self.y - ri * 0.92 * math.sin(a))
        cor = self.cor if self.ativo else C["apagado"]
        if self.anel_led:
            acesos = round(f * 24)
            for i, led in enumerate(self._leds):
                self.c.itemconfigure(led, fill=cor if i <= acesos else C["apagado"])
        elif self.bipolar:
            meio = -(self.de) / (self.ate - self.de)
            self.c.itemconfigure(self._arco, start=225 - 270 * meio, extent=-270 * (f - meio), outline=cor)
        else:
            self.c.itemconfigure(self._arco, extent=-270 * f, outline=cor)
        self.c.itemconfigure(self._texto, text=self.formato(self.valor))

    def habilitar(self, ativo):
        self.ativo = ativo
        self.c.itemconfigure(self._rotulo, fill=C["fraco"] if ativo else C["apagado"])
        self.c.itemconfigure(self._texto, fill=C["texto"] if ativo else C["apagado"])
        self.desenhar()


class Fader(_Controle):
    def __init__(self, canvas, x, y_topo, altura, rotulo, de, ate, valor, ao_mudar, marcas,
                 formato=lambda v: f"{v:.0f}", padrao=None, cor_tampa="#c9cdd2", dica="", passo=None):
        super().__init__(canvas, de, ate, valor, padrao, ao_mudar, formato, dica, passo)
        self.x, self.y0, self.h = x, y_topo, altura
        c, t = canvas, self.tag
        # área de clique do trilho (com cor: retângulo vazio só recebe clique na borda)
        self._zona = c.create_rectangle(x - 20, y_topo - 10, x + 20, y_topo + altura + 10, outline="",
                                        fill=C["painel"], tags=t)
        for v in marcas:
            yy = self._y(v)
            c.create_line(x - 22, yy, x - 12, yy, fill=C["fraco"], tags=t)
            c.create_text(x - 26, yy, text=f"{v:+.0f}" if v else "0", anchor="e", fill=C["fraco"],
                          font=(FONTE, 7), tags=t)
            c.create_line(x + 12, yy, x + 18, yy, fill=C["linha"], tags=t)
        ret_arredondado(c, x - 4, y_topo - 6, x + 4, y_topo + altura + 6, 3, fill="#050607", outline="#2b2f36", tags=t)
        tw = 17
        self._tampa = [
            ret_arredondado(c, 0, 0, 1, 1, 3, fill="#08090b", tags=t),  # sombra
            ret_arredondado(c, 0, 0, 1, 1, 3, fill=cor_tampa, outline="#16181b", tags=t),
            c.create_rectangle(0, 0, 1, 1, fill=escurecer(cor_tampa, 0.82), width=0, tags=t),
            c.create_line(0, 0, 1, 1, fill="#ffffff", width=2, tags=t),
        ]
        self._tw = tw
        self._rotulo = c.create_text(x, y_topo + altura + 22, text=rotulo, fill=C["fraco"], font=(FONTE, 8, "bold"), tags=t)
        self._texto = c.create_text(x, y_topo - 20, text="", fill=C["texto"], font=(FONTE, 8, "bold"), tags=t)
        self._ligar_eventos(t, escala_px=altura)

        def clicar_trilho(e):
            if self.ativo and abs(e.y - self._y(self.valor)) > 12:
                self.definir(self._valor_em(e.y), avisar=True)

        c.tag_bind(self._zona, "<ButtonPress-1>", clicar_trilho, add="+")
        self.desenhar()

    def _y(self, v):
        return self.y0 + self.h * (1 - (v - self.de) / (self.ate - self.de))

    def _valor_em(self, y):
        return self.de + (1 - (y - self.y0) / self.h) * (self.ate - self.de)

    def desenhar(self):
        yy, x, tw = self._y(self.valor), self.x, self._tw
        sombra, corpo, faixa, linha = self._tampa
        self.c.coords(sombra, *self._pontos(x - tw + 1, yy - 12 + 3, x + tw + 1, yy + 12 + 3))
        self.c.coords(corpo, *self._pontos(x - tw, yy - 12, x + tw, yy + 12))
        self.c.coords(faixa, x - tw + 2, yy + 2, x + tw - 2, yy + 10)
        self.c.coords(linha, x - tw + 3, yy, x + tw - 3, yy)
        self.c.itemconfigure(self._texto, text=self.formato(self.valor),
                             fill=C["texto"] if self.ativo else C["apagado"])

    @staticmethod
    def _pontos(x1, y1, x2, y2, r=3):
        return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
                x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]

    def habilitar(self, ativo):
        self.ativo = ativo
        self.c.itemconfigure(self._rotulo, fill=C["fraco"] if ativo else C["apagado"])
        self.desenhar()


class BotaoLed:
    def __init__(self, canvas, x, y, texto, ligado, ao_mudar, cor=None, largura=62, altura=26, dica=""):
        self.c = canvas
        self.ligado = ligado
        self.ao_mudar = ao_mudar
        self.cor = cor or C["verde"]
        self.tag = f"w{next(_ids)}"
        t = self.tag
        x1, y1, x2, y2 = x - largura / 2, y - altura / 2, x + largura / 2, y + altura / 2
        ret_arredondado(canvas, x1, y1 + 2, x2, y2 + 2, 5, fill="#07080a", tags=t)
        self._brilho = ret_arredondado(canvas, x1 - 2, y1 - 2, x2 + 2, y2 + 2, 7, fill="", outline="", width=2, tags=t)
        self._corpo = ret_arredondado(canvas, x1, y1, x2, y2, 5, fill="#2b2f36", outline="#101114", tags=t)
        self._led = canvas.create_rectangle(x1 + 8, y1 + 4, x2 - 8, y1 + 7, width=0, tags=t)
        self._texto = canvas.create_text(x, y + 3, text=texto, font=(FONTE, 8, "bold"), tags=t)
        canvas.tag_bind(t, "<ButtonRelease-1>", lambda _e: self.alternar())
        if dica:
            canvas.tag_bind(t, "<Enter>", lambda _e: _dica(canvas, dica))
            canvas.tag_bind(t, "<Leave>", lambda _e: _dica(canvas, ""))
        canvas.tag_bind(t, "<Enter>", lambda _e: canvas.configure(cursor="hand2"), add="+")
        canvas.tag_bind(t, "<Leave>", lambda _e: canvas.configure(cursor=""), add="+")
        self.desenhar()

    def alternar(self):
        self.definir(not self.ligado)
        if self.ao_mudar:
            self.ao_mudar(self.ligado)

    def definir(self, ligado):
        self.ligado = ligado
        self.desenhar()

    def desenhar(self):
        if self.ligado:
            self.c.itemconfigure(self._corpo, fill=escurecer(self.cor, 0.30))
            self.c.itemconfigure(self._led, fill=self.cor)
            self.c.itemconfigure(self._texto, fill=self.cor)
            self.c.itemconfigure(self._brilho, outline=escurecer(self.cor, 0.45))
        else:
            self.c.itemconfigure(self._corpo, fill="#2b2f36")
            self.c.itemconfigure(self._led, fill="#1b1d21")
            self.c.itemconfigure(self._texto, fill=C["fraco"])
            self.c.itemconfigure(self._brilho, outline="")


class MedidorLed:
    """Medidor vertical segmentado (-60..0 dB) com memória de pico."""

    def __init__(self, canvas, x, y_topo, altura, largura=8, segmentos=24, rotulo=""):
        self.c = canvas
        self.seg = []
        self.cores = []
        passo = altura / segmentos
        for i in range(segmentos):
            limite = -60 + 60 * (i + 1) / segmentos
            cor = C["verde"] if limite <= -12 else C["laranja"] if limite <= -4 else C["vermelho"]
            y2 = y_topo + altura - i * passo
            self.seg.append(canvas.create_rectangle(x, y2 - passo + 1.5, x + largura, y2, width=0,
                                                    fill=escurecer(cor, 0.22)))
            self.cores.append(cor)
        self.apagadas = [escurecer(cor, 0.22) for cor in self.cores]
        self.n = segmentos
        self._estado = [False] * segmentos  # o que está pintado agora
        self._pico = 0
        self._pico_t = 0
        self._valor = -100.0
        if rotulo:
            canvas.create_text(x + largura / 2, y_topo + altura + 12, text=rotulo, fill=C["fraco"], font=(FONTE, 7, "bold"))

    def mostrar(self, db):
        self._valor = db if db > self._valor else max(db, self._valor - 1.2)
        acesos = int(max(0, min(self.n, (self._valor + 60) / 60 * self.n)))
        if acesos >= self._pico:
            self._pico, self._pico_t = acesos, 20
        elif self._pico_t > 0:
            self._pico_t -= 1
        else:
            self._pico -= 1
        # só repinta os segmentos que mudaram (cada repintura custa CPU no Tk)
        for i, s in enumerate(self.seg):
            aceso = i < acesos or i == self._pico - 1
            if aceso != self._estado[i]:
                self._estado[i] = aceso
                self.c.itemconfigure(s, fill=self.cores[i] if aceso else self.apagadas[i])
