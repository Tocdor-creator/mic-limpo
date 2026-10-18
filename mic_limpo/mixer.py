"""Jogo × chat pelo mixer do Windows (Core Audio via ctypes, sem dependências).

Ajusta o volume de cada aplicativo como o "Mixer de volume" do Windows faz:
programas de chat (Discord etc.) seguem o knob CHAT e todo o resto segue o
knob JOGO. Também lê o pico de cada grupo e controla o volume geral.
Toda interface COM obtida é liberada pelo __del__ de _Com, para não vazar.
"""

import ctypes
import os
from ctypes import wintypes as w

_ole32 = ctypes.windll.ole32
_kernel32 = ctypes.windll.kernel32

CHAT = {"discord.exe", "discordptb.exe", "discordcanary.exe", "teamspeak.exe", "ts3client_win64.exe",
        "ms-teams.exe", "teams.exe", "skype.exe", "slack.exe", "zoom.exe", "mumble.exe", "guilded.exe"}
IGNORAR_DISPOSITIVOS = ("CABLE",)  # nunca mexer no caminho do microfone


class _GUID(ctypes.Structure):
    _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16), ("d3", ctypes.c_uint16),
                ("d4", ctypes.c_ubyte * 8)]

    @classmethod
    def de(cls, texto):
        g = cls()
        _ole32.CLSIDFromString(ctypes.c_wchar_p("{" + texto + "}"), ctypes.byref(g))
        return g


class _PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                ("r3", ctypes.c_ushort), ("valor", ctypes.c_void_p), ("extra", ctypes.c_void_p)]


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", w.DWORD)]


CLSID_ENUMERADOR = _GUID.de("BCDE0395-E52F-467C-8E3D-C4579291692E")
IID_ENUMERADOR = _GUID.de("A95664D2-9614-4F35-A746-DE8DB63617E6")
IID_SESSOES2 = _GUID.de("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F")
IID_CONTROLE2 = _GUID.de("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d")
IID_VOLUME_APP = _GUID.de("87CE5498-68D6-44E5-9215-6DA47EF883D8")
IID_MEDIDOR = _GUID.de("C02216F6-8C67-4B5B-9D00-D008E73E0064")
IID_VOLUME_GERAL = _GUID.de("5CDF2C82-841E-4546-9722-0CF74078229A")
PKEY_NOME = _PROPERTYKEY(_GUID.de("a45c254e-df1c-4efd-8020-67d146a850e0"), 14)
CLSCTX_ALL = 23


class _Com:
    """Ponteiro de interface COM com Release automático."""

    def __init__(self, ptr):
        self.ptr = ptr

    def chamar(self, indice, tipos, *args):
        vtbl = ctypes.cast(self.ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        return ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *tipos)(vtbl[indice])(self.ptr, *args)

    def obter(self, indice, tipos, *args):
        """Chama um método cujo último parâmetro devolve outra interface."""
        saida = ctypes.c_void_p()
        self.chamar(indice, tipos + (ctypes.POINTER(ctypes.c_void_p),), *args, ctypes.byref(saida))
        return _Com(saida.value)

    def consultar(self, iid):
        try:
            return self.obter(0, (ctypes.POINTER(_GUID),), ctypes.byref(iid))
        except OSError:
            return None

    def __del__(self):
        if self.ptr:
            vtbl = ctypes.cast(self.ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])(self.ptr)
            self.ptr = None


def _float(com, indice):
    v = ctypes.c_float()
    com.chamar(indice, (ctypes.POINTER(ctypes.c_float),), ctypes.byref(v))
    return v.value


def _texto_com(com, indice):
    p = ctypes.c_void_p()
    com.chamar(indice, (ctypes.POINTER(ctypes.c_void_p),), ctypes.byref(p))
    try:
        return ctypes.wstring_at(p.value) if p.value else ""
    finally:
        _ole32.CoTaskMemFree(p)


def _nome_dispositivo(dispositivo):
    loja = dispositivo.obter(4, (w.DWORD,), 0)
    pv = _PROPVARIANT()
    loja.chamar(5, (ctypes.POINTER(_PROPERTYKEY), ctypes.POINTER(_PROPVARIANT)), ctypes.byref(PKEY_NOME), ctypes.byref(pv))
    try:
        return ctypes.wstring_at(pv.valor) if pv.valor else ""
    finally:
        _ole32.PropVariantClear(ctypes.byref(pv))


_nomes_processo = {}


def _nome_processo(pid):
    if pid in _nomes_processo:
        return _nomes_processo[pid]
    nome = "?"
    h = _kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        buf = ctypes.create_unicode_buffer(520)
        tam = w.DWORD(520)
        if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(tam)):
            nome = os.path.basename(buf.value)
        _kernel32.CloseHandle(h)
    if len(_nomes_processo) > 500:
        _nomes_processo.clear()
    _nomes_processo[pid] = nome
    return nome


class _Sessao:
    def __init__(self, instancia, nome, grupo, volume, medidor):
        self.instancia, self.nome, self.grupo = instancia, nome, grupo
        self.volume, self.medidor = volume, medidor

    def ler_volume(self):
        return _float(self.volume, 4)

    def definir_volume(self, valor):
        self.volume.chamar(3, (ctypes.c_float, ctypes.c_void_p), max(0.0, min(1.0, valor)), None)

    def pico(self):
        try:
            return _float(self.medidor, 3) if self.medidor else 0.0
        except OSError:
            return 0.0


