"""Equalizador: bandas no estilo "cookbook" (RBJ) transformadas em um filtro FIR
de fase mínima, aplicado por FFT. Fase mínima = quase sem atraso extra, e a
curva desenhada na tela é exatamente a mesma que vai para o áudio.
"""

import numpy as np

TAXA = 48000
N_PROJETO = 8192  # resolução usada para calcular o filtro (5,9 Hz por ponto)
TAPS = 2048  # tamanho do filtro final (43 ms de resposta: precisa disso para graves)
N_FFT = 4096  # FFT do overlap-save: cabe quadro de 480 + filtro de 2048

TIPOS = ("passa_alta", "grave", "pico", "agudo")


def bandas_padrao():
    return [
        {"nome": "CORTE", "tipo": "passa_alta", "freq": 80.0, "ganho": 0.0, "q": 0.707},
        {"nome": "GRAVE", "tipo": "grave", "freq": 150.0, "ganho": 0.0, "q": 0.707},
        {"nome": "MÉDIO", "tipo": "pico", "freq": 800.0, "ganho": 0.0, "q": 1.0},
        {"nome": "PRESENÇA", "tipo": "pico", "freq": 3500.0, "ganho": 0.0, "q": 1.0},
        {"nome": "AGUDO", "tipo": "agudo", "freq": 9000.0, "ganho": 0.0, "q": 0.707},
    ]


def coeficientes(banda):
    """(b0, b1, b2, a0, a1, a2) de uma banda."""
    f0 = min(max(banda["freq"], 10.0), TAXA * 0.45)
    w0 = 2 * np.pi * f0 / TAXA
    c, s = np.cos(w0), np.sin(w0)
    alfa = s / (2 * max(banda["q"], 0.1))
    a = 10 ** (banda["ganho"] / 40)
    tipo = banda["tipo"]
    if tipo == "passa_alta":
        return (1 + c) / 2, -(1 + c), (1 + c) / 2, 1 + alfa, -2 * c, 1 - alfa
    if tipo == "pico":
        return 1 + alfa * a, -2 * c, 1 - alfa * a, 1 + alfa / a, -2 * c, 1 - alfa / a
    ra = np.sqrt(a)
    if tipo == "grave":
        return (a * ((a + 1) - (a - 1) * c + 2 * ra * alfa), 2 * a * ((a - 1) - (a + 1) * c),
                a * ((a + 1) - (a - 1) * c - 2 * ra * alfa), (a + 1) + (a - 1) * c + 2 * ra * alfa,
                -2 * ((a - 1) + (a + 1) * c), (a + 1) + (a - 1) * c - 2 * ra * alfa)
    if tipo == "agudo":
        return (a * ((a + 1) + (a - 1) * c + 2 * ra * alfa), -2 * a * ((a - 1) + (a + 1) * c),
                a * ((a + 1) + (a - 1) * c - 2 * ra * alfa), (a + 1) - (a - 1) * c + 2 * ra * alfa,
                2 * ((a - 1) - (a + 1) * c), (a + 1) - (a - 1) * c - 2 * ra * alfa)
    raise ValueError(f"tipo de banda desconhecido: {tipo}")


def resposta_db(bandas, freqs):
    """Ganho total (dB) do EQ em cada frequência — usado pelo gráfico e pelo filtro."""
    z = np.exp(-1j * 2 * np.pi * np.asarray(freqs, dtype=float) / TAXA)
    h = np.ones_like(z)
    for banda in bandas:
        b0, b1, b2, a0, a1, a2 = coeficientes(banda)
        h *= (b0 + b1 * z + b2 * z * z) / (a0 + a1 * z + a2 * z * z)
    return 20 * np.log10(np.maximum(np.abs(h), 1e-9))


def filtro_fft(bandas):
    """Espectro (rfft de N_FFT pontos) do FIR de fase mínima que reproduz as bandas."""
    freqs = np.fft.rfftfreq(N_PROJETO, 1 / TAXA)
    # Piso de -60 dB: o corte de graves vai a -180 dB em 0 Hz e isso estraga o
    # cálculo de fase mínima (o cepstro "dá a volta" e entorta os graves).
    log_mag = np.maximum(resposta_db(bandas, freqs), -60.0) * (np.log(10) / 20)
    cep = np.fft.irfft(log_mag, N_PROJETO)
    dobra = np.zeros(N_PROJETO)
    dobra[0] = 1
    dobra[1:N_PROJETO // 2] = 2
    dobra[N_PROJETO // 2] = 1
    h = np.fft.irfft(np.exp(np.fft.rfft(cep * dobra)), N_PROJETO)[:TAPS]
    h[-512:] *= np.hanning(1024)[512:]  # suaviza o fim para não estalar
    return np.fft.rfft(h, N_FFT).astype(np.complex64)


class Equalizador:
    """Aplica o filtro em quadros de 480 amostras (overlap-save)."""

    def __init__(self, bandas):
        self._hist = np.zeros(N_FFT, dtype=np.float32)
        self._h = filtro_fft(bandas)

    def atualizar(self, bandas):
        self._h = filtro_fft(bandas)  # troca atômica: a thread de áudio pega o novo no próximo quadro

    def processar(self, x):
        n = len(x)
        self._hist[:-n] = self._hist[n:]
        self._hist[-n:] = x
        y = np.fft.irfft(np.fft.rfft(self._hist) * self._h, N_FFT)
        return y[-n:].astype(np.float32)
