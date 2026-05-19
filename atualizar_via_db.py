# =============================================================
# 2S CONSIG - ATUALIZAR PRODUCAO VIA MySQL
# Conecta no banco da 2S e substitui a aba "Producao" da dados_2s.xlsx
# As demais abas (Usuarios, Hierarquia, Tabelas_CMS) ficam intactas.
# =============================================================

import os, sys
import pandas as pd
from datetime import datetime
from pathlib import Path

PASTA          = Path(__file__).parent
CRED_FILE      = PASTA / 'credenciais_db.txt'
ARQUIVO_DADOS  = PASTA / 'dados_2s.xlsx'
TABELA         = 'contrato'

# Mapeamento: coluna do banco -> coluna da planilha
# Quando o nome no banco e diferente do esperado, ajusto aqui.
MAPA_COLUNAS = {
    'ccb_numero':              'CCB',
    'data_pagamento':          'Data do Desembolso',
    'data_digitado':           'Data de Digitação',
    'data_digitacao':          'Data de Digitação',
    'created_at':              'Data de Digitação',
    'data_criacao':            'Data de Digitação',
    'status_proposta':         'Status',
    'tabela_id':               'Identificador da tabela',
    'valor_bruto':             'Valor Bruto',
    'valor_liquido':           'Valor Líquido',
    'email':                   'E-mail',
    'email_corretor':          'E-mail',
    'login_corretor':          'E-mail',
    'orgao':                   'Orgao',
    'qtd_parcelas':            'Qtd Parcelas',
    'tabela_nome':             'Tabela Nome',
}

# Traducao do status_proposta (EN -> PT)
TRADUCAO_STATUS = {
    'DISBURSED':           'Desembolsado',
    'CANCELED':            'Cancelado',
    'CANCELLED':           'Cancelado',
    'CANCEL':              'Cancelado',
    'AWAITING_SIGNATURE':  'Aguardando assinatura',
    'SIGNATURE_PENDING':   'Aguardando assinatura',
    'PENDING':             'Pendente',
    'IN_FINALIZE':         'Aguardando desembolso',
    'FINALIZING':          'Aguardando desembolso',
    'AWAITING_DISBURSE':   'Aguardando desembolso',
    'SIGNATURE_APPROVED':  'Assinatura aprovada',
    'SIGNATURE_REPROVED':  'Assinatura reprovada',
    'REPROVED':            'Assinatura reprovada',
    'INTEGRATED':                      'Integrada no banco',
    'IN_BANK':                         'Integrada no banco',
    'IN_AVERBATION':                   'Em averbação',
    'AVERBATION':                      'Em averbação',
    'RISK_ANALYSIS':                   'Rejeitada pela análise de risco',
    'REJECTED_BY_RISK':                'Rejeitada pela análise de risco',
    'REJECTED_BY_RISK_ANALYSIS':       'Rejeitada pela análise de risco',
    'AWAITING_RISK_ANALYSIS':          'Aguardando análise de risco',
    'AWAITING_DISBURSEMENT':           'Aguardando desembolso',
    'AWAITING_DISBURSE':               'Aguardando desembolso',
    'SIGNATURE_REJECTED':              'Assinatura reprovada',
    'SIGNATURE_REPROVED':              'Assinatura reprovada',
    'AWAITING_SIGNATURE_ANALYSIS':     'Aguardando análise de assinatura',
    'SIGNATURE_ANALYSIS':              'Aguardando análise de assinatura',
    'EXPIRED':                         'Expirado',
    'ERROR':                           'Erro',
    'PROCESSING':                      'Processando',
}


def log(msg): print(f'[{datetime.now().strftime("%H:%M:%S")}] {msg}')


