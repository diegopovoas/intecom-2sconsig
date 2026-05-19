"""
Servidor web simples para o Painel BI 2S Consig.
Serve o painel_bi_2s.html gerado pelo processar_2s.py.
Acesso: http://<ip-do-servidor>:8080
"""
import os
import sys
from datetime import datetime

try:
    from flask import Flask, send_file, abort
except ImportError:
    print("Instalando Flask...")
    os.system(f'"{sys.executable}" -m pip install flask -q')
    from flask import Flask, send_file, abort

PASTA  = os.path.dirname(os.path.abspath(__file__))
PAINEL = os.path.join(PASTA, 'painel_bi_2s.html')
PORTA  = int(os.environ.get('PORTA', 8080))

app = Flask(__name__)

@app.route('/')
def index():
    if not os.path.exists(PAINEL):
        abort(503, 'Painel ainda não gerado. Execute RODAR.bat primeiro.')
    return send_file(PAINEL)

@app.route('/status')
def status():
    if not os.path.exists(PAINEL):
        return {'ok': False, 'msg': 'painel nao encontrado'}, 503
    mtime = os.path.getmtime(PAINEL)
    ultima = datetime.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M:%S')
    tam    = os.path.getsize(PAINEL)
    return {'ok': True, 'ultima_atualizacao': ultima, 'tamanho_bytes': tam}

if __name__ == '__main__':
    import socket
    ip = socket.gethostbyname(socket.gethostname())
    print('=' * 55)
    print('  2S CONSIG - Servidor do Painel BI')
    print('=' * 55)
    print(f'  Local   : http://localhost:{PORTA}')
    print(f'  Rede    : http://{ip}:{PORTA}')
    print(f'  Status  : http://{ip}:{PORTA}/status')
    print()
    print('  Deixe esta janela aberta.')
    print('  Para parar: Ctrl+C')
    print('=' * 55)
    app.run(host='0.0.0.0', port=PORTA, debug=False)
