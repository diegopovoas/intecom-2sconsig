# =============================================================
# 2S CONSIG - PROCESSAMENTO + GERACAO DO PAINEL BI
# Versao 3.0 (reconstruido)
#
# Como usar:
#   1. Coloque os 3 arquivos na mesma pasta deste script
#   2. De dois cliques em RODAR.bat
#   3. O painel_bi_2s.html sera gerado na mesma pasta
# =============================================================

import pandas as pd
import os, sys, json, re
from pathlib import Path
from datetime import datetime, date
from calendar import monthrange

# ============================================================
# CONFIGURACAO
# ============================================================
PASTA = os.path.dirname(os.path.abspath(__file__))

ARQUIVO_DADOS      = os.path.join(PASTA, 'dados_2s.xlsx')
ARQUIVO_PARQUET    = os.path.join(PASTA, 'producao.parquet')
ARQUIVO_HTML       = os.path.join(PASTA, 'painel_bi_2s.html')

LABEL_INTERNO = 'Usuario interno / operacional'
# ============================================================

def log(msg):
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    except UnicodeEncodeError:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}".encode('ascii', errors='replace').decode('ascii'))

def load_panel_users():
    """Usuarios do login do painel: arquivo local (nao versionar - ver .gitignore)."""
    path = Path(PASTA) / 'painel_usuarios.local.json'
    if path.exists():
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                return data
        except (json.JSONDecodeError, OSError) as e:
            log(f'ERRO lendo painel_usuarios.local.json: {e}')
            sys.exit(1)
    log('AVISO: crie painel_usuarios.local.json (copie de painel_usuarios.example.json).')
    return {}

def dias_uteis(ano, mes, ate_dia):
    tot, pas = 0, 0
    for d in range(1, monthrange(ano, mes)[1]+1):
        if date(ano, mes, d).weekday() < 5:
            tot += 1
            if d <= ate_dia: pas += 1
    return tot, pas

def jss(v): return json.dumps(v, ensure_ascii=False, default=str)

def mes_label(m):
    mapa = {'01':'Jan','02':'Fev','03':'Mar','04':'Abr','05':'Mai',
            '06':'Jun','07':'Jul','08':'Ago','09':'Set','10':'Out',
            '11':'Nov','12':'Dez'}
    try:
        ano, mes = str(m).split('-')
        return f"{mapa.get(mes, mes)}/{ano[2:]}"
    except: return str(m)

def ok_hier(v):
    return len(str(v)) > 5 and str(v) not in ['nan', 'None', '0']

# ============================================================
# PASSO 1: PROCESSAMENTO DOS DADOS
# ============================================================
def processar_dados():
    log("Verificando arquivos...")
    for arq, nome in [(ARQUIVO_DADOS, 'dados_2s.xlsx'),]:
        if not os.path.exists(arq):
            log(f"ERRO: '{nome}' nao encontrado -> {arq}")
            if os.environ.get('NO_BROWSER') != '1':
                input("\nPressione ENTER para fechar...")
            sys.exit(1)
        log(f"  OK: {os.path.basename(arq)}")
    print()

    log("Carregando arquivos...")
    # Producao: lê do parquet (rapido) com fallback para aba Excel
    if os.path.exists(ARQUIVO_PARQUET):
        prod = pd.read_parquet(ARQUIVO_PARQUET)
        log(f"  Producao (parquet): {len(prod):,} linhas")
    else:
        log("  AVISO: producao.parquet nao encontrado, lendo do Excel (mais lento)...")
        prod = pd.read_excel(ARQUIVO_DADOS, sheet_name='Producao')
        log(f"  Producao (xlsx): {len(prod):,} linhas")
    # Abas de referencia (pequenas)
    xls  = pd.ExcelFile(ARQUIVO_DADOS)
    usu  = pd.read_excel(xls, sheet_name='Usuarios')
    hier = pd.read_excel(xls, sheet_name='Hierarquia')
    tabs_cms = pd.read_excel(xls, sheet_name='Tabelas_CMS')
    hier.columns = [c.replace('﻿','').strip() for c in hier.columns]
    log(f"  Usuarios: {len(usu):,} | Hierarquia: {len(hier):,} | Tabelas: {len(tabs_cms):,}")

    log("Cruzando dados...")
    # codigo_nova é a chave unificada: bate com Código Corretor (Usuarios) e Cod Parceiro (Hierarquia)
    prod['_ek'] = pd.to_numeric(prod['codigo_nova'], errors='coerce')
    if 'Código Corretor' in usu.columns:
        usu['_ek'] = pd.to_numeric(usu['Código Corretor'], errors='coerce')
        usu['_cc'] = usu['_ek']
    hier['_cp'] = pd.to_numeric(hier['Cod Parceiro'], errors='coerce')
    if 'Parceiro' in prod.columns: prod = prod.rename(columns={'Parceiro':'Parceiro_prod'})
    if 'Produto'       in prod.columns: prod = prod.rename(columns={'Produto':'Produto_original'})
    if 'Fundo'         in prod.columns: prod = prod.rename(columns={'Fundo':'Fundo_original'})
    if 'Bancarizadora' in prod.columns: prod = prod.rename(columns={'Bancarizadora':'Bancarizadora_original'})

    log("Usando Tabelas CMS da aba Tabelas_CMS...")
    tabs = tabs_cms.copy()

    prod['_tab_key'] = prod['Identificador da tabela'].astype(str).str.strip().str.lower()
    tabs['_tab_key'] = tabs['PRODUTO__ID'].astype(str).str.strip().str.lower()
    cols_tabs = [c for c in ['_tab_key','Fundo','Produto','Bancarizadora'] if c in tabs.columns]
    tabs_uniq = tabs[cols_tabs].drop_duplicates(subset=['_tab_key'])
    prod = prod.merge(tabs_uniq, on='_tab_key', how='left')
    match_tab = prod['Fundo'].notna().sum()
    log(f"   -> {match_tab:,} de {len(prod):,} contratos com Fundo identificado ({match_tab/len(prod)*100:.1f}%)")
    prod = prod.drop(columns=['_tab_key'])

    cols_usu = [c for c in ['_ek','_cc','Nome Corretor','Código Comercial','Nome Comercial','Código Regional','Nome Regional'] if c in usu.columns]
    df = prod.merge(usu[cols_usu], on='_ek', how='left')

    col_reg = next((c for c in hier.columns if 'reg' in c.lower() and 'cod' not in c.lower() and c != 'Cod Parceiro'), 'Regional')
    cols_hier = [c for c in ['_cp','Parceiro','Comercial',col_reg,'Superintendente'] if c in hier.columns]
    hier_s = hier[cols_hier].rename(columns={col_reg:'Regional'})
    df = df.merge(hier_s, left_on='_cc', right_on='_cp', how='left')
    df = df.drop_duplicates(subset=['CCB'])

    sem = df['Superintendente'].isna()
    for col in ['Nome Corretor','Parceiro','Comercial','Regional','Superintendente']:
        if col in df.columns: df.loc[sem, col] = LABEL_INTERNO

    # Parser robusto de datas — banco tem formatos mistos
    # (ISO com Z, ISO com microsegundos, DD/MM/AAAA, etc.)
    import re as _re
    def _fix_ddmmyyyy(v):
        if not v or not isinstance(v, str): return v
        m = _re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', v.strip())
        if m:
            d, mo, y = m.groups()
            return f'{y}-{mo.zfill(2)}-{d.zfill(2)}'
        return v

    for col in ['Data de Digitação','Data do Desembolso']:
        if col not in df.columns: continue
        raw = df[col].copy()
        s = raw.astype(str).str.strip()
        s[s.isin(['nan','None','NaT','nat',''])] = None
        s = s.map(_fix_ddmmyyyy)
        s = s.str.replace(r'Z$', '+00:00', regex=True)
        try:
            result = pd.to_datetime(s, format='mixed', utc=True, errors='coerce')
        except Exception:
            result = pd.to_datetime(s, errors='coerce', utc=True)
            nao_ok = result.isna() & s.notna()
            if nao_ok.sum() > 0:
                for fmt in ['%Y-%m-%d %H:%M:%S.%f','%Y-%m-%d %H:%M:%S','%Y-%m-%dT%H:%M:%S','%Y-%m-%dT%H:%M','%d/%m/%Y','%Y-%m-%d']:
                    ainda = result.isna() & s.notna()
                    if ainda.sum() == 0: break
                    try:
                        p = pd.to_datetime(s[ainda], format=fmt, errors='coerce')
                        ok = p.notna()
                        if ok.sum() > 0:
                            result[ainda[ainda].index[ok]] = p[ok].dt.tz_localize('UTC')
                    except Exception:
                        pass
        nao_ok2 = result.isna() & s.notna()
        if nao_ok2.sum() > 0:
            r2 = pd.to_datetime(s[nao_ok2], errors='coerce', dayfirst=True)
            ok2 = r2.notna()
            if ok2.sum() > 0:
                try:
                    result[nao_ok2[nao_ok2].index[ok2]] = r2[ok2].dt.tz_localize('UTC')
                except Exception:
                    pass
        if getattr(result.dt, 'tz', None) is not None:
            result = result.dt.tz_convert(None)
        df[col] = result
        log(f"  Datas '{col}': {result.notna().sum():,} de {raw.notna().sum():,} parseadas com sucesso")

    for col in ['Valor Bruto','Valor Líquido']:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')

    df['Mes'] = df['Data do Desembolso'].dt.to_period('M').astype(str)
    df = df.drop(columns=[c for c in ['_ek','_cc','_cp'] if c in df.columns])

    log(f"  {len(df):,} contratos | {df['Superintendente'].notna().sum():,} com hierarquia | {sem.sum():,} internos")
    return df

