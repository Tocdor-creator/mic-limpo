"""Desenha o ícone do Mic Limpo (mic verde em fundo escuro) e salva em mic_limpo/icone.ico."""

import os

from PIL import Image, ImageDraw

DESTINO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mic_limpo", "icone.ico")
L = 256
VERDE = (34, 197, 94, 255)

img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((8, 8, L - 8, L - 8), radius=56, fill=(21, 23, 28, 255))
d.rounded_rectangle((98, 44, 158, 150), radius=30, fill=VERDE)  # cápsula
d.arc((70, 84, 186, 186), start=0, end=180, fill=VERDE, width=14)  # suporte em U
d.line((128, 186, 128, 214), fill=VERDE, width=14)  # haste
d.line((94, 214, 162, 214), fill=VERDE, width=14)  # base
img.save(DESTINO, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("salvo em", DESTINO)
