# Contexto — 2S Consig BI

## Visão Geral
Painel de gestão da 2S Consig (produção, pagamentos, parceiros, esteira).
Atualização automática a cada 15 min via Agendador de Tarefas do Windows.
Desde 11/06/2026: dados protegidos por login real (Supabase Auth + RLS) —
o GitHub Pages serve apenas a "casca" de login, sem nenhum dado.

## Links
- **Painel:** https://diegopovoas.github.io/intecom-2sconsig/
- **Gestão de usuários (admin):** https://diegopovoas.github.io/intecom-2sconsig/usuarios.html
- **GitHub:** https://github.com/diegopovoas/intecom-2sconsig
- **Supabase:** projeto `uhjnfdyfyealtmbldjso` (2S Consig - Gestão, São Paulo)

## Arquitetura
```
MySQL (2sconsig.novapowerhub.com.br:3306, banco twosconsig)
    ↓ a cada 15 min (tarefa "Atualizar BI 2S" → RODAR_AUTO.vbs)
atualizar_via_db.py → producao.parquet
    ↓
processar_2s.py → painel_bi_2s.html (local, gitignored)
    ↓
publicar_supabase.py → tabela painel_cache (HTML protegido por login)

index.html (GitHub Pages) = login Supabase → baixa o painel do banco →
injeta menu (⚙️ Usuários p/ admin + ⏻ Sair) → auto-refresh a cada 5 min
```

## Como Usar
| Arquivo | Ação |
|---|---|
| `RODAR.bat` | Execução manual com output na tela |
| `RODAR_SILENCIOSO.bat` | Execução silenciosa (usada pela tarefa agendada) |
| `RODAR_AUTO.vbs` | Lançador invisível da tarefa do Windows |
| `AGENDAR_TAREFA.bat` | (Re)configura a tarefa automática no Windows |

## Usuários
Gestão 100% online em `/usuarios.html` (criar, editar, senha, bloquear, excluir).
Papéis: `admin` (gerencia usuários) e `user` (só vê o painel).
Setup do banco: `_supabase/setup_2s.sql`. Credenciais: `_supabase/config.json` (gitignored).

## Arquivos sensíveis (gitignored, nunca versionar)
`credenciais_db.txt` · `_supabase/config.json` · `producao.parquet` ·
`dados_2s.xlsx` · `painel_bi_2s.html` / `_FINAL.html` · `log_execucao.txt`

## Recuperação de Desastre
1. Novo projeto Supabase → rodar `_supabase/setup_2s.sql`
2. Atualizar URL/chaves em `_supabase/config.json`, `index.html` e `usuarios.html`
3. Recriar usuários em `/usuarios.html` (primeiro admin via script/SQL)
4. Rodar `RODAR.bat`

<!-- teste de auto-deploy Vercel: 2026-06-25T20:37:16Z -->
<!-- teste final auto-deploy 2026-06-25T20:46:56Z -->
