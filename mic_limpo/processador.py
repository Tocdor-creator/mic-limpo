"""Cadeia de efeitos aplicada a cada quadro de 10 ms do microfone.

Ordem: supressão de ruído (RNNoise) -> EQ -> nivelador automático -> portão
(silenciar entre falas) -> compressor -> limitador -> mudo.
Tudo em float32 mono, 48 kHz, quadros de 480.
"""

import ctypes
import importlib.util
import math
import os

import numpy as np

from .eq import Equalizador

TAXA = 48000
QUADRO = 480  # 10 ms, tamanho fixo exigido pelo RNNoise

_RAMPA = np.arange(QUADRO, dtype=np.float32) / QUADRO
_BLOCO_LIM = 48  # 1 ms: tamanho do bloco que o limitador analisa
_BLOCOS = QUADRO // _BLOCO_LIM
_RAMPA_BLOCO = np.arange(_BLOCO_LIM, dtype=np.float32) / _BLOCO_LIM
_SOLTAR_BLOCO = 10 ** (0.01 / 20)  # limitador solta ~10 dB/s

TETO = 0.89  # -1 dBFS: o limitador segura os picos aqui
TETO_DB = 20 * math.log10(TETO)
PISO_PORTAO = 10 ** (-50 / 20)  # quanto o silenciador abaixa nas pausas
SEGURAR_QUADROS = 25  # mantém o portão aberto 250 ms depois da última sílaba
ESPECTRO = 4096  # amostras guardadas para o analisador de espectro da tela


def _carregar_rnnoise():
    # Usa só o rnnoise.dll que vem no pacote pyrnnoise. Importar o pacote em si
    # puxa FFmpeg e matplotlib (~200 MB de RAM) sem necessidade.
    pasta = importlib.util.find_spec("pyrnnoise").submodule_search_locations[0]
    lib = ctypes.CDLL(os.path.join(pasta, "rnnoise.dll"))
    lib.rnnoise_create.argtypes = [ctypes.c_void_p]
    lib.rnnoise_create.restype = ctypes.c_void_p
    lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
    lib.rnnoise_process_frame.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float),
                                          ctypes.POINTER(ctypes.c_float)]
    lib.rnnoise_process_frame.restype = ctypes.c_float
    assert lib.rnnoise_get_frame_size() == QUADRO
    return lib


_rn = _carregar_rnnoise()


def db(valor):
    return 20 * math.log10(max(valor, 1e-6))


def rms_db(x):
    return 10 * math.log10(float(np.dot(x, x)) / len(x) + 1e-12)


def limiar_da_sensibilidade(sensibilidade):
    """0..100 na tela -> probabilidade de voz exigida (0.9 rígido .. 0.1 abre fácil)."""
    return 0.9 - 0.8 * (max(0.0, min(100.0, sensibilidade)) / 100.0)


def curva_dinamica(cfg, entrada_db):
    """Curva estática entrada -> saída (dB) do portão + compressor + limitador.
    É a mesma conta que o áudio usa; o gráfico desenha isto."""
    x = np.asarray(entrada_db, dtype=float)
    y = x.copy()
    if cfg.comp_ligado:
        acima = x > cfg.comp_limiar_db
        y[acima] = cfg.comp_limiar_db + (x[acima] - cfg.comp_limiar_db) / max(cfg.comp_razao, 1.0)
    y = np.minimum(y, TETO_DB)
    if cfg.silenciar_pausas:
        y[x < cfg.portao_limiar_db] = -120.0
    return y


def _rampa(g0, g1):
    if g0 == g1:
        return np.full(QUADRO, g1, dtype=np.float32)
    return (g0 + (g1 - g0) * _RAMPA).astype(np.float32)


