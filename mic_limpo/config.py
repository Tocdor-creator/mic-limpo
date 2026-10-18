"""Preferências do Mic Limpo, salvas em %APPDATA%\\MicLimpo\\config.json."""

import json
import os
from dataclasses import asdict, dataclass, field, fields

from .eq import bandas_padrao

PASTA = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "MicLimpo")
ARQUIVO = os.path.join(PASTA, "config.json")


@dataclass
class Config:
    entrada: str = ""  # nome do microfone real ("" = escolher sozinho)
    saida: str = ""  # nome do cabo virtual ("" = CABLE Input)
    mudo: bool = False
    remover_ruido: bool = True
    silenciar_pausas: bool = True
    sensibilidade: float = 50.0  # 0..100: quão fácil o silenciador abre
    portao_limiar_db: float = -60.0  # e só abre se a voz (já nivelada) passar deste nível
    nivelar: bool = True
    alvo_db: float = -24.0  # volume médio desejado da voz (dBFS RMS)
    ganho_max_db: float = 36.0  # quanto o nivelador pode aumentar no máximo
    ganho_manual_db: float = 0.0  # usado quando o nivelador está desligado
    ganho_aprendido_db: float = 0.0  # último ganho do nivelador, para não recomeçar do zero
    eq_ligado: bool = True
    eq: list = field(default_factory=bandas_padrao)
    comp_ligado: bool = True
    comp_limiar_db: float = -18.0
    comp_razao: float = 3.0
    mixer_ligado: bool = True  # controlar volume de jogo × chat pelo mixer do Windows
    vol_chat: float = 100.0  # 0..100 (%)
    vol_jogo: float = 100.0
    ouvir: bool = False  # tocar o resultado nos alto-falantes para testar
    saida_ouvir: str = ""  # onde tocar ("" = alto-falante padrão)
    ligar_ao_abrir: bool = True


def _eq_valido(eq):
    padrao = bandas_padrao()
    if not isinstance(eq, list) or len(eq) != len(padrao):
        return False
    return all(isinstance(b, dict) and b.get("tipo") == p["tipo"] and
               all(isinstance(b.get(k), (int, float)) for k in ("freq", "ganho", "q"))
               for b, p in zip(eq, padrao))


def carregar():
    try:
        with open(ARQUIVO, encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return Config()
    nomes = {f.name for f in fields(Config)}
    cfg = Config(**{k: v for k, v in dados.items() if k in nomes})
    if not _eq_valido(cfg.eq):
        cfg.eq = bandas_padrao()
    return cfg


def salvar(cfg):
    os.makedirs(PASTA, exist_ok=True)
    tmp = ARQUIVO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=2, ensure_ascii=False)
    os.replace(tmp, ARQUIVO)
