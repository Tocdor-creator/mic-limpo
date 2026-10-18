"""Testa o controle de volume por app usando uma sessão de áudio do próprio
teste (toca silêncio no alto-falante padrão). Não mexe no volume de outros apps.

Rodar com: .venv\\Scripts\\python.exe testes\\teste_mixer.py
"""

import ctypes
import os
import sys
import time

import sounddevice as sd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mic_limpo import dispositivos, mixer  # noqa: E402

falhas = []


def conferir(nome, ok, detalhe):
    print(f"[{'OK ' if ok else 'FALHOU'}] {nome}: {detalhe}")
    if not ok:
        falhas.append(nome)


def memoria_mb():
    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faltas", ctypes.c_ulong)] + [(f"c{i}", ctypes.c_size_t) for i in range(9)]
    k = ctypes.WinDLL("kernel32")
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong]
    c = PMC()
    c.cb = ctypes.sizeof(c)
    k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.c8 / 2 ** 20  # PrivateUsage


m = mixer.Mixer(incluir_proprio=True)
alto = dispositivos.alto_falante_sugerido()
with sd.OutputStream(device=dispositivos.indice(alto, "saida"), samplerate=48000, channels=2,
                     extra_settings=sd.WasapiSettings(auto_convert=True)):
    time.sleep(0.5)
    m.atualizar()
    proprias = [s for s in m._sessoes if s.instancia and "python" in s.nome.lower()]
    conferir("acha a sessão do próprio teste", len(proprias) >= 1,
             f"{len(m._sessoes)} sessões; chat={m.apps_chat} jogo={m.apps_jogo}")
    if proprias:
        s = proprias[0]
        original = s.ler_volume()
        s.definir_volume(0.42)
        conferir("muda o volume do app", abs(s.ler_volume() - 0.42) < 0.01, f"{original:.2f} -> {s.ler_volume():.2f}")
        s.definir_volume(original)
        conferir("devolve o volume", abs(s.ler_volume() - original) < 0.01, f"voltou para {s.ler_volume():.2f}")

    # Atualizar várias vezes não pode vazar memória (o app faz isso a cada 2 s)
    for _ in range(50):
        m.atualizar()
        m.picos()
    antes = memoria_mb()
    for _ in range(300):
        m.atualizar()
        m.picos()
    depois = memoria_mb()
    conferir("300 leituras sem vazar", depois - antes < 2, f"memória {antes:.1f} -> {depois:.1f} MB")

nome, vol = m.volume_geral()
conferir("lê o volume geral", 0.0 <= vol <= 1.0, f"{nome}: {vol * 100:.0f}%")

print()
print("TUDO CERTO" if not falhas else f"{len(falhas)} falha(s): {', '.join(falhas)}")
sys.exit(1 if falhas else 0)
