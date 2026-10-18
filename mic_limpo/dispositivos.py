"""Lista os dispositivos WASAPI e escolhe microfone real, cabo virtual e alto-falante."""

import sounddevice as sd

VIRTUAIS = ("CABLE", "VB-Audio", "Steam Streaming", "Sonar", "Voicemeeter")
EMBUTIDOS = ("Grupo de microfones", "Microphone Array", "Realtek", "Intel")


def recarregar():
    """Relê a lista do Windows (ex.: depois de plugar um mic ou instalar o VB-CABLE)."""
    sd._terminate()
    sd._initialize()


def _wasapi():
    for i, api in enumerate(sd.query_hostapis()):
        if "WASAPI" in api["name"]:
            return i, api
    raise RuntimeError("WASAPI não encontrado")


def _lista(tipo):
    _, api = _wasapi()
    devs = sd.query_devices()
    chave = "max_input_channels" if tipo == "entrada" else "max_output_channels"
    return [(i, devs[i]["name"]) for i in api["devices"] if devs[i][chave] > 0]


def entradas():
    return [nome for _, nome in _lista("entrada")]


def saidas():
    return [nome for _, nome in _lista("saida")]


def indice(nome, tipo):
    for i, n in _lista(tipo):
        if n == nome:
            return i
    return None


def virtual(nome):
    return any(v.lower() in nome.lower() for v in VIRTUAIS)


def _padrao(tipo):
    _, api = _wasapi()
    i = api["default_input_device" if tipo == "entrada" else "default_output_device"]
    return sd.query_devices(i)["name"] if i >= 0 else None


def microfone_sugerido():
    nomes = [n for n in entradas() if not virtual(n)]
    padrao = _padrao("entrada")
    if padrao in nomes:
        return padrao
    externos = [n for n in nomes if not any(e.lower() in n.lower() for e in EMBUTIDOS)]
    return (externos or nomes or [""])[0]


def cabo_sugerido():
    for n in saidas():
        if "CABLE Input" in n:
            return n
    return ""


def alto_falante_sugerido():
    nomes = [n for n in saidas() if not virtual(n)]
    padrao = _padrao("saida")
    if padrao in nomes:
        return padrao
    return (nomes or [""])[0]