class Mixer:
    def __init__(self, incluir_proprio=False):
        _ole32.CoInitializeEx(None, 2)  # STA; se já estiver iniciado, tudo bem
        ptr = ctypes.c_void_p()
        hr = _ole32.CoCreateInstance(ctypes.byref(CLSID_ENUMERADOR), None, CLSCTX_ALL,
                                     ctypes.byref(IID_ENUMERADOR), ctypes.byref(ptr))
        if hr != 0 or not ptr.value:
            raise OSError(f"Core Audio indisponível (0x{hr & 0xFFFFFFFF:08x})")
        self._enum = _Com(ptr.value)
        self._pid = None if incluir_proprio else os.getpid()
        self._sessoes = []
        self._originais = {}  # instância -> volume antes de mexermos
        self._aplicado = {}  # instância -> último volume que definimos
        self.apps_chat, self.apps_jogo = [], []

    # ---------- sessões ----------

    def atualizar(self):
        """Relê as sessões de áudio de todos os alto-falantes (exceto o cabo do mic)."""
        sessoes = []
        colecao = self._enum.obter(3, (ctypes.c_int, w.DWORD), 0, 1)  # eRender, ATIVOS
        n = w.UINT()
        colecao.chamar(3, (ctypes.POINTER(w.UINT),), ctypes.byref(n))
        for i in range(n.value):
            disp = colecao.obter(4, (w.UINT,), i)
            if any(x in _nome_dispositivo(disp) for x in IGNORAR_DISPOSITIVOS):
                continue
            try:
                gerente = disp.obter(3, (ctypes.POINTER(_GUID), w.DWORD, ctypes.c_void_p),
                                     ctypes.byref(IID_SESSOES2), CLSCTX_ALL, None)
                lista = gerente.obter(5, ())
            except OSError:
                continue
            total = ctypes.c_int()
            lista.chamar(3, (ctypes.POINTER(ctypes.c_int),), ctypes.byref(total))
            for j in range(total.value):
                sessao = self._ler_sessao(lista.obter(4, (ctypes.c_int,), j))
                if sessao:
                    sessoes.append(sessao)
        self._sessoes = sessoes
        self.apps_chat = sorted({s.nome for s in sessoes if s.grupo == "chat"})
        self.apps_jogo = sorted({s.nome for s in sessoes if s.grupo == "jogo"})

    def _ler_sessao(self, controle):
        c2 = controle.consultar(IID_CONTROLE2)
        if c2 is None:
            return None
        estado = ctypes.c_int()
        c2.chamar(3, (ctypes.POINTER(ctypes.c_int),), ctypes.byref(estado))
        if estado.value == 2 or c2.chamar(15, ()) == 0:  # encerrada ou "sons do sistema"
            return None
        pid = w.DWORD()
        c2.chamar(14, (ctypes.POINTER(w.DWORD),), ctypes.byref(pid))
        if pid.value == 0 or pid.value == self._pid:
            return None
        nome = _nome_processo(pid.value)
        volume = c2.consultar(IID_VOLUME_APP)
        if volume is None:
            return None
        grupo = "chat" if nome.lower() in CHAT else "jogo"
        apelido = os.path.splitext(nome)[0]
        return _Sessao(_texto_com(c2, 13), apelido, grupo, volume, c2.consultar(IID_MEDIDOR))

    # ---------- volumes ----------

    def aplicar(self, vol_chat, vol_jogo):
        """Volumes 0..1. Só escreve quando o alvo muda ou a sessão é nova, para não
        brigar com quem mexer no mixer do Windows na mão."""
        for s in self._sessoes:
            alvo = vol_chat if s.grupo == "chat" else vol_jogo
            if self._aplicado.get(s.instancia) == alvo:
                continue
            try:
                if s.instancia not in self._originais:
                    self._originais[s.instancia] = s.ler_volume()
                s.definir_volume(alvo)
                self._aplicado[s.instancia] = alvo
            except OSError:
                pass

    def restaurar(self):
        """Devolve o volume que cada app tinha antes do Mic Limpo mexer."""
        try:
            self.atualizar()
        except OSError:
            pass
        for s in self._sessoes:
            if s.instancia in self._originais:
                try:
                    s.definir_volume(self._originais[s.instancia])
                except OSError:
                    pass
        self._originais.clear()
        self._aplicado.clear()

    def picos(self):
        chat = jogo = 0.0
        for s in self._sessoes:
            p = s.pico()
            if s.grupo == "chat":
                chat = max(chat, p)
            else:
                jogo = max(jogo, p)
        return chat, jogo

    # ---------- volume geral ----------

    def _volume_geral(self):
        disp = self._enum.obter(4, (ctypes.c_int, ctypes.c_int), 0, 0)  # eRender, eConsole
        vol = disp.obter(3, (ctypes.POINTER(_GUID), w.DWORD, ctypes.c_void_p),
                         ctypes.byref(IID_VOLUME_GERAL), CLSCTX_ALL, None)
        return _nome_dispositivo(disp), vol

    def volume_geral(self):
        nome, vol = self._volume_geral()
        return nome, _float(vol, 9)

    def definir_volume_geral(self, valor):
        _, vol = self._volume_geral()
        vol.chamar(7, (ctypes.c_float, ctypes.c_void_p), max(0.0, min(1.0, valor)), None)
