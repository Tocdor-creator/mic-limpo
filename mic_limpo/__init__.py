"""Mic Limpo: tira ruído e nivela o volume do microfone, saindo no VB-CABLE."""

import os

# O OpenBLAS do numpy reserva ~225 MB (um buffer por núcleo) mesmo sem ser
# usado. Com uma thread o programa inteiro fica em ~30 MB.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