class Processador:
    def __init__(self, cfg):
        self.cfg = cfg
        self._estado = _rn.rnnoise_create(None)
        self._buf = np.zeros(QUADRO, dtype=np.float32)
        self._ptr = self._buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        self._eq = Equalizador(cfg.eq)

        # Começa do ganho que o nivelador já tinha aprendido na última vez
        self._ganho_db = min(cfg.ganho_aprendido_db, cfg.ganho_max_db) if cfg.nivelar else 0.0
        self._ganho_lin = 10 ** (self._ganho_db / 20)
        self._pot = 10 ** ((cfg.alvo_db - self._ganho_db) / 10)  # potência média da fala
        self._portao = 1.0
        self._segurar = 0
        self._comp_db = 0.0
        self._comp_lin = 1.0
        self._lim = 1.0

        # leituras para a janela
        self.entrada_db = -100.0
        self.saida_db = -100.0
        self.din_entrada_db = -100.0  # nível que chega no portão/compressor
        self.din_saida_db = -100.0
        self.prob_voz = 0.0
        self.falando = False
        self.espectro = np.zeros(ESPECTRO, dtype=np.float32)

    def fechar(self):
        if self._estado:
            _rn.rnnoise_destroy(self._estado)
            self._estado = None

    def atualizar_eq(self):
        self._eq.atualizar(self.cfg.eq)

    @property
    def ganho_db(self):
        return self._ganho_db

    @property
    def compressor_db(self):
        return self._comp_db

    @property
    def limitador_db(self):
        return db(self._lim)

    def processar(self, quadro, prob_forcada=None):
        cfg = self.cfg
        self.entrada_db = rms_db(quadro)

        # RNNoise sempre roda: mesmo com a supressão desligada, a
        # probabilidade de voz alimenta o silenciador e o nivelador.
        np.multiply(quadro, 32768.0, out=self._buf)
        prob = _rn.rnnoise_process_frame(self._estado, self._ptr, self._ptr)
        if prob_forcada is not None:
            prob = prob_forcada
        self.prob_voz = prob
        x = self._buf * (1.0 / 32768.0) if cfg.remover_ruido else quadro.astype(np.float32, copy=True)

        # EQ sempre recebe o áudio (o histórico fica certo ao religar)
        x_eq = self._eq.processar(x)
        if cfg.eq_ligado:
            x = x_eq

        # Nivelador: mede a fala (não o silêncio) e corrige o ganho aos poucos
        p = float(np.dot(x, x)) / QUADRO + 1e-12
        nivel = 10 * math.log10(p)
        if cfg.nivelar:
            # Voz mais baixa que (alvo - aumento máximo) é longe demais para ser
            # você (TV, alguém na sala): o nivelador ignora em vez de aumentar.
            perto = nivel >= cfg.alvo_db - cfg.ganho_max_db - 6
            if prob >= 0.6 and perto:
                a = 0.15 if p > self._pot else 0.06
                self._pot += a * (p - self._pot)
                desejado = min(max(cfg.alvo_db - 10 * math.log10(self._pot), -30.0), cfg.ganho_max_db)
                passo = desejado - self._ganho_db
                # abaixa rápido quando você grita, sobe devagar quando fala baixo
                passo = max(passo, -1.5) if passo < 0 else min(passo, 0.12)
                self._ganho_db += passo
            elif self._ganho_db > cfg.ganho_max_db:
                self._ganho_db = cfg.ganho_max_db
        else:
            passo = cfg.ganho_manual_db - self._ganho_db
            self._ganho_db += max(-1.0, min(1.0, passo))
        novo_ganho = 10 ** (self._ganho_db / 20)
        env = _rampa(self._ganho_lin, novo_ganho)
        self._ganho_lin = novo_ganho
        nivel_din = nivel + self._ganho_db
        self.din_entrada_db = nivel_din

        # Portão: abre com voz reconhecida E nível acima do limiar
        if prob >= limiar_da_sensibilidade(cfg.sensibilidade) and nivel_din >= cfg.portao_limiar_db:
            self._segurar = SEGURAR_QUADROS
        elif self._segurar > 0:
            self._segurar -= 1
        self.falando = self._segurar > 0
        alvo_portao = 1.0 if (not cfg.silenciar_pausas or self.falando) else PISO_PORTAO
        if alvo_portao >= self._portao:
            novo_portao = alvo_portao  # abre na hora (rampa de 10 ms)
        else:
            novo_portao = self._portao + (alvo_portao - self._portao) * 0.25  # fecha em ~100 ms
        env *= _rampa(self._portao, novo_portao)
        self._portao = novo_portao

        # Compressor: acima do limiar, cada X dB a mais viram 1 dB
        alvo_comp = 0.0
        if cfg.comp_ligado and nivel_din > cfg.comp_limiar_db:
            alvo_comp = (cfg.comp_limiar_db + (nivel_din - cfg.comp_limiar_db) / max(cfg.comp_razao, 1.0)) - nivel_din
        coef = 0.6 if alvo_comp < self._comp_db else 0.08  # ataque rápido, soltura ~120 ms
        self._comp_db += (alvo_comp - self._comp_db) * coef
        novo_comp = 10 ** (self._comp_db / 20)
        env *= _rampa(self._comp_lin, novo_comp)
        self._comp_lin = novo_comp

        y = x * env

        # Limitador com antecipação dentro do quadro: olha o pico de cada bloco
        # de 1 ms e já chega abaixado nele, em vez de cortar o começo do grito.
        picos = np.abs(y).reshape(_BLOCOS, _BLOCO_LIM).max(axis=1)
        exigido = np.minimum(1.0, TETO / np.maximum(picos, 1e-9))
        g = min(self._lim, exigido[0])
        pontos = [g]
        for b in range(_BLOCOS):
            proximo = exigido[b + 1] if b + 1 < _BLOCOS else 1.0
            g = min(g * _SOLTAR_BLOCO, exigido[b], proximo)
            pontos.append(g)
        pontos = np.asarray(pontos, dtype=np.float32)
        env_lim = pontos[:-1, None] + (pontos[1:] - pontos[:-1])[:, None] * _RAMPA_BLOCO[None, :]
        self._lim = float(pontos[-1])
        y *= env_lim.reshape(QUADRO)
        np.clip(y, -0.98, 0.98, out=y)  # só por segurança

        self.din_saida_db = rms_db(y)
        self.espectro[:-QUADRO] = self.espectro[QUADRO:]
        self.espectro[-QUADRO:] = y
        if cfg.mudo:
            y[:] = 0.0
        self.saida_db = rms_db(y)
        return y