def carregar_credenciais():
    if not CRED_FILE.exists():
        CRED_FILE.write_text(
            "# Credenciais MySQL 2S - NAO VERSIONE\n"
            "DB_HOST=2sconsig.novapowerhub.com.br\n"
            "DB_PORT=3306\n"
            "DB_NAME=twosconsig\n"
            "DB_USER=seu_usuario\n"
            "DB_PASS=sua_senha\n",
            encoding='utf-8'
        )
        log(f'Criei o arquivo {CRED_FILE.name}. Preencha e rode de novo.')
        sys.exit(1)
    cfg = {}
    for line in CRED_FILE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            cfg[k.strip()] = v.strip()
    for k in ['DB_HOST','DB_PORT','DB_NAME','DB_USER','DB_PASS']:
        if not cfg.get(k):
            log(f'ERRO: {k} ausente em {CRED_FILE.name}')
            sys.exit(1)
    return cfg


def conectar(cfg):
    try:
        import pymysql
    except ImportError:
        log('pymysql nao instalado. Instalando...')
        import subprocess
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pymysql', '--quiet'])
        import pymysql
    log(f'Conectando em {cfg["DB_HOST"]}:{cfg["DB_PORT"]} (db={cfg["DB_NAME"]})...')
    conn = pymysql.connect(
        host=cfg['DB_HOST'], port=int(cfg['DB_PORT']),
        user=cfg['DB_USER'], password=cfg['DB_PASS'],
        database=cfg['DB_NAME'], charset='utf8mb4', connect_timeout=30,
        # conv: evita que datas "0000-00-00" do MySQL causem crash
        conv={**pymysql.converters.conversions,
              pymysql.converters.FIELD_TYPE.DATE:     str,
              pymysql.converters.FIELD_TYPE.DATETIME: str,
              pymysql.converters.FIELD_TYPE.TIMESTAMP:str},
    )
    log('  Conectado!')
    return conn


def descobrir_colunas(conn):
    with conn.cursor() as cur:
        cur.execute(f"DESCRIBE {TABELA}")
        cols = [(r[0], r[1]) for r in cur.fetchall()]
    log(f'  Tabela "{TABELA}" tem {len(cols)} colunas')
    return cols


def buscar_contratos(conn, colunas_db):
    """Busca todos os contratos. Renomeia colunas pra bater com a planilha."""
    nomes = [c[0] for c in colunas_db]
    # Colunas relevantes para diagnóstico
    cols_data = [c[0] for c in colunas_db if any(k in c[0].lower() for k in ['data','date','payment','pagamento','desembolso','disburs','created'])]
    log(f'  Colunas de data encontradas no banco: {cols_data}')
    select_cols = ', '.join(f'`{c}`' for c in nomes)
    log(f'  Executando SELECT {len(nomes)} colunas (SEM filtro de data — tudo)...')
    df = pd.read_sql(f'SELECT {select_cols} FROM {TABELA}', conn)
    log(f'  Carregado: {len(df):,} contratos')

    # Diagnóstico rápido: status e cobertura de datas
    col_status = next((c for c in ['status_proposta','Status','status'] if c in df.columns), None)
    if col_status:
        log(f'  Status no banco (coluna "{col_status}", top 10):')
        for s, n in df[col_status].value_counts().head(10).items():
            log(f'    {str(s):<40} {n:>8,}')

    col_data_pag = next((c for c in ['data_pagamento','data_desembolso','disbursement_date'] if c in df.columns), None)
    if col_data_pag:
        dt = pd.to_datetime(df[col_data_pag], errors='coerce')
        nulos = dt.isna().sum()
        log(f'  Coluna "{col_data_pag}": {len(dt)-nulos:,} com data, {nulos:,} nulos, range: {dt.min()} ~ {dt.max()}')
    else:
        log(f'  ATENCAO: nenhuma coluna de data_pagamento encontrada! Mapeamento pode estar errado.')
        log(f'  Colunas disponiveis: {list(df.columns[:20])}')

    return df