# ============================================================
# PASSO 2: CALCULAR METRICAS PARA O BI
# ============================================================
def calcular_metricas(df):
    log("Calculando metricas do BI...")

    des = df[df['Status']=='Desembolsado'].copy()
    des = des[des['Mes'].notna() & (des['Mes'] != 'NaT') & (des['Mes'] != 'nan')]

    from datetime import date as _date
    data_hoje_real = pd.Timestamp(_date.today())
    data_max_arquivo = df['Data do Desembolso'].dt.normalize().max()
    data_hoje = data_hoje_real
    total_reg = len(df)
    total_des = len(des)

    # MENSAL
    mensal_g = des.groupby('Mes').agg(C=('CCB','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).reset_index().sort_values('Mes')
    meses_raw = mensal_g['Mes'].tolist()
    meses_lbl = [mes_label(m) for m in meses_raw]
    contratos  = mensal_g['C'].tolist()
    bruto      = [round(v,2) for v in mensal_g['B'].tolist()]
    liquido    = [round(v,2) for v in mensal_g['L'].tolist()]
    ticketB    = [round(b/c) if c>0 else 0 for b,c in zip(bruto,contratos)]
    ticketL    = [round(l/c) if c>0 else 0 for l,c in zip(liquido,contratos)]

    # POR PRODUTO x MES
    prod_mes = des.groupby(['Mes','Produto']).agg(C=('CCB','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).reset_index()
    prod_rows = [{'m':mes_label(r.Mes),'p':r.Produto,'c':int(r.C),'b':round(r.B,2),'l':round(r.L,2)} for _,r in prod_mes.iterrows()]

    # POR FUNDO x MES
    fundo_mes = des.groupby(['Mes','Fundo']).agg(C=('CCB','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).reset_index() if 'Fundo' in des.columns else pd.DataFrame()
    fundo_rows = [{'m':mes_label(r.Mes),'f':r.Fundo,'c':int(r.C),'b':round(r.B,2),'l':round(r.L,2)} for _,r in fundo_mes.iterrows()]

    # FUNDOS TOTAIS
    fundos_g = des.groupby('Fundo').agg(C=('CCB','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).sort_values('B',ascending=False).reset_index() if 'Fundo' in des.columns else pd.DataFrame()
    fundos = [{'f':r.Fundo,'c':int(r.C),'b':round(r.B,2),'l':round(r.L,2)} for _,r in fundos_g.iterrows()]

    # SUPERINTENDENTES
    sups_g = des[des['Superintendente'].apply(ok_hier)].groupby('Superintendente').agg(C=('CCB','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).sort_values('B',ascending=False).reset_index().head(8)
    sups = [{'n': r.Superintendente.split(' - ',1)[-1] if ' - ' in r.Superintendente else r.Superintendente,
             'c':int(r.C),'b':round(r.B,2),'l':round(r.L,2)} for _,r in sups_g.iterrows()]

    # TOP PARCEIROS
    parc_g = des[des['Parceiro'].apply(ok_hier)].groupby('Parceiro').agg(C=('CCB','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).sort_values('B',ascending=False).reset_index().head(15)
    top_parc = [{'n':r.Parceiro,'c':int(r.C),'b':round(r.B,2),'l':round(r.L,2)} for _,r in parc_g.iterrows()]

    # STATUS
    def _cat_status(s):
        s = str(s).lower()
        if 'desembolsado' in s: return 'Desembolsado'
        if 'cancel' in s: return 'Cancelado'
        if 'assinatura' in s or 'reprovad' in s: return 'Ag. Assinatura'
        if 'desembolso' in s or 'integrad' in s: return 'Ag. Desembolso'
        if 'risco' in s or 'analise' in s or 'análise' in s: return 'Em Analise'
        if 'averbac' in s or 'averbação' in s: return 'Em Averbacao'
        return 'Outros'
    df['_sc'] = df['Status'].apply(_cat_status)
    status_g = df.groupby('_sc')['CCB'].count().sort_values(ascending=False).reset_index()
    status_list = [{'s':r._sc,'v':int(r.CCB)} for _,r in status_g.iterrows()]

    # MES ATUAL
    mes_atual = data_hoje.replace(day=1)
    mes_des = des[des['Data do Desembolso'] >= mes_atual]
    bruto_mes  = round(mes_des['Valor Bruto'].sum(), 2)
    liq_mes    = round(mes_des['Valor Líquido'].sum(), 2)
    contr_mes  = len(mes_des)
    tdu, pdu = dias_uteis(data_hoje.year, data_hoje.month, data_hoje.day)
    proj_b = round(bruto_mes/pdu*tdu, 2) if pdu else 0
    proj_l = round(liq_mes/pdu*tdu, 2) if pdu else 0
    proj_c = round(contr_mes/pdu*tdu) if pdu else 0
    pct_mes = round(pdu/tdu*100, 1) if tdu else 0

    # DIA A DIA do mês atual
    if len(mes_des) > 0:
        mes_des_d = mes_des.copy()
        mes_des_d['_dia'] = mes_des_d['Data do Desembolso'].dt.day
        dia_dia_g = mes_des_d.groupby('_dia').agg(C=('CCB','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).reset_index()
        import calendar as _cal
        ultimo_dia = min(data_hoje.day, _cal.monthrange(data_hoje.year, data_hoje.month)[1])
        dia_dia_map = {int(r._dia): {'c': int(r.C), 'b': round(r.B, 2), 'l': round(r.L, 2)} for _, r in dia_dia_g.iterrows()}
        dia_dia_list = [{'d': d, 'c': dia_dia_map.get(d, {}).get('c', 0),
                         'b': dia_dia_map.get(d, {}).get('b', 0),
                         'l': dia_dia_map.get(d, {}).get('l', 0)} for d in range(1, ultimo_dia + 1)]
    else:
        dia_dia_list = []

    mes_prod = mes_des.groupby('Produto').agg(C=('CCB','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).reset_index() if len(mes_des)>0 else pd.DataFrame(columns=['Produto','C','B','L'])
    mes_fundo = mes_des.groupby('Fundo').agg(C=('CCB','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).reset_index() if 'Fundo' in mes_des.columns and len(mes_des)>0 else pd.DataFrame(columns=['Fundo','C','B','L'])
    mes_anterior_b = bruto[-2] if len(bruto) >= 2 else 0
    mes_anterior_c = contratos[-2] if len(contratos) >= 2 else 0
    var_b = round((proj_b/mes_anterior_b - 1)*100, 1) if mes_anterior_b else 0

    # HOJE
    hoje_df = df[(df['Data do Desembolso'].dt.normalize()==data_hoje)&(df['Status']=='Desembolsado')].copy()
    hoje_total_b = round(hoje_df['Valor Bruto'].sum(), 2)
    hoje_total_l = round(hoje_df['Valor Líquido'].sum(), 2)
    hoje_c = len(hoje_df)
    hoje_parc_g = hoje_df.groupby('Parceiro').agg(C=('CCB','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).sort_values('B',ascending=False).reset_index().head(15)
    hoje_parc = [{'n':r.Parceiro,'c':int(r.C),'b':round(r.B,2),'l':round(r.L,2)} for _,r in hoje_parc_g.iterrows()]
    hoje_prod_g = hoje_df.groupby('Produto').agg(C=('CCB','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).reset_index() if len(hoje_df)>0 else pd.DataFrame(columns=['Produto','C','B','L'])
    hoje_fundo_g = hoje_df.groupby('Fundo').agg(C=('CCB','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).reset_index() if 'Fundo' in hoje_df.columns and len(hoje_df)>0 else pd.DataFrame(columns=['Fundo','C','B','L'])

    # P3: HIERARQUIA
    def get_level(d, col, top=20):
        filt = d[d[col].apply(ok_hier)] if col in d.columns else d
        return filt.groupby(col).agg(C=('Valor Bruto','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).sort_values('B',ascending=False).reset_index().head(top).round(2)

    by_sup  = get_level(des,'Superintendente',10)
    by_reg  = get_level(des,'Regional',20)
    by_com  = get_level(des,'Comercial',40)
    by_parc2 = get_level(des,'Parceiro',30)

    # Enriquece by_parc2 com hierarquia (sup/reg) para permitir filtros no JS
    if 'Parceiro' in des.columns:
        parc_hier_map = des[des['Parceiro'].apply(ok_hier)].drop_duplicates('Parceiro')[
            ['Parceiro'] + [c for c in ['Superintendente','Regional','Comercial'] if c in des.columns]
        ]
        by_parc2 = by_parc2.merge(parc_hier_map, on='Parceiro', how='left')

    h = des[des['Superintendente'].apply(ok_hier)].copy()
    sup_mes_g = h.groupby(['Superintendente','Mes']).agg(C=('Valor Bruto','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).reset_index().round(2)
    reg_mes_g = des[des['Regional'].apply(ok_hier)].groupby(['Regional','Mes']).agg(C=('Valor Bruto','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).reset_index().round(2) if 'Regional' in des.columns else pd.DataFrame()

    # Parceiro x Mes - LIMITADO aos top 30 parceiros
    if 'Parceiro' in des.columns and 'Mes' in des.columns and len(by_parc2) > 0:
        top_parc_keys = by_parc2['Parceiro'].tolist()
        parc_mes_g = des[des['Parceiro'].apply(ok_hier) & des['Parceiro'].isin(top_parc_keys)].groupby(['Parceiro','Mes']).agg(
            C=('Valor Bruto','count'), B=('Valor Bruto','sum'), L=('Valor Líquido','sum')
        ).reset_index()
        parc_mes_g['B'] = parc_mes_g['B'].round(0).astype(int)
        parc_mes_g['L'] = parc_mes_g['L'].round(0).astype(int)
    else:
        parc_mes_g = pd.DataFrame()

    # P3 POR PRODUTO
    prod_list_p3 = sorted([p for p in des['Produto'].dropna().unique().tolist() if str(p).strip() and str(p).lower() != 'nan'])
    by_sup_prod = {}; by_reg_prod = {}; by_com_prod = {}; by_parc_prod = {}
    sup_mes_prod = {}; reg_mes_prod = {}
    for _prod in prod_list_p3:
        d_p = des[des['Produto'] == _prod]
        by_sup_prod[_prod] = get_level(d_p, 'Superintendente', 10).to_dict('records')
        by_reg_prod[_prod] = get_level(d_p, 'Regional', 20).to_dict('records')
        by_com_prod[_prod] = get_level(d_p, 'Comercial', 40).to_dict('records')
        bp_p = get_level(d_p, 'Parceiro', 30)
        if 'Parceiro' in d_p.columns and len(bp_p) > 0:
            phm_p = d_p[d_p['Parceiro'].apply(ok_hier)].drop_duplicates('Parceiro')[
                ['Parceiro'] + [c for c in ['Superintendente','Regional','Comercial'] if c in d_p.columns]]
            bp_p = bp_p.merge(phm_p, on='Parceiro', how='left')
        by_parc_prod[_prod] = bp_p.to_dict('records')
        h_p = d_p[d_p['Superintendente'].apply(ok_hier)].copy() if 'Superintendente' in d_p.columns else d_p
        sup_mes_prod[_prod] = h_p.groupby(['Superintendente','Mes']).agg(C=('Valor Bruto','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).reset_index().round(2).to_dict('records') if 'Superintendente' in h_p.columns and len(h_p) else []
        reg_mes_prod[_prod] = d_p[d_p['Regional'].apply(ok_hier)].groupby(['Regional','Mes']).agg(C=('Valor Bruto','count'),B=('Valor Bruto','sum'),L=('Valor Líquido','sum')).reset_index().round(2).to_dict('records') if 'Regional' in d_p.columns and len(d_p) else []

    # CONVERSAO
    conv_prod = df.groupby('Produto').agg(Total=('CCB','count')).reset_index()
    conv_des  = des.groupby('Produto').agg(Desemb=('CCB','count')).reset_index()
    conv_prod = conv_prod.merge(conv_des, on='Produto', how='left').fillna(0)

    # CONV POR FUNDO
    conv_fundo = df.groupby('Fundo').agg(Total=('CCB','count')).reset_index() if 'Fundo' in df.columns else pd.DataFrame()
    conv_des_f = des.groupby('Fundo').agg(Desemb=('CCB','count')).reset_index() if 'Fundo' in des.columns else pd.DataFrame()
    if len(conv_fundo) and len(conv_des_f):
        conv_fundo = conv_fundo.merge(conv_des_f, on='Fundo', how='left').fillna(0)

    # CONV MENSAL (cohort por mes de DIGITACAO)
    if 'Data de Digitação' in df.columns:
        df['Mes2'] = df['Data de Digitação'].dt.to_period('M').astype(str)
        des_with_dig = df[df['Status']=='Desembolsado'].copy()
        canc_with_dig = df[df['Status']=='Cancelado'].copy()
    else:
        df['Mes2'] = df['Mes']
        des_with_dig = des
        canc_with_dig = df[df['Status']=='Cancelado']
    valido = lambda d: d[d['Mes2'].notna() & ~d['Mes2'].astype(str).isin(['NaT','nan',''])]
    conv_mes_tot = valido(df).groupby('Mes2')['CCB'].count().reset_index().rename(columns={'Mes2':'Mes','CCB':'Total'})
    conv_mes_des = valido(des_with_dig).groupby('Mes2')['CCB'].count().reset_index().rename(columns={'Mes2':'Mes','CCB':'Desemb'}) if len(des_with_dig) else pd.DataFrame(columns=['Mes','Desemb'])
    conv_mes_can = valido(canc_with_dig).groupby('Mes2')['CCB'].count().reset_index().rename(columns={'Mes2':'Mes','CCB':'Canc'}) if len(canc_with_dig) else pd.DataFrame(columns=['Mes','Canc'])
    conv_mes = conv_mes_tot.merge(conv_mes_des, on='Mes', how='left').merge(conv_mes_can, on='Mes', how='left').fillna(0)
    conv_mes = conv_mes[conv_mes['Mes'].isin(meses_raw)]
    conv_mes['Conv'] = (conv_mes['Desemb']/conv_mes['Total']*100).round(1)

    # Dados mensais por produto
    def mes_prod_list(produto):
        r = []
        for m in meses_raw:
            row = prod_mes[(prod_mes['Mes']==m)&(prod_mes['Produto']==produto)]
            r.append(int(row['C'].sum()) if len(row)>0 else 0)
        return r

    produtos_distintos = sorted([p for p in des['Produto'].dropna().unique().tolist() if str(p).strip() and str(p).lower() != 'nan'])
    mensal_por_produto = {p: mes_prod_list(p) for p in produtos_distintos}
    mensal_fgts = mensal_por_produto.get('FGTS', [0]*len(meses_raw))
    mensal_ec   = mensal_por_produto.get('E-CONSIGNADO', mensal_por_produto.get('CLT', [0]*len(meses_raw)))

    # Cross-tab produto x fundo
    prod_fundo_compat = {}
    if 'Fundo' in des.columns:
        for p in produtos_distintos:
            fundos_do_prod = des[des['Produto']==p]['Fundo'].dropna().unique().tolist()
            prod_fundo_compat[p] = [str(f) for f in fundos_do_prod if str(f).strip() and str(f).lower() != 'nan']

    # Bruta e liquida agregadas por produto
    bruta_liq_por_prod = des.groupby('Produto').agg(B=('Valor Bruto','sum'), L=('Valor Líquido','sum')).round(2).to_dict('index')

    # PERIODOS para esteira (mes, 7 dias, hoje)
    dt_col = 'Data de Digitação' if 'Data de Digitação' in df.columns else 'Data do Desembolso'
    df_p = df.copy()
    df_p['_dt'] = pd.to_datetime(df_p[dt_col], errors='coerce').dt.normalize()
    hoje_norm = data_hoje.normalize()
    mes_ini   = hoje_norm.replace(day=1)
    sete_d    = hoje_norm - pd.Timedelta(days=6)

    fatias = {
        'todos': df_p,
        'mes':   df_p[df_p['_dt'] >= mes_ini],
        '7d':    df_p[df_p['_dt'] >= sete_d],
        'hoje':  df_p[df_p['_dt'] == hoje_norm],
    }

    def agg_periodo(dfp):
        if len(dfp) == 0:
            return {'porProduto':{}, 'porFundo':{}, 'statusCompleto':[],
                    'totais':{'total':0,'desemb':0,'canc':0,'and':0,'bruta':0,'liq':0}}
        desp = dfp[dfp['Status']=='Desembolsado']
        pp = {}
        if 'Produto' in dfp.columns:
            tot_g = dfp.groupby('Produto').agg(Tot=('CCB','count')).reset_index()
            des_g = desp.groupby('Produto').agg(Des=('CCB','count'), Br=('Valor Bruto','sum'), Lq=('Valor Líquido','sum')).reset_index() if len(desp) else pd.DataFrame(columns=['Produto','Des','Br','Lq'])
            mg = tot_g.merge(des_g, on='Produto', how='left').fillna(0)
            for _, r in mg.iterrows():
                t = int(r['Tot']); d = int(r['Des'])
                pp[str(r['Produto'])] = {'total':t,'desemb':d,'canc':t-d,'and':0,
                                       'bruta':round(float(r['Br']),2),'liq':round(float(r['Lq']),2)}
        pf = {}
        if 'Fundo' in dfp.columns:
            tot_f = dfp.groupby('Fundo').agg(Tot=('CCB','count')).reset_index()
            des_f = desp.groupby('Fundo').agg(Des=('CCB','count'), Br=('Valor Bruto','sum'), Lq=('Valor Líquido','sum')).reset_index() if len(desp) else pd.DataFrame(columns=['Fundo','Des','Br','Lq'])
            mf = tot_f.merge(des_f, on='Fundo', how='left').fillna(0)
            for _, r in mf.iterrows():
                t = int(r['Tot']); d = int(r['Des'])
                pf[str(r['Fundo'])] = {'total':t,'desemb':d,'canc':t-d,'and':0,
                                     'bruta':round(float(r['Br']),2),'liq':round(float(r['Lq']),2),
                                     'conv':round(d/t*100,1) if t else 0}
        sc = []
        if '_sc' in dfp.columns:
            sc_g = dfp.groupby('_sc')['CCB'].count().sort_values(ascending=False).reset_index()
            sc = [{'s':r._sc, 'v':int(r.CCB)} for _,r in sc_g.iterrows()]
        total = len(dfp)
        desemb = len(desp)
        canc_n = int(dfp['_sc'].eq('Cancelado').sum()) if '_sc' in dfp.columns else 0
        and_n  = total - desemb - canc_n
        bruta  = round(float(desp['Valor Bruto'].sum()), 2) if len(desp) else 0
        liq    = round(float(desp['Valor Líquido'].sum()), 2) if len(desp) else 0
        return {'porProduto':pp,'porFundo':pf,'statusCompleto':sc,
                'totais':{'total':total,'desemb':desemb,'canc':canc_n,'and':and_n,'bruta':bruta,'liq':liq}}

    df_p['_sc'] = df['_sc'].values if '_sc' in df.columns else 'Outros'
    periodos = {k: agg_periodo(v) for k, v in fatias.items()}

    return {
        'data_ref': data_hoje.strftime('%d/%m/%Y'),
        'total_reg': total_reg,
        'total_des': total_des,
        'total_bruto': round(des['Valor Bruto'].sum(), 2),
        'total_liq': round(des['Valor Líquido'].sum(), 2),
        'meses_lbl': meses_lbl,
        'meses_raw': meses_raw,
        'contratos': contratos,
        'bruto': bruto,
        'liquido': liquido,
        'ticketB': ticketB,
        'ticketL': ticketL,
        'prod_rows': prod_rows,
        'fundo_rows': fundo_rows,
        'fundos': fundos,
        'sups': sups,
        'top_parc': top_parc,
        'status_list': status_list,
        'mes_atual_lbl': mes_label(data_hoje.strftime('%Y-%m')),
        'mes_contr': contr_mes,
        'mes_bruto': bruto_mes,
        'mes_liq': liq_mes,
        'mes_proj_b': proj_b,
        'mes_proj_l': proj_l,
        'mes_proj_c': int(proj_c),
        'mes_pdu': pdu,
        'mes_tdu': tdu,
        'mes_pct': pct_mes,
        'mes_ant_b': round(mes_anterior_b, 2),
        'mes_ant_c': mes_anterior_c,
        'mes_var_b': var_b,
        'mes_prod': {r.Produto:{'c':int(r.C),'b':round(r.B,2),'l':round(r.L,2)} for _,r in mes_prod.iterrows()} if len(mes_prod) else {},
        'mes_fundo': {r.Fundo:{'c':int(r.C),'b':round(r.B,2),'l':round(r.L,2)} for _,r in mes_fundo.iterrows()} if len(mes_fundo) else {},
        'hoje_data': data_hoje.strftime('%d/%m/%Y'),
        'hoje_c': hoje_c,
        'hoje_b': hoje_total_b,
        'hoje_l': hoje_total_l,
        'hoje_parc': hoje_parc,
        'hoje_prod': {r.Produto:{'c':int(r.C),'b':round(r.B,2),'l':round(r.L,2)} for _,r in hoje_prod_g.iterrows()} if len(hoje_prod_g) else {},
        'hoje_fundo': {r.Fundo:{'c':int(r.C),'b':round(r.B,2),'l':round(r.L,2)} for _,r in hoje_fundo_g.iterrows()} if len(hoje_fundo_g) else {},
        'dia_dia': dia_dia_list,
        'by_sup': by_sup.to_dict('records'),
        'by_reg': by_reg.to_dict('records'),
        'by_com': by_com.to_dict('records'),
        'by_parc2': by_parc2.to_dict('records'),
        'sup_list': [r.Superintendente for _,r in sups_g.iterrows()],
        'reg_list': by_reg['Regional'].tolist() if 'Regional' in by_reg.columns else [],
        'sup_mes': sup_mes_g.to_dict('records'),
        'reg_mes': reg_mes_g.to_dict('records') if len(reg_mes_g) else [],
        'parc_mes': parc_mes_g.to_dict('records') if len(parc_mes_g) else [],
        'prod_list_p3': prod_list_p3,
        'by_sup_prod': by_sup_prod,
        'by_reg_prod': by_reg_prod,
        'by_com_prod': by_com_prod,
        'by_parc_prod': by_parc_prod,
        'sup_mes_prod': sup_mes_prod,
        'reg_mes_prod': reg_mes_prod,
        'conv_prod': conv_prod.to_dict('records'),
        'conv_fundo': conv_fundo.to_dict('records') if len(conv_fundo) else [],
        'conv_mes': conv_mes.to_dict('records'),
        'mensal_fgts': mensal_fgts,
        'mensal_ec': mensal_ec,
        'mensal_por_produto': mensal_por_produto,
        'prod_fundo_compat': prod_fundo_compat,
        'bruta_liq_por_prod': bruta_liq_por_prod,
        'periodos': periodos,
    }

# ============================================================
# PASSO 3: GERAR BLOCO DE DADOS JS
# ============================================================
def gerar_js_dados(m):
    def fmt_k(v):
        if v >= 1_000_000: return f"R$ {v/1_000_000:.2f}M"
        return f"R$ {v/1_000:.0f}K"

    total_reg = m['total_reg']
    total_des = m['total_des']
    conv_geral = round(total_des/total_reg*100,1) if total_reg else 0
    total_bruto = m['total_bruto']
    total_liq   = m['total_liq']

    # Por produto - detecta o segundo produto automaticamente (CLT, E-CONSIGNADO, etc)
    cp = m['conv_prod']
    def get_prod(nome, key):
        r = next((x for x in cp if x.get('Produto')==nome), None)
        return r[key] if r else 0
    outros_produtos = [x for x in cp if x.get('Produto') and x.get('Produto') != 'FGTS']
    outros_produtos.sort(key=lambda x: int(x.get('Total',0)), reverse=True)
    nome_ec = outros_produtos[0]['Produto'] if outros_produtos else 'E-CONSIGNADO'
    fgts_total  = get_prod('FGTS','Total')
    fgts_des    = get_prod('FGTS','Desemb')
    ec_total    = get_prod(nome_ec,'Total')
    ec_des      = get_prod(nome_ec,'Desemb')
    fgts_b  = sum(r['b'] for r in m['prod_rows'] if r['p']=='FGTS')
    fgts_l  = sum(r['l'] for r in m['prod_rows'] if r['p']=='FGTS')
    ec_b    = sum(r['b'] for r in m['prod_rows'] if r['p']==nome_ec)
    ec_l    = sum(r['l'] for r in m['prod_rows'] if r['p']==nome_ec)
    fgts_conv = round(fgts_des/fgts_total*100,1) if fgts_total else 0
    ec_conv   = round(ec_des/ec_total*100,1)     if ec_total   else 0
    fgts_tk_b = round(fgts_b/fgts_des) if fgts_des else 0
    ec_tk_b   = round(ec_b/ec_des)     if ec_des   else 0

    # Esteira E.porProduto
    e_por_prod = {}
    blp = m.get('bruta_liq_por_prod', {})
    for r in cp:
        tot = int(r.get('Total',0)); des = int(r.get('Desemb',0))
        prod_nome = r['Produto']
        bl = blp.get(prod_nome, {})
        e_por_prod[prod_nome] = {
            'total':tot, 'desemb':des, 'canc':tot-des, 'and':0,
            'bruta':float(bl.get('B',0) or 0), 'liq':float(bl.get('L',0) or 0),
        }

    e_por_fundo = {}
    for r in m['conv_fundo']:
        tot = int(r.get('Total',0)); des2 = int(r.get('Desemb',0))
        fd = m['fundos']
        fd_r = next((x for x in fd if x['f']==r.get('Fundo','')), None)
        e_por_fundo[r.get('Fundo','')] = {
            'total':tot,'desemb':des2,'canc':tot-des2,'and':0,
            'bruta': fd_r['b'] if fd_r else 0,
            'liq': fd_r['l'] if fd_r else 0,
            'conv': round(des2/tot*100,1) if tot else 0
        }

    cm = m['conv_mes']
    mensal_conv = [{'m':mes_label(r['Mes']),'total':int(r['Total']),'desemb':int(r['Desemb']),'canc':int(r.get('Canc',0)),'conv':r['Conv']} for r in cm]

    sups_js = m['sups']
    sup1 = sups_js[0] if len(sups_js)>0 else {'n':'-','c':0,'b':0,'l':0}
    sup2 = sups_js[1] if len(sups_js)>1 else {'n':'-','c':0,'b':0,'l':0}
    sup3 = sups_js[2] if len(sups_js)>2 else {'n':'-','c':0,'b':0,'l':0}
    sup4 = sups_js[3] if len(sups_js)>3 else {'n':'-','c':0,'b':0,'l':0}

    st = {r['s']:r['v'] for r in m['status_list']}
    st_des  = st.get('Desembolsado',0)
    st_canc = st.get('Cancelado',0)
    st_ag   = sum(v for k,v in st.items() if k not in ['Desembolsado','Cancelado'])

    hp = m['hoje_prod']
    hf = m['hoje_fundo']
    hoje_fgts_c = hp.get('FGTS',{}).get('c',0)
    hoje_fgts_b = hp.get('FGTS',{}).get('b',0)
    hoje_fgts_l = hp.get('FGTS',{}).get('l',0)
    hoje_ec_c   = hp.get(nome_ec,{}).get('c',0)
    hoje_ec_b   = hp.get(nome_ec,{}).get('b',0)
    hoje_ec_l   = hp.get(nome_ec,{}).get('l',0)

    mp = m['mes_prod']
    mf2 = m['mes_fundo']

    sup_mes_js = [{'Superintendente':r.get('Superintendente',''),'Mes':mes_label(r.get('Mes','')),'C':r.get('C',0),'B':r.get('B',0),'L':r.get('L',0)} for r in m['sup_mes']]
    reg_mes_js = [{'Regional':r.get('Regional',''),'Mes':mes_label(r.get('Mes','')),'C':r.get('C',0),'B':r.get('B',0),'L':r.get('L',0)} for r in m['reg_mes']]

    by_sup_js = [{'Superintendente':r.get('Superintendente',''),'C':r.get('C',0),'B':r.get('B',0),'L':r.get('L',0)} for r in m['by_sup']]
    by_reg_js = [{'Regional':r.get('Regional',''),'C':r.get('C',0),'B':r.get('B',0),'L':r.get('L',0)} for r in m['by_reg']]
    by_com_js = [{'Comercial':r.get('Comercial',''),'C':r.get('C',0),'B':r.get('B',0),'L':r.get('L',0)} for r in m['by_com']]
    by_parc_js= [{'Nome parceiro':r.get('Parceiro',r.get('Nome parceiro','')),
                  'Superintendente': r.get('Superintendente',''),
                  'Regional': r.get('Regional',''),
                  'Comercial': r.get('Comercial',''),
                  'C':r.get('C',0),'B':r.get('B',0),'L':r.get('L',0)} for r in m['by_parc2']]
    parc_mes_js = [{'Nome parceiro': r.get('Parceiro',''),
                    'Mes': mes_label(r.get('Mes','')),
                    'C': r.get('C',0), 'B': r.get('B',0), 'L': r.get('L',0)} for r in m.get('parc_mes', [])]

    def fmt_by_sup_prod(rows): return [{'Superintendente':r.get('Superintendente',''),'C':r.get('C',0),'B':r.get('B',0),'L':r.get('L',0)} for r in rows]
    def fmt_by_reg_prod(rows): return [{'Regional':r.get('Regional',''),'C':r.get('C',0),'B':r.get('B',0),'L':r.get('L',0)} for r in rows]
    def fmt_by_com_prod(rows): return [{'Comercial':r.get('Comercial',''),'C':r.get('C',0),'B':r.get('B',0),'L':r.get('L',0)} for r in rows]
    def fmt_by_parc_prod(rows): return [{'Nome parceiro':r.get('Parceiro',r.get('Nome parceiro','')),'Superintendente':r.get('Superintendente',''),'Regional':r.get('Regional',''),'Comercial':r.get('Comercial',''),'C':r.get('C',0),'B':r.get('B',0),'L':r.get('L',0)} for r in rows]
    def fmt_sup_mes_prod(rows): return [{'Superintendente':r.get('Superintendente',''),'Mes':mes_label(r.get('Mes','')),'C':r.get('C',0),'B':r.get('B',0),'L':r.get('L',0)} for r in rows]
    def fmt_reg_mes_prod(rows): return [{'Regional':r.get('Regional',''),'Mes':mes_label(r.get('Mes','')),'C':r.get('C',0),'B':r.get('B',0),'L':r.get('L',0)} for r in rows]

    by_sup_prod_js  = {p: fmt_by_sup_prod(v)  for p,v in m.get('by_sup_prod',{}).items()}
    by_reg_prod_js  = {p: fmt_by_reg_prod(v)  for p,v in m.get('by_reg_prod',{}).items()}
    by_com_prod_js  = {p: fmt_by_com_prod(v)  for p,v in m.get('by_com_prod',{}).items()}
    by_parc_prod_js = {p: fmt_by_parc_prod(v) for p,v in m.get('by_parc_prod',{}).items()}
    sup_mes_prod_js = {p: fmt_sup_mes_prod(v) for p,v in m.get('sup_mes_prod',{}).items()}
    reg_mes_prod_js = {p: fmt_reg_mes_prod(v) for p,v in m.get('reg_mes_prod',{}).items()}

    bloco = f"""const D = {{
  meses:    {jss(m['meses_lbl'])},
  contratos:{jss(m['contratos'])},
  bruto:    {jss(m['bruto'])},
  liquido:  {jss(m['liquido'])},
  ticketB:  {jss(m['ticketB'])},
  ticketL:  {jss(m['ticketL'])},

  prodRows: {jss(m['prod_rows'])},
  fundoRows:{jss(m['fundo_rows'])},

  sups: {jss(sups_js)},
  topParc: {jss(m['top_parc'])},
  fundos: {jss(m['fundos'])},

  status: {jss(m['status_list'])},

  _meta: {{
    data_ref: {jss(m['data_ref'])},
    total_reg: {total_reg},
    total_des: {total_des},
    conv_geral: {conv_geral},
    total_bruto: {total_bruto},
    total_liq: {total_liq},
    fgts_total:{fgts_total}, fgts_des:{fgts_des}, fgts_b:{round(fgts_b,2)}, fgts_l:{round(fgts_l,2)}, fgts_conv:{fgts_conv}, fgts_tkb:{fgts_tk_b},
    ec_total:{ec_total},   ec_des:{ec_des},   ec_b:{round(ec_b,2)},   ec_l:{round(ec_l,2)},   ec_conv:{ec_conv},   ec_tkb:{ec_tk_b},
    nome_ec: {jss(nome_ec)},
    st_des:{st_des}, st_canc:{st_canc}, st_ag:{st_ag},
    mes_lbl: {jss(m['mes_atual_lbl'])},
    mes_contr:{m['mes_contr']}, mes_bruto:{m['mes_bruto']}, mes_liq:{m['mes_liq']},
    mes_proj_b:{m['mes_proj_b']}, mes_proj_l:{m['mes_proj_l']}, mes_proj_c:{m['mes_proj_c']},
    mes_pdu:{m['mes_pdu']}, mes_tdu:{m['mes_tdu']}, mes_pct:{m['mes_pct']},
    mes_ant_b:{m['mes_ant_b']}, mes_ant_c:{m['mes_ant_c']}, mes_var_b:{m['mes_var_b']},
    mes_prod: {jss(mp)},
    mes_fundo: {jss(mf2)},
    hoje_data: {jss(m['hoje_data'])},
    hoje_c:{m['hoje_c']}, hoje_b:{m['hoje_b']}, hoje_l:{m['hoje_l']},
    hoje_fgts_c:{hoje_fgts_c}, hoje_fgts_b:{hoje_fgts_b}, hoje_fgts_l:{hoje_fgts_l},
    hoje_ec_c:{hoje_ec_c},   hoje_ec_b:{hoje_ec_b},   hoje_ec_l:{hoje_ec_l},
    hoje_prod: {jss(hp)},
    hoje_parc: {jss(m['hoje_parc'])},
    hoje_fundo: {jss(hf)},
    dia_dia: {jss(m['dia_dia'])},
    gerado_em: {jss(datetime.now().strftime('%d/%m/%Y %H:%M'))},
    sup1_n:{jss(sup1['n'])}, sup1_c:{sup1['c']}, sup1_b:{round(sup1['b'],2)}, sup1_l:{round(sup1['l'],2)},
    sup2_n:{jss(sup2['n'])}, sup2_c:{sup2['c']}, sup2_b:{round(sup2['b'],2)}, sup2_l:{round(sup2['l'],2)},
    sup3_n:{jss(sup3['n'])}, sup3_c:{sup3['c']}, sup3_b:{round(sup3['b'],2)}, sup3_l:{round(sup3['l'],2)},
    sup4_n:{jss(sup4['n'])}, sup4_c:{sup4['c']}, sup4_b:{round(sup4['b'],2)}, sup4_l:{round(sup4['l'],2)},
  }},
}};

"""
    p3_bloco = f"""// ===== P3 DATA =====
const P3D = {{
  sup_list: {jss(m['sup_list'])},
  reg_list: {jss(m['reg_list'])},
  mes_list: {jss(m['meses_lbl'])},
  mes_lbl:  {jss({l:l for l in m['meses_lbl']})},
  prod_list: {jss(m.get('prod_list_p3',[]))},
  by_sup:   {jss(by_sup_js)},
  by_reg:   {jss(by_reg_js)},
  by_com:   {jss(by_com_js)},
  by_parc:  {jss(by_parc_js)},
  sup_mes:  {jss(sup_mes_js)},
  reg_mes:  {jss(reg_mes_js)},
  parc_mes: {jss(parc_mes_js)},
  by_sup_prod:  {jss(by_sup_prod_js)},
  by_reg_prod:  {jss(by_reg_prod_js)},
  by_com_prod:  {jss(by_com_prod_js)},
  by_parc_prod: {jss(by_parc_prod_js)},
  sup_mes_prod: {jss(sup_mes_prod_js)},
  reg_mes_prod: {jss(reg_mes_prod_js)},
}};

"""

    mensal_conv_list = {r['m']: r for r in mensal_conv}
    e_mensal = [mensal_conv_list.get(l, {'m':l,'total':0,'desemb':0,'canc':0,'conv':0}) for l in m['meses_lbl']]

    e_bloco = f"""// ===== P4 DATA =====
const E = {{
  porProduto: {jss(e_por_prod)},
  porFundo: {jss(e_por_fundo)},
  statusCompleto: {jss(m['status_list'])},
  mensal: {jss(e_mensal)},
  mensalFGTS: {jss(m['mensal_fgts'])},
  mensalEC:   {jss(m['mensal_ec'])},
  mensalPorProduto: {jss(m.get('mensal_por_produto', {}))},
  prodFundoCompat:  {jss(m.get('prod_fundo_compat', {}))},
  periodos:         {jss(m.get('periodos', {}))},
}};

const F = {{periodo:'todos', produto:'todos', fundo:'todos', status:'todos'}};
let charts4 = {{}};

"""
    return bloco, p3_bloco, e_bloco

# ============================================================
# PASSO 4: ATUALIZAR HTML DINAMICO
# ============================================================
def atualizar_html_dinamico(html, m):
    """Atualiza textos dinamicos no HTML (KPIs, datas, etc.)"""
    def fmt_k(v):
        if abs(v) >= 1_000_000: return f"R$ {v/1_000_000:.2f}M"
        return f"R$ {v/1_000:.0f}K"
    def fmt_n(v): return f"{int(v):,}".replace(',','.')

    meta = m
    total_reg  = meta['total_reg']
    total_des  = meta['total_des']
    conv_geral = round(total_des/total_reg*100,1) if total_reg else 0
    total_b    = meta['total_bruto']

    cp = m['conv_prod']
    outros = sorted([x for x in cp if x.get('Produto')!='FGTS'], key=lambda x: int(x.get('Total',0)), reverse=True)
    nome_ec = outros[0]['Produto'] if outros else 'E-CONSIGNADO'
    fgts_total = next((int(r.get('Total',0)) for r in cp if r.get('Produto')=='FGTS'), 0)
    fgts_des   = next((int(r.get('Desemb',0)) for r in cp if r.get('Produto')=='FGTS'), 0)
    ec_total   = next((int(r.get('Total',0)) for r in cp if r.get('Produto')==nome_ec), 0)
    ec_des     = next((int(r.get('Desemb',0)) for r in cp if r.get('Produto')==nome_ec), 0)
    fgts_b = sum(r['b'] for r in m['prod_rows'] if r['p']=='FGTS')
    ec_b   = sum(r['b'] for r in m['prod_rows'] if r['p']==nome_ec)

    st = {r['s']:r['v'] for r in m['status_list']}
    st_des  = st.get('Desembolsado', 0)
    st_canc = st.get('Cancelado', 0)
    st_ag   = sum(v for k,v in st.items() if k not in ['Desembolsado','Cancelado'])
    sups_js = m['sups']
    sup1 = sups_js[0] if len(sups_js)>0 else {'n':'-','c':0,'b':0,'l':0}
    sup2 = sups_js[1] if len(sups_js)>1 else {'n':'-','c':0,'b':0,'l':0}
    sup3 = sups_js[2] if len(sups_js)>2 else {'n':'-','c':0,'b':0,'l':0}
    sup4 = sups_js[3] if len(sups_js)>3 else {'n':'-','c':0,'b':0,'l':0}

    subs = {
        '78.513 registros': f"{fmt_n(total_reg)} registros",
        'Ref. 11/05/2026': f"Ref. {meta['data_ref']}",
        'Ref. 12/09/2025': f"Ref. {meta['data_ref']}",
        '>54.926<': f">{fmt_n(total_des)}<",
        '>de 78.513 digitados<': f">de {fmt_n(total_reg)} digitados<",
        '>70,0% conversão<': f">{conv_geral}% conversão<",
    }

    for old, new in subs.items():
        if old in html and old != new:
            html = html.replace(old, new, 1)

    return html


# ============================================================
# PASSO 4B: EMBUTIR CHART.JS NO HTML (funciona offline)
# ============================================================
def embutir_chartjs(html):
    cache_path = os.path.join(PASTA, 'chartjs.cache.js')
    chartjs_code = None

    if os.path.exists(cache_path):
        try:
            chartjs_code = open(cache_path, encoding='utf-8', errors='ignore').read()
            log(f"  Chart.js carregado do cache ({len(chartjs_code):,} chars)")
        except Exception as e:
            log(f"  Erro ao ler cache: {e}")

    if not chartjs_code:
        log("  Tentando baixar Chart.js...")
        try:
            import requests
            urls = [
                'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js',
                'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js',
            ]
            for url in urls:
                try:
                    r = requests.get(url, timeout=15, verify=False)
                    if r.status_code == 200 and len(r.content) > 10000:
                        chartjs_code = r.text
                        open(cache_path, 'w', encoding='utf-8').write(chartjs_code)
                        log(f"  Baixado e salvo em cache ({len(chartjs_code):,} chars)")
                        break
                except: continue
        except: pass

    if chartjs_code:
        import re as _re
        m = _re.search(r'<script[^>]+chart\.umd\.min\.js[^>]*>(?:</script>)?', html)
        if m:
            old_tag = m.group(0)
            new_tag = '<script>\n' + chartjs_code + '\n</script>'
            html = html.replace(old_tag, new_tag)
            log("  Chart.js embutido no HTML (funciona 100% offline)")
        else:
            log("  Aviso: tag Chart.js nao encontrada no template")
    else:
        log("  Aviso: Chart.js nao disponivel offline - necessario internet")

    return html


# ============================================================
# MAIN
# ============================================================
def main():
    log('=' * 55)
    log('  2S CONSIG - PROCESSAMENTO + GERACAO DO PAINEL BI')
    log('=' * 55)
    print()

    df = processar_dados()
    print()

    metricas = calcular_metricas(df)
    log(f'Periodo: {metricas["meses_lbl"][0]} -> {metricas["meses_lbl"][-1]}')
    log(f'Ref: {metricas["data_ref"]} | Total: {metricas["total_reg"]:,} | Des: {metricas["total_des"]:,}')
    print()

    log('Gerando painel HTML...')
    bloco_d, bloco_p3, bloco_e4 = gerar_js_dados(metricas)

    template_path = os.path.join(PASTA, 'template_bi_2s.html')
    if not os.path.exists(template_path):
        log('ERRO: template_bi_2s.html nao encontrado na pasta!')
        if os.environ.get('NO_BROWSER') != '1':
            input('\nPressione ENTER para fechar...')
        sys.exit(1)

    html = open(template_path, encoding='utf-8').read()
    html = html.replace('__PAINEL_USERS_OBJ__', jss(load_panel_users()))

    # ── Injetar usuarios com senha hasheada ──────────────────────
    import hashlib as _hashlib, json as _json
    _usuarios_path = os.path.join(PASTA, 'usuarios.json')
    if os.path.exists(_usuarios_path):
        with open(_usuarios_path, encoding='utf-8') as _f:
            _usuarios_raw = _json.load(_f)
        _usuarios_hash = {u.upper(): _hashlib.sha256(p.encode()).hexdigest()
                          for u, p in _usuarios_raw.items()}
        log(f'Usuarios carregados: {", ".join(_usuarios_hash.keys())}')
    else:
        # fallback: sem arquivo, bloqueia acesso
        _usuarios_hash = {}
        log('AVISO: usuarios.json nao encontrado — nenhum usuario habilitado')
    html = html.replace('%%USUARIOS_HASH%%', _json.dumps(_usuarios_hash))

    M_START = '// %%DADOS_INICIO%%\n'
    M_END   = '// %%DADOS_FIM%%\n'
    ms = html.find(M_START)
    me = html.find(M_END)
    if ms == -1 or me == -1:
        log('ERRO: Marcadores nao encontrados no template.')
        if os.environ.get('NO_BROWSER') != '1':
            input('\nPressione ENTER para fechar...')
        sys.exit(1)
    html = html[:ms] + M_START + bloco_d + M_END + html[me + len(M_END):]

    p3s = html.find('// ===== P3 DATA =====')
    p3e = html.find('const P3F =', p3s)
    if p3s != -1 and p3e != -1:
        html = html[:p3s] + bloco_p3 + html[p3e:]

    e4s = html.find('// ===== P4 DATA INICIO =====')
    e4e = html.find('// ===== P4 DATA FIM =====', e4s)
    if e4s != -1 and e4e != -1:
        html = html[:e4s] + bloco_e4 + html[e4e + len('// ===== P4 DATA FIM =====\n'):]

    html = atualizar_html_dinamico(html, metricas)
    html = embutir_chartjs(html)

    tmp_html = ARQUIVO_HTML + '.tmp'
    with open(tmp_html, 'w', encoding='utf-8') as f:
        f.write(html)
    os.replace(tmp_html, ARQUIVO_HTML)
    arq_final = os.path.join(PASTA, 'painel_bi_2s_FINAL.html')
    try:
        with open(arq_final, 'w', encoding='utf-8') as f:
            f.write(html)
        log(f"  Tambem salvo: {os.path.basename(arq_final)}")
    except Exception as e:
        log(f"  Aviso: nao consegui salvar _FINAL ({e}) - talvez esteja aberto no navegador")

    # Verifica integridade do painel salvo
    try:
        with open(ARQUIVO_HTML, 'r', encoding='utf-8') as f:
            conteudo = f.read()
        tam = len(conteudo)
        ok_fim = conteudo.rstrip().endswith('</html>')
        n_open = conteudo.count('<script')
        n_close = conteudo.count('</script>')
        if not ok_fim or n_open != n_close:
            log('  ===========================================================')
            log(f'  AVISO: PAINEL TRUNCADO! Tamanho: {tam:,} bytes')
            log(f'  Termina em </html>: {ok_fim} | <script>:{n_open} </script>:{n_close}')
            log('  -> FECHE o painel no Chrome e rode o RODAR.bat de novo!')
            log('  ===========================================================')
        else:
            log(f'  Painel integro: {tam:,} bytes')
    except Exception as e:
        log(f'  Aviso: verificacao falhou ({e})')

    print()
    log('=' * 55)
    log('  CONCLUIDO COM SUCESSO!')
    log('=' * 55)
    log(f'Painel: {os.path.basename(ARQUIVO_HTML)}')
    log(f'Periodo     : {metricas["meses_lbl"][0]} -> {metricas["meses_lbl"][-1]}')
    log(f'Contratos   : {metricas["total_des"]:,} desembolsados de {metricas["total_reg"]:,}')
    log(f'Prod. Bruta : R$ {metricas["total_bruto"]:,.2f}')
    print()
    if os.environ.get('NO_BROWSER') != '1':
        log('Abrindo o painel no navegador...')
        import webbrowser
        webbrowser.open('file:///' + ARQUIVO_HTML.replace(os.sep, '/'))
        input('\nPressione ENTER para fechar...')
    else:
        log('NO_BROWSER=1, pulando abertura do navegador')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'\nERRO: {e}')
        import traceback; traceback.print_exc()
        if os.environ.get('NO_BROWSER') != '1':
            input('\nPressione ENTER para fechar...')
