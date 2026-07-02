"""Reorganiza XMLs do layout antigo (arvore: <CNPJ>/<AAAA-MM>/<TIPO>/) pro layout
do Dominio (<TIPO>/<codigo>-<apelido>/). MOVE (não re-baixa). Idempotente.

Uso:  python reorg.py            # dry-run (só mostra)
      python reorg.py --mover    # executa o move
"""
import sys
import shutil
from pathlib import Path

import dominio_sync as d

d._carregar_env()
cfg = d.Config()
base = cfg.pasta_base
mapa = d.carregar_mapa_empresas(cfg)
mover = "--mover" in sys.argv

movidos = pulados = sem_mapa = 0
sem_mapa_cnpjs = set()

# Estrutura antiga: base/<CNPJ(14 digitos)>/<AAAA-MM>/<TIPO>/<chave>.xml
for cnpj_dir in base.iterdir():
    if not cnpj_dir.is_dir():
        continue
    nome = cnpj_dir.name
    cnpj = "".join(ch for ch in nome if ch.isdigit())
    # só pastas que SÃO um CNPJ (14 dígitos) e o nome é só dígitos = layout antigo
    if len(cnpj) != 14 or not nome.isdigit():
        continue
    for xml in cnpj_dir.rglob("*.xml"):
        tipo = "NFE"
        partes = [p.upper() for p in xml.parts]
        if "CTE" in partes:
            tipo = "CTE"
        elif "NFSE" in partes:
            tipo = "NFSE"
        info = mapa.get(cnpj)
        if not info:
            sem_mapa += 1
            sem_mapa_cnpjs.add(cnpj)
            continue
        codigo, apelido = info
        dest = base / tipo / f"{codigo}-{apelido}".strip() / xml.name
        if dest.exists():
            pulados += 1
            continue
        if mover:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(xml), str(dest))
        movidos += 1

print(f"{'MOVIDOS' if mover else 'MOVERIA'}: {movidos} | ja_no_destino: {pulados} | sem_mapa: {sem_mapa}")
if sem_mapa_cnpjs:
    print("CNPJs sem mapa (ficam onde estao):", sorted(sem_mapa_cnpjs))