def adaptar_para_planilha(df_db, prod_existente):
    """Renomeia colunas via MAPA_COLUNAS e traduz status. Preserva colunas extras."""
    df = df_db.copy()

    # Renomeia colunas conhecidas
    rename_map = {k: v for k, v in MAPA_COLUNAS.items() if k in df.columns and v not in df.columns}
    df = df.rename(columns=rename_map)
    log(f'  Renomeadas: {len(rename_map)} colunas')
    if rename_map:
        for k, v in rename_map.items():
            log(f'    "{k}" -> "{v}"')
    else:
        log(f'  ATENCAO: nenhuma coluna foi renomeada! Verifique se MAPA_COLUNAS bate com as colunas do banco.')
        log(f'  Colunas do banco (primeiras 20): {list(df.columns[:20])}')

    # Traduz Status (EN -> PT)
    if 'Status' in df.columns:
        log(f'  Status ANTES da traducao:')
        for s, n in df['Status'].value_counts().head(10).items():
            log(f'    {str(s):<40} {n:>8,}')
        df['Status'] = df['Status'].astype(str).str.upper().map(TRADUCAO_STATUS).fillna(df['Status'])
        log(f'  Status APOS traducao:')
        for s, n in df['Status'].value_counts().head(10).items():
            log(f'    {str(s):<40} {n:>8,}')
    else:
        log(f'  ATENCAO: coluna "Status" nao encontrada apos renomeacao!')

    # Normaliza datas (formatos mistos: ISO+tz, DD/MM/AAAA, ISO truncado, microsegundos)
    # IMPORTANTE: nao usar dayfirst=True com format='mixed' — inverte mes/dia em datas ISO
    import re as _re
    def _normalizar_ddmmyyyy(v):
        """Converte DD/MM/AAAA para AAAA-MM-DD antes do parse principal.
        Evita que format='mixed' (sem dayfirst) trate como MM/DD/AAAA."""
        if not v or not isinstance(v, str): return v
        m = _re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', v.strip())
        if m:
            d, mo, y = m.groups()
            return f'{y}-{mo.zfill(2)}-{d.zfill(2)}'
        return v

    for col_data in ['Data do Desembolso', 'Data de Digitação']:
        if col_data not in df.columns: continue
        raw = df[col_data].copy()
        # Normaliza para string e padroniza sufixo Z -> +00:00
        s = raw.astype(str).str.strip()
        s[s.isin(['nan', 'None', 'NaT', 'nat', '0000-00-00', '0000-00-00 00:00:00'])] = None
        # Converte DD/MM/AAAA -> AAAA-MM-DD (formato brasileiro -> ISO) antes do parse
        s = s.map(_normalizar_ddmmyyyy)
        s = s.str.replace(r'Z$', '+00:00', regex=True)
        # Tenta format='mixed' + utc=True (pandas >= 2.0) — lida com todos os formatos de uma vez
        try:
            parsed = pd.to_datetime(s, format='mixed', utc=True, errors='coerce')
        except Exception:
            # pandas < 2.0: passo 1 — tz-aware com utc=True
            parsed = pd.to_datetime(s, errors='coerce', utc=True)
            # passo 2 — restantes tz-naive (YYYY-MM-DD HH:MM:SS.ffffff, DD/MM/YYYY etc.)
            nao_ok = parsed.isna() & s.notna()
            if nao_ok.sum() > 0:
                for fmt in ['%Y-%m-%d %H:%M:%S.%f','%Y-%m-%d %H:%M:%S','%Y-%m-%dT%H:%M:%S','%Y-%m-%dT%H:%M','%d/%m/%Y','%Y-%m-%d']:
                    ainda = parsed.isna() & s.notna()
                    if ainda.sum() == 0: break
                    try:
                        p = pd.to_datetime(s[ainda], format=fmt, errors='coerce')
                        ok = p.notna()
                        if ok.sum() > 0:
                            p_utc = p[ok].dt.tz_localize('UTC')
                            parsed[ainda[ainda].index[ok]] = p_utc
                    except Exception:
                        pass
        # Recupera NaTs restantes que sao tz-naive com parse generico
        nao_ok2 = parsed.isna() & s.notna()
        if nao_ok2.sum() > 0:
            r2 = pd.to_datetime(s[nao_ok2], errors='coerce', dayfirst=True)
            ok2 = r2.notna()
            if ok2.sum() > 0:
                try:
                    r2_utc = r2[ok2].dt.tz_localize('UTC')
                    parsed[nao_ok2[nao_ok2].index[ok2]] = r2_utc
                except Exception:
                    pass
        # Remove timezone (salva tudo como naive)
        if getattr(parsed.dt, 'tz', None) is not None:
            df[col_data] = parsed.dt.tz_convert(None)
        else:
            df[col_data] = parsed
        antes = raw.notna().sum()
        depois = df[col_data].notna().sum()
        log(f'  Datas "{col_data}": {depois:,} de {antes:,} parseadas com sucesso')

    # Diagnóstico: Data do Desembolso
    if 'Data do Desembolso' in df.columns:
        dt2 = pd.to_datetime(df['Data do Desembolso'], errors='coerce')
        des_com = ((df['Status'] == 'Desembolsado') & dt2.notna()).sum()
        des_sem = ((df['Status'] == 'Desembolsado') & dt2.isna()).sum()
        log(f'  Desembolsados com data: {des_com:,}  |  sem data: {des_sem:,}')
        if des_com > 0:
            log(f'  Periodo desembolso: {dt2.min().date()} ate {dt2.max().date()}')
    else:
        log(f'  ATENCAO: "Data do Desembolso" nao encontrada apos renomeacao!')

    # Garante que colunas de referencia estao presentes (mesmo que vazias)
    for col in prod_existente.columns:
        if col not in df.columns:
            df[col] = pd.NA

    # Coloca as colunas na mesma ordem da referencia (extras vao no fim)
    cols_ordem = [c for c in prod_existente.columns if c in df.columns]
    cols_extra = [c for c in df.columns if c not in prod_existente.columns]
    df = df[cols_ordem + cols_extra]

    return df


