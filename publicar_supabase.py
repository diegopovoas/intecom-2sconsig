#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2S BI — Publica o painel gerado no Supabase (painel_cache).
Substitui o git push do fluxo de 15 em 15 minutos: o HTML completo
fica protegido por login no banco, fora do GitHub público.
"""
import sys, os, json
from datetime import datetime
import urllib.request
import urllib.error

PASTA = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(PASTA, '_supabase', 'config.json')
PAINEL = os.path.join(PASTA, 'painel_bi_2s.html')


def log(msg):
    print(f'[{datetime.now():%H:%M:%S}] {msg}')


def main():
    if not os.path.exists(CONFIG):
        log('ERRO: _supabase/config.json nao encontrado.')
        sys.exit(1)
    if not os.path.exists(PAINEL):
        log('ERRO: painel_bi_2s.html nao encontrado — rode o processar_2s.py antes.')
        sys.exit(1)

    cfg = json.loads(open(CONFIG, encoding='utf-8').read())
    html = open(PAINEL, encoding='utf-8').read()

    body = json.dumps([{
        'escopo': 'painel',
        'html': html,
        'atualizado_em': datetime.now().astimezone().isoformat(),
    }]).encode('utf-8')

    req = urllib.request.Request(
        cfg['url'].rstrip('/') + '/rest/v1/painel_cache?on_conflict=escopo',
        data=body, method='POST',
        headers={
            'apikey': cfg['service_role_key'],
            'Authorization': f"Bearer {cfg['service_role_key']}",
            'Content-Type': 'application/json',
            'Prefer': 'resolution=merge-duplicates,return=minimal',
        })
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            r.read()
        log(f'Painel publicado no Supabase ({len(html)//1024} KB).')
    except urllib.error.HTTPError as e:
        log(f'ERRO HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:300]}')
        sys.exit(1)


if __name__ == '__main__':
    main()
