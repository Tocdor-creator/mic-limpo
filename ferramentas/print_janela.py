"""Salva um print só da janela do Mic Limpo (mesmo se estiver coberta) em docs/mesa.png.
    .venv\\Scripts\\python ferramentas\\print_janela.py [título da janela]
"""

import ctypes
import os
import sys
from ctypes import wintypes as w

from PIL import Image

ctypes.windll.shcore.SetProcessDpiAwareness(1)
u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
DESTINO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "mesa.png")

hwnd = u32.FindWindowW(None, sys.argv[1] if len(sys.argv) > 1 else "Mic Limpo")
if not hwnd:
    raise SystemExit("Janela do Mic Limpo não encontrada (o programa está aberto?)")
if u32.IsIconic(hwnd):
    u32.ShowWindow(hwnd, 9)

ret = w.RECT()
u32.GetClientRect(hwnd, ctypes.byref(ret))
larg, alt = ret.right, ret.bottom
hdc_tela = u32.GetDC(hwnd)
hdc = g32.CreateCompatibleDC(hdc_tela)
bmp = g32.CreateCompatibleBitmap(hdc_tela, larg, alt)
g32.SelectObject(hdc, bmp)
u32.PrintWindow(hwnd, hdc, 3)  # PW_CLIENTONLY | PW_RENDERFULLCONTENT


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG), ("biPlanes", w.WORD),
                ("biBitCount", w.WORD), ("biCompression", w.DWORD), ("biSizeImage", w.DWORD),
                ("biXPelsPerMeter", w.LONG), ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD),
                ("biClrImportant", w.DWORD)]


info = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), larg, -alt, 1, 32, 0, 0, 0, 0, 0, 0)
buf = ctypes.create_string_buffer(larg * alt * 4)
g32.GetDIBits(hdc, bmp, 0, alt, buf, ctypes.byref(info), 0)
g32.DeleteObject(bmp)
g32.DeleteDC(hdc)
u32.ReleaseDC(hwnd, hdc_tela)

os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
Image.frombuffer("RGBA", (larg, alt), buf, "raw", "BGRA", 0, 1).convert("RGB").save(DESTINO, optimize=True)
print(f"salvo em {DESTINO} ({larg}x{alt})")
