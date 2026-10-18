"""Liga o microfone real ao cabo virtual passando pelo Processador.

O microfone e o cabo têm relógios diferentes, então cada saída tem sua própria
fila: guarda ~30 ms antes de tocar e descarta o excesso se a fila crescer demais.
"""

import threading

import numpy as np
import sounddevice as sd

from . import dispositivos
from .processador import QUADRO, TAXA, Processador

ALVO = 3 * QUADRO  # 30 ms guardados antes de começar a tocar
MAXIMO = 12 * QUADRO  # acima de 120 ms na fila, volta para o ALVO


def _wasapi():
    return sd.WasapiSettings(auto_convert=True)


class Fila:
    """Buffer circular de amostras float32, seguro entre as threads de áudio."""

    def __init__(self, capacidade=TAXA):
        self._buf = np.zeros(capacidade, dtype=np.float32)
        self._cap = capacidade
        self._ini = 0
        self._n = 0
        self._trava = threading.Lock()

    def __len__(self):
        return self._n

    def escrever(self, x):
        with self._trava:
            n = len(x)
            if n >= self._cap:
                x = x[-self._cap:]
                n = self._cap
            excesso = self._n + n - self._cap
            if excesso > 0:
                self._ini = (self._ini + excesso) % self._cap
                self._n -= excesso
            fim = (self._ini + self._n) % self._cap
            p1 = min(n, self._cap - fim)
            self._buf[fim:fim + p1] = x[:p1]
            self._buf[:n - p1] = x[p1:]
            self._n += n

    def ler(self, n, destino):
        """Copia até n amostras para destino e devolve quantas copiou."""
        with self._trava:
            k = min(n, self._n)
            p1 = min(k, self._cap - self._ini)
            destino[:p1] = self._buf[self._ini:self._ini + p1]
            destino[p1:k] = self._buf[:k - p1]
            self._ini = (self._ini + k) % self._cap
            self._n -= k
            return k

    def descartar(self, n):
        with self._trava:
            n = min(n, self._n)
            self._ini = (self._ini + n) % self._cap
            self._n -= n


class Saida:
    def __init__(self, nome):
        idx = dispositivos.indice(nome, "saida")
        if idx is None:
            raise RuntimeError(f"Saída não encontrada: {nome}")
        self.nome = nome
        self.canais = min(2, sd.query_devices(idx)["max_output_channels"])
        self.fila = Fila()
        self.faltas = 0
        self.descartes = 0
        self._enchendo = True
        self._tmp = np.zeros(QUADRO * 4, dtype=np.float32)
        self.stream = sd.OutputStream(
            device=idx, samplerate=TAXA, blocksize=QUADRO, channels=self.canais,
            dtype="float32", latency="low", extra_settings=_wasapi(), callback=self._cb,
        )

    def _cb(self, outdata, frames, tempo, status):
        fila = self.fila
        if self._enchendo:
            if len(fila) < ALVO:
                outdata.fill(0)
                return
            self._enchendo = False
        if len(fila) > MAXIMO:
            fila.descartar(len(fila) - ALVO)
            self.descartes += 1
        if frames > len(self._tmp):
            self._tmp = np.zeros(frames, dtype=np.float32)
        tmp = self._tmp[:frames]
        k = fila.ler(frames, tmp)
        if k < frames:
            tmp[k:] = 0
            self._enchendo = True
            self.faltas += 1
        outdata[:] = tmp[:, None]

    def iniciar(self):
        self.stream.start()

    def fechar(self):
        self.stream.stop(ignore_errors=True)
        self.stream.close(ignore_errors=True)


class Motor:
    def __init__(self, cfg):
        self.cfg = cfg
        self.proc = None
        self.entrada_nome = ""
        self.erro = None
        self._entrada = None
        self._cabo = None
        self._ouvir = None
        self._acum = Fila(QUADRO * 16)
        self._quadro = np.zeros(QUADRO, dtype=np.float32)

    @property
    def ativo(self):
        return self._entrada is not None

    def ligar(self):
        self.desligar()
        cfg = self.cfg
        entrada = cfg.entrada or dispositivos.microfone_sugerido()
        saida = cfg.saida or dispositivos.cabo_sugerido()
        if not saida:
            raise RuntimeError("VB-CABLE não encontrado. Instale o driver e clique em Atualizar.")
        if "CABLE Output" in entrada:
            raise RuntimeError("O microfone não pode ser o próprio CABLE Output (viraria um loop).")
        idx = dispositivos.indice(entrada, "entrada")
        if idx is None:
            raise RuntimeError(f"Microfone não encontrado: {entrada or '(nenhum)'}")

        self.erro = None
        self.proc = Processador(cfg)
        self._acum = Fila(QUADRO * 16)
        try:
            self._cabo = Saida(saida)
            if cfg.ouvir:
                self._ouvir = Saida(cfg.saida_ouvir or dispositivos.alto_falante_sugerido())
            self._entrada = self._abrir_entrada(idx)
            self._cabo.iniciar()
            if self._ouvir:
                self._ouvir.iniciar()
            self._entrada.start()
        except Exception:
            self.desligar()
            raise
        self.entrada_nome = entrada

    def _abrir_entrada(self, idx):
        opcoes = dict(device=idx, samplerate=TAXA, blocksize=QUADRO, dtype="float32",
                      latency="low", extra_settings=_wasapi(), callback=self._cb_entrada)
        try:
            return sd.InputStream(channels=1, **opcoes)
        except sd.PortAudioError:
            canais = min(2, sd.query_devices(idx)["max_input_channels"])
            return sd.InputStream(channels=canais, **opcoes)

    def _cb_entrada(self, indata, frames, tempo, status):
        try:
            mono = indata[:, 0] if indata.shape[1] == 1 else indata.mean(axis=1)
            self._acum.escrever(mono)
            while len(self._acum) >= QUADRO:
                self._acum.ler(QUADRO, self._quadro)
                y = self.proc.processar(self._quadro)
                self._cabo.fila.escrever(y)
                ouvir = self._ouvir
                if ouvir is not None:
                    ouvir.fila.escrever(y)
        except Exception as e:  # nunca derrubar a thread de áudio
            self.erro = f"{type(e).__name__}: {e}"

    def definir_ouvir(self, ligado):
        """Liga/desliga o retorno nos alto-falantes sem parar o microfone."""
        if not self.ativo:
            return
        if ligado and self._ouvir is None:
            s = Saida(self.cfg.saida_ouvir or dispositivos.alto_falante_sugerido())
            s.iniciar()
            self._ouvir = s
        elif not ligado and self._ouvir is not None:
            s, self._ouvir = self._ouvir, None
            s.fechar()

    def saudavel(self):
        if not self.ativo:
            return True
        return self._entrada.active and self._cabo.stream.active and self.erro is None

    def latencia_ms(self):
        if not self.ativo:
            return 0
        return round((self._entrada.latency + self._cabo.stream.latency) * 1000 + ALVO * 1000 / TAXA + 10)

    def desligar(self):
        entrada, self._entrada = self._entrada, None
        if entrada is not None:
            entrada.stop(ignore_errors=True)
            entrada.close(ignore_errors=True)
        for nome in ("_ouvir", "_cabo"):
            s = getattr(self, nome)
            setattr(self, nome, None)
            if s is not None:
                s.fechar()
        if self.proc is not None:
            self.proc.fechar()
            self.proc = None