def main():
    log('=' * 55)
    log('  2S - ATUALIZAR PRODUCAO VIA MySQL')
    log('=' * 55)

    if not ARQUIVO_DADOS.exists():
        log(f'ERRO: {ARQUIVO_DADOS.name} nao encontrado')
        sys.exit(1)

    cfg = carregar_credenciais()
    conn = conectar(cfg)

    try:
        colunas_db = descobrir_colunas(conn)
        df_db = buscar_contratos(conn, colunas_db)
    finally:
        conn.close()
        log('  Conexao fechada')

    # Le apenas as abas de referencia (pequenas — Usuarios, Hierarquia, Tabelas_CMS)
    # A aba Producao NAO e mais lida/escrita no Excel — vai para parquet (muito mais rapido)
    log('Lendo abas de referencia do dados_2s.xlsx...')
    xls = pd.ExcelFile(ARQUIVO_DADOS)
    abas_ref = [s for s in xls.sheet_names if s != 'Producao']
    sheets_ref = {s: pd.read_excel(xls, sheet_name=s) for s in abas_ref}
    log(f'  Abas lidas: {abas_ref}')

    # Usa colunas de referencia do parquet existente (se houver) ou DataFrame vazio
    parquet_ref = PASTA / 'producao.parquet'
    if parquet_ref.exists():
        try:
            prod_ref = pd.read_parquet(parquet_ref)
            log(f'  Referencia de colunas: producao.parquet ({len(prod_ref):,} linhas anteriores)')
        except Exception:
            prod_ref = pd.DataFrame()
    else:
        # Primeira execucao: tenta pegar colunas da aba Producao se ainda existir no xlsx
        prod_ref = sheets_ref.get('Producao', pd.DataFrame())

    df_novo = adaptar_para_planilha(df_db, prod_ref)
    log(f'  Producao nova: {len(df_novo):,} linhas, {len(df_novo.columns)} colunas')

    log('Salvando producao.parquet...')
    df_novo.to_parquet(parquet_ref, index=False)
    log(f'  OK! ({parquet_ref.stat().st_size // 1024:,} KB)')

    log('=' * 55)
    log('  PRODUCAO ATUALIZADA COM SUCESSO!')
    log('=' * 55)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nCancelado.')
        sys.exit(1)
    except Exception as e:
        print(f'\nERRO: {e}')
        import traceback; traceback.print_exc()
        sys.exit(1)
