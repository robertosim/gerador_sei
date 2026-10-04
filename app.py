import os
import re
import csv
import io
import json
import time
import logging
import traceback
import threading
import subprocess
import socket
import webbrowser
import urllib.parse
import urllib.request
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, jsonify, Response
from werkzeug.exceptions import HTTPException
from database import (get_db, init_db, DEFAULT_CONFIG, DEFAULT_CONFIG_GERACAO, DB_PATH,
                      processar_nome_arvore_template)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, 'processos_sei.log')
CSV_DIR = os.path.join(BASE_DIR, 'csv')
CHROME_DEBUG_PORT = 9222
SERVIDOR_PORTA = 5000
SERVIDOR_URL = f'http://localhost:{SERVIDOR_PORTA}'
KEEPALIVE_INTERVALO = 60


def porta_aberta(porta, host='127.0.0.1', timeout=2):
    try:
        with socket.create_connection((host, porta), timeout=timeout):
            return True
    except OSError:
        return False


def verificar_chrome_debug():
    """Garante o Chrome em modo debug; retorna True se a porta 9222 responder."""
    if porta_aberta(CHROME_DEBUG_PORT):
        log.info('Chrome ja esta rodando em modo debug na porta %d', CHROME_DEBUG_PORT)
        return True

    log.info('Chrome nao encontrado em modo debug. Iniciando Chrome com --remote-debugging-port=%d...', CHROME_DEBUG_PORT)
    try:
        chrome_paths = [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            os.path.expanduser(r'~\AppData\Local\Google\Chrome\Application\chrome.exe'),
        ]
        chrome_exe = next((p for p in chrome_paths if os.path.exists(p)), None)

        if not chrome_exe:
            log.warning('Chrome nao encontrado nos caminhos padrao')
            return False

        # Perfil separado: sem ele a instancia ja aberta do Chrome absorve o
        # comando e a porta 9222 nunca abre.
        chrome_profile = os.path.join(os.environ.get('SystemDrive', 'C:'), 'ChromeDebug')
        subprocess.Popen([
            chrome_exe,
            f'--remote-debugging-port={CHROME_DEBUG_PORT}',
            f'--user-data-dir={chrome_profile}',
            '--no-first-run',
            '--no-default-browser-check',
            'https://sei.incra.gov.br'
        ], cwd=os.path.dirname(chrome_exe))

        for _ in range(20):
            time.sleep(1)
            if porta_aberta(CHROME_DEBUG_PORT):
                log.info('Chrome iniciado com sucesso em modo debug (perfil %s)', chrome_profile)
                return True

        log.warning('Chrome iniciado mas porta %d nao respondeu em 20s', CHROME_DEBUG_PORT)
        return False
    except Exception as e:
        log.error('Erro ao iniciar Chrome: %s', e)
        return False


def abrir_aba_chrome_debug(url):
    """Abre uma aba na instancia do Chrome debug via endpoint DevTools."""
    endpoint = f'http://127.0.0.1:{CHROME_DEBUG_PORT}/json/new?{urllib.parse.quote(url, safe="")}'
    req = urllib.request.Request(endpoint, method='PUT')
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status in (200, 201)


def abrir_aba_do_servidor(url=SERVIDOR_URL):
    """Espera o servidor subir e abre uma aba com o painel no navegador.

    Prefere a instancia do Chrome debug (a mesma usada pela automacao) e usa
    o navegador padrao como fallback. Desativavel com GERADOR_SEI_SEM_ABA=1.
    """
    if os.environ.get('GERADOR_SEI_SEM_ABA'):
        log.info('GERADOR_SEI_SEM_ABA ativo: aba do painel nao sera aberta')
        return

    for _ in range(60):
        if porta_aberta(SERVIDOR_PORTA):
            break
        time.sleep(1)
    else:
        log.warning('Servidor nao respondeu na porta %d em 60s; aba nao aberta', SERVIDOR_PORTA)
        return

    # A inicializacao do Chrome debug pode levar ate 20s
    for _ in range(30):
        if porta_aberta(CHROME_DEBUG_PORT):
            break
        time.sleep(1)

    for tentativa in range(3):
        try:
            if abrir_aba_chrome_debug(url):
                log.info('Aba do painel aberta no Chrome debug: %s', url)
                return
        except Exception as e:
            log.debug('Tentativa %d de abrir aba via DevTools falhou: %s', tentativa + 1, e)
        time.sleep(2)

    log.info('Abrindo painel no navegador padrao: %s', url)
    webbrowser.open(url)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        RotatingFileHandler(LOG_PATH, maxBytes=5_000_000, backupCount=3, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('anexador')

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
# Sem isso o template fica compilado em memoria e alteracoes em
# templates/index.html so aparecem apos reiniciar o servidor.
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

init_db()
log.info('Aplicacao iniciada | DB: %s | Uploads: %s', DB_PATH, app.config['UPLOAD_FOLDER'])

_keepalive_iniciado = False
KEEPALIVE_CFG_PATH = os.path.join(BASE_DIR, 'keepalive.json')


def _ler_keepalive_cfg():
    """Le a preferencia de keep-alive (sobrevive a reinicios do app)."""
    try:
        with open(KEEPALIVE_CFG_PATH, 'r', encoding='utf-8') as f:
            d = json.load(f)
        return {'ativo': bool(d.get('ativo', True)),
                'intervalo': int(d.get('intervalo', KEEPALIVE_INTERVALO))}
    except Exception:
        return {'ativo': True, 'intervalo': KEEPALIVE_INTERVALO}


def _salvar_keepalive_cfg(ativo, intervalo=None):
    try:
        d = _ler_keepalive_cfg()
        d['ativo'] = bool(ativo)
        if intervalo:
            d['intervalo'] = int(intervalo)
        with open(KEEPALIVE_CFG_PATH, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        return d
    except Exception as e:
        log.error('Erro ao salvar config do keep-alive: %s', e)
        return None


def iniciar_keepalive_app(ativo=None, intervalo=None):
    """Inicia a thread que recarrega a aba do SEI quando o app esta ocioso.

    `ativo=None` usa a preferencia salva; nunca sobrescreve a escolha do
    usuario quando a thread ja esta rodando.
    """
    global _keepalive_iniciado
    cfg = _ler_keepalive_cfg()
    if ativo is None:
        ativo = cfg['ativo']
    if intervalo is None:
        intervalo = cfg['intervalo']
    if _keepalive_iniciado:
        return True
    try:
        from sei import iniciar_keepalive
        iniciar_keepalive(ativo=ativo, intervalo=int(intervalo))
        _keepalive_iniciado = True
        log.info('Keep-alive do SEI %s: recarga a cada %ds quando ocioso',
                 'ativo' if ativo else 'iniciado porem desativado', intervalo)
        return True
    except Exception as e:
        log.error('Erro ao iniciar keep-alive: %s\n%s', e, traceback.format_exc())
        return False


# O reloader do Flask executa o modulo no processo pai e no filho; tudo que
# dispara uma vez so pode rodar no filho (WERKZEUG_RUN_MAIN=true) ou quando
# nao ha reloader (WERKZEUG_SERVER_FD ausente).
def processo_principal():
    return os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or 'WERKZEUG_SERVER_FD' not in os.environ


if processo_principal():
    iniciar_keepalive_app()
    # Nao bloqueia o startup: abrir o Chrome debug pode demorar ate 20s
    threading.Thread(target=verificar_chrome_debug, daemon=True).start()


@app.before_request
def log_request():
    log.info('>>> %s %s | IP=%s | Content-Type=%s',
             request.method, request.url, request.remote_addr, request.content_type)


@app.after_request
def log_response(response):
    log.info('<<< %s %s -> %s', request.method, request.url, response.status_code)
    return response


@app.errorhandler(Exception)
def handle_exception(e):
    # 404/405 etc: resposta normal do Flask, sem traceback no log
    if isinstance(e, HTTPException):
        log.warning('%s %s -> %s', request.method, request.url, e.code)
        return e
    log.error('EXCECAO NAO TRATADA: %s\n%s', str(e), traceback.format_exc())
    return jsonify({'error': str(e)}), 500


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    log.info('--- INICIO upload-csv ---')

    if 'csv_file' not in request.files:
        log.warning('Nenhum campo csv_file no request')
        return jsonify({'error': 'Nenhum arquivo CSV enviado'}), 400

    file = request.files['csv_file']
    log.info('Arquivo recebido: filename=%s, content_type=%s, tamanho=%s bytes',
             file.filename, file.content_type, file.content_length)

    if file.filename == '':
        log.warning('Filename vazio')
        return jsonify({'error': 'Nenhum arquivo selecionado'}), 400

    if not file.filename.lower().endswith('.csv'):
        log.warning('Arquivo nao e CSV: %s', file.filename)
        return jsonify({'error': 'Arquivo deve ser CSV'}), 400

    try:
        raw = file.read()
        log.info('Bytes lidos: %d', len(raw))
        log.debug('Primeiros 100 bytes: %s', raw[:100])

        content = None
        encoding_usado = None
        for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']:
            try:
                content = raw.decode(enc)
                encoding_usado = enc
                log.info('Encoding detectado: %s', enc)
                break
            except (UnicodeDecodeError, LookupError) as e:
                log.debug('Encoding %s falhou: %s', enc, e)
                continue

        if content is None:
            content = raw.decode('latin-1', errors='replace')
            encoding_usado = 'latin-1 (fallback com replace)'
            log.warning('Nenhum encoding funcionou, usando latin-1 com replace')

        sample = content[:4096]
        delimiter = ';'
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=';,|\t')
            delimiter = dialect.delimiter
            log.info('Delimiter detectado por Sniffer: %r', delimiter)
        except csv.Error as e:
            log.warning('Sniffer falhou: %s | usando ; como padrao', e)

        if ';' in content[:500]:
            delimiter = ';'
            log.info('Delimitador confirmado: ; (encontrado no header)')

        log.info('Encoding final: %s | Delimiter: %r', encoding_usado, delimiter)

        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
        colunas_encontradas = reader.fieldnames or []
        log.info('Colunas no CSV: %s', colunas_encontradas)

        def normalize(s):
            import unicodedata
            s = unicodedata.normalize('NFKD', s)
            s = s.encode('ascii', 'ignore').decode('ascii')
            return s.strip().upper()

        def find_col(row, *candidates):
            cols = list(row.keys())
            norm_cols = {normalize(c): c for c in cols}
            for c in candidates:
                nc = normalize(c)
                if nc in norm_cols:
                    log.debug('Coluna encontrada: %s -> %s', c, norm_cols[nc])
                    return norm_cols[nc]
            for c in candidates:
                nc = normalize(c)
                for ncol, orig in norm_cols.items():
                    if nc in ncol:
                        log.debug('Coluna encontrada (fuzzy): %s -> %s', c, orig)
                        return orig
            log.warning('Coluna nao encontrada entre: %s | disponiveis: %s', candidates, list(norm_cols.keys()))
            return None

        db = get_db()
        # Como na extensao: o novo CSV atualiza a lista sem apagar o que ja
        # existe (mantem PDF, status de anexacao e registros fora do CSV).
        existentes = {}
        for r in db.execute('SELECT id, cod_sipra FROM anexos_sei').fetchall():
            existentes[str(r['cod_sipra'] or '').strip().upper()] = r['id']
        log.info('anexos_sei existentes: %d (merge com o CSV)', len(existentes))

        inseridos = 0
        atualizados = 0
        erros_linha = 0
        for i, row in enumerate(reader, start=2):
            try:
                col_cod = find_col(row, 'CODIGO BENEFICIARIO', 'CODIGO DO BENEFICIARIO', 'COD. BENEFICIARIO', 'CODIGO SIPRA', 'COD_SIPRA')
                col_proc = find_col(row, 'NO PROCESSO SEI', 'PROCESSO SEI', 'PROC SEI', 'PROCESSO')
                col_nome = find_col(row, 'NOME TITULAR 1', 'BENEFICIARIO', 'NOME')

                cod = row.get(col_cod, '').strip() if col_cod else ''
                proc = row.get(col_proc, '').strip() if col_proc else ''
                nome = row.get(col_nome, '').strip() if col_nome else ''

                if cod:
                    chave = cod.strip().upper()
                    id_existente = existentes.get(chave)
                    if id_existente:
                        sets, vals = [], []
                        if nome:
                            sets.append('nome = ?')
                            vals.append(nome)
                        if proc:
                            sets.append('processo_sei = ?')
                            vals.append(proc)
                        if sets:
                            vals.append(id_existente)
                            db.execute(
                                f'UPDATE anexos_sei SET {", ".join(sets)} WHERE id = ?',
                                vals
                            )
                        atualizados += 1
                    else:
                        db.execute(
                            'INSERT INTO anexos_sei (cod_sipra, nome, processo_sei, pdf_anexo, anexado) VALUES (?, ?, ?, ?, 0)',
                            (cod, nome, proc, '')
                        )
                        inseridos += 1
                else:
                    erros_linha += 1
                    log.warning('Linha %d: codigo sipra vazio | dados: %s', i, dict(row))
            except Exception as e:
                erros_linha += 1
                log.error('Erro na linha %d: %s | dados: %s', i, e, dict(row))

        db.commit()
        mantidos = len(existentes)
        db.close()

        log.info('--- FIM upload-csv | inseridos=%d | atualizados=%d | mantidos=%d | erros=%d ---',
                 inseridos, atualizados, mantidos, erros_linha)
        return jsonify({'success': True, 'inseridos': inseridos,
                        'atualizados': atualizados, 'mantidos': mantidos})
    except Exception as e:
        log.error('ERRO upload-csv: %s\n%s', e, traceback.format_exc())
        return jsonify({'error': str(e)}), 500


# Padrao do codigo SIPRA: duas letras seguidas de digitos (ex.: MS001200000001).
# As bordas impedem pegar pedacos de palavras ("relatorio2024" nao vira "io2024").
PADRAO_CODIGO = re.compile(r'(?<![A-Za-z0-9])([A-Za-z]{2}\d{4,})(?![A-Za-z0-9])')

_REGEX_CODIGO = {}


def _so_alnum(txt):
    """Mantem so letras/digitos e maiusculas: compara codigo com nome de arquivo."""
    return re.sub(r'[^A-Za-z0-9]', '', txt or '').upper()


def _regex_do_codigo(cod_norm):
    """Regex do codigo com fronteiras: casa "MS 001200000001" e "unidade-familiar-
    MS001200000001", mas nao "MS001200000001" dentro de "MS0012000000012"."""
    r = _REGEX_CODIGO.get(cod_norm)
    if r is None:
        partes = re.match(r'^([A-Za-z]+)(\d+)$', cod_norm)
        if partes:
            r = re.compile(
                r'(?<![A-Za-z0-9])' + re.escape(partes.group(1))
                + r'[\s._\-]*' + re.escape(partes.group(2)) + r'(?!\d)',
                re.IGNORECASE)
        else:
            r = re.compile(re.escape(cod_norm), re.IGNORECASE)
        _REGEX_CODIGO[cod_norm] = r
    return r


def extrair_codigo(nome_arquivo, codigos):
    """Codigo do registro que aparece no nome do PDF.

    codigos: dict {codigo_normalizado: codigo_original} vindo do banco (CSV).

    1) o codigo do banco casado com fronteiras no nome do arquivo;
    2) o codigo como texto puro no nome, sem depender de separadores
       (cobre "MS001200000001MARIA.pdf" e prefixos de pasta);
    3) se o codigo nao esta no banco, o token que case com o padrao
       <2 letras><digitos> e devolvido (gera registro novo).
    """
    base = os.path.basename(str(nome_arquivo or '').replace('\\', '/'))
    if base.lower().endswith('.pdf'):
        base = base[:-4]
    nome_norm = _so_alnum(base)

    melhor, melhor_len = '', 0

    for cod_norm, cod in codigos.items():
        if cod_norm and len(cod_norm) > melhor_len and _regex_do_codigo(cod_norm).search(base):
            melhor, melhor_len = cod, len(cod_norm)

    if not melhor:
        for cod_norm, cod in codigos.items():
            if not cod_norm or len(cod_norm) <= melhor_len:
                continue
            pos = nome_norm.find(cod_norm)
            while pos >= 0:
                fim = pos + len(cod_norm)
                # "MS0012000000012" nao pode casar com "MS001200000001"
                if fim >= len(nome_norm) or not nome_norm[fim].isdigit():
                    melhor, melhor_len = cod, len(cod_norm)
                    break
                pos = nome_norm.find(cod_norm, pos + 1)

    if melhor:
        return melhor

    for token in PADRAO_CODIGO.findall(base):
        return codigos.get(token.upper(), token.upper())
    return ''


@app.route('/api/upload-pdfs', methods=['POST'])
def upload_pdfs():
    log.info('--- INICIO upload-pdfs ---')

    if 'pdf_files' not in request.files:
        log.warning('Nenhum campo pdf_files no request')
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400

    files = request.files.getlist('pdf_files')
    if not files or all(f.filename == '' for f in files):
        log.warning('Nenhum arquivo selecionado')
        return jsonify({'error': 'Nenhum arquivo selecionado'}), 400

    log.info('Arquivos recebidos: %d', len(files))

    pdf_dir = app.config['UPLOAD_FOLDER']
    os.makedirs(pdf_dir, exist_ok=True)

    db = get_db()

    # Codigos vindo do CSV (aba Gerar): {normalizado: original}. A associacao
    # compara o codigo com o NOME DO ARQUIVO, entao "MS001200000001 - MARIA.pdf"
    # ou "unidade-familiar-MS001200000001.pdf" caem no mesmo registro.
    codigos_db = {}
    for r in db.execute('SELECT cod_sipra FROM anexos_sei').fetchall():
        cod = str(r['cod_sipra'] or '').strip()
        if cod:
            codigos_db[_so_alnum(cod)] = cod
    log.info('Codigos no banco para associacao: %d', len(codigos_db))

    associados = 0
    ignorados = 0
    novos = 0
    resultados = []

    for i, f in enumerate(files, start=1):
        raw_name = f.filename or ''
        nome_arquivo = os.path.basename(raw_name.replace('\\', '/'))
        log.debug('Arquivo %d/%d: raw=%s | nome=%s | content_type=%s', i, len(files), raw_name, nome_arquivo, f.content_type)

        if not nome_arquivo.lower().endswith('.pdf'):
            ignorados += 1
            log.debug('Ignorado (nao e PDF): %s', nome_arquivo)
            continue

        cod_sipra = extrair_codigo(nome_arquivo, codigos_db)
        if not cod_sipra:
            ignorados += 1
            resultados.append({'arquivo': nome_arquivo, 'status': 'sem_codigo', 'codigo': None})
            log.warning('Ignorado (sem codigo <2 letras><digitos>): %s', nome_arquivo)
            continue

        log.debug('Codigo SIPRA extraido: %s de %s', cod_sipra, nome_arquivo)

        try:
            caminho_salvar = os.path.join(pdf_dir, nome_arquivo)
            f.save(caminho_salvar)
            log.debug('Arquivo salvo: %s', caminho_salvar)
        except Exception as e:
            log.error('Erro ao salvar %s: %s\n%s', nome_arquivo, e, traceback.format_exc())
            ignorados += 1
            continue

        row = db.execute(
            'SELECT id FROM anexos_sei WHERE UPPER(cod_sipra) = UPPER(?)', (cod_sipra,)
        ).fetchone()

        if row:
            db.execute(
                'UPDATE anexos_sei SET pdf_anexo = ?, anexado = 0 WHERE id = ?',
                (nome_arquivo, row['id'])
            )
            associados += 1
            resultados.append({'arquivo': nome_arquivo, 'status': 'ok', 'codigo': cod_sipra})
            log.debug('Associado ao registro existente: %s -> %s', nome_arquivo, cod_sipra)
        else:
            db.execute(
                'INSERT INTO anexos_sei (cod_sipra, nome, processo_sei, pdf_anexo, anexado) VALUES (?, ?, ?, ?, 0)',
                (cod_sipra, '', '', nome_arquivo)
            )
            codigos_db[_so_alnum(cod_sipra)] = cod_sipra
            novos += 1
            resultados.append({'arquivo': nome_arquivo, 'status': 'novo', 'codigo': cod_sipra})
            log.debug('Novo registro criado: %s -> %s', nome_arquivo, cod_sipra)

    db.commit()
    db.close()

    associados += novos
    log.info('--- FIM upload-pdfs | associados=%d (novos=%d) | ignorados=%d ---',
             associados, novos, ignorados)
    return jsonify({
        'success': True,
        'associados': associados,
        'novos': novos,
        'ignorados': ignorados,
        'resultados': resultados
    })


@app.route('/api/registros')
def get_registros():
    db = get_db()
    rows = db.execute('''
        SELECT a.*, 
               td.nome as tipo_documento_nome,
               hl.nome as hipotese_legal_nome,
               (SELECT pg.processo_gerado FROM processos_gerados pg
                 WHERE pg.cod_beneficiario = a.cod_sipra
                   AND pg.status = 1
                   AND pg.processo_gerado IS NOT NULL
                   AND pg.processo_gerado <> ''
                 ORDER BY pg.id DESC LIMIT 1) as processo_gerado
        FROM anexos_sei a
        LEFT JOIN tipo_documento td ON a.tipo_documento = td.codigo
        LEFT JOIN hipotese_legal hl ON a.hipotese_legal = hl.codigo
        ORDER BY a.cod_sipra
    ''').fetchall()
    db.close()
    resultado = []
    for r in rows:
        item = dict(r)
        # Mostra o nome ja resolvido; se faltar dado no registro (sem CSV),
        # mostra o proprio coringa em vez de deixar a coluna vazia.
        processado = processar_nome_arvore_template(item.get('nome_arvore'), item)
        item['nome_arvore_processado'] = processado or item.get('nome_arvore') or ''
        resultado.append(item)
    return jsonify(resultado)


@app.route('/api/limpar', methods=['POST'])
def limpar_tabela():
    log.info('Limpando tabela anexos_sei')
    db = get_db()
    db.execute('DELETE FROM anexos_sei')
    db.commit()
    db.close()
    return jsonify({'success': True})


@app.route('/api/atualizar-campo', methods=['POST'])
def atualizar_campo():
    try:
        data = request.get_json(force=True)
        campo = data.get('campo')
        valor = data.get('valor')
        registro_id = data.get('id')
        
        campos_permitidos = ['nome', 'processo_sei', 'pdf_anexo', 'tipo_documento', 'nome_arvore', 'nivel_acesso', 'hipotese_legal']
        if campo not in campos_permitidos:
            return jsonify({'error': 'Campo nao permitido'}), 400
        
        db = get_db()
        db.execute(f'UPDATE anexos_sei SET {campo} = ? WHERE id = ?', (valor, registro_id))
        db.commit()
        db.close()
        
        log.info('Campo atualizado: id=%s, campo=%s, valor=%s', registro_id, campo, valor)
        return jsonify({'success': True})
    except Exception as e:
        log.error('ERRO ao atualizar campo: %s', e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats')
def get_stats():
    db = get_db()
    total = db.execute('SELECT COUNT(*) FROM anexos_sei').fetchone()[0]
    com_pdf = db.execute('SELECT COUNT(*) FROM anexos_sei WHERE anexado = 1').fetchone()[0]
    erros = db.execute('SELECT COUNT(*) FROM anexos_sei WHERE anexado = -1').fetchone()[0]
    sem_pdf = total - com_pdf - erros
    com_processo = db.execute("SELECT COUNT(*) FROM anexos_sei WHERE processo_sei != '' AND processo_sei IS NOT NULL").fetchone()[0]
    db.close()
    return jsonify({
        'total': total,
        'com_pdf': com_pdf,
        'erros': erros,
        'sem_pdf': sem_pdf,
        'com_processo': com_processo
    })


@app.route('/api/config', methods=['GET'])
def get_config():
    db = get_db()
    row = db.execute('SELECT * FROM config_anexo LIMIT 1').fetchone()
    db.close()
    if row:
        cfg = dict(row)
        log.info('Config carregada do banco: %s', cfg)
        return jsonify(cfg)
    log.info('Config padrao retornada')
    return jsonify(DEFAULT_CONFIG)


@app.route('/api/config', methods=['POST'])
def save_config():
    try:
        cfg = request.get_json(force=True)
        log.info('Salvando config: %s', cfg)

        # "null"/"None" vem dos placeholders antigos dos <option>: nunca devem
        # parar no banco (viravam a string literal "null" no tipo_documento).
        def limpar(valor, padrao=''):
            if valor is None:
                return padrao
            texto = str(valor).strip()
            if texto.lower() in ('null', 'none'):
                return padrao
            return texto

        serie = limpar(cfg.get('serie'))
        sigilo = limpar(cfg.get('sigilo'), 'R')
        nome_arvore = limpar(cfg.get('nome_arvore'))
        hipotese = limpar(cfg.get('hipotese'))
        nivel = limpar(cfg.get('nivel'), '1')

        db = get_db()
        db.execute('DELETE FROM config_anexo')
        db.execute('''INSERT INTO config_anexo (serie, sigilo, nome_arvore, hipotese, nivel)
                      VALUES (?, ?, ?, ?, ?)''',
                   (serie, sigilo, nome_arvore, hipotese, nivel))

        # Campo em branco na configuracao NAO apaga o que o registro ja tinha:
        # em massa so entra o que foi preenchido aqui.

        rows = db.execute('SELECT * FROM anexos_sei').fetchall()
        for row in rows:
            atual = dict(row)
            tipo_final = serie or str(atual.get('tipo_documento') or '')
            hip_final = hipotese or str(atual.get('hipotese_legal') or '')
            nivel_final = nivel or str(atual.get('nivel_acesso') or '1')
            template = nome_arvore or str(atual.get('nome_arvore') or '')

            # Guarda o TEMPLATE, nao o valor resolvido: o nome final e
            # calculado na hora de exibir/anexar, quando o registro ja tiver
            # os dados do CSV (nome, processo, ...). Assim nada se perde
            # mesmo que o coringa ainda nao tenha dado para substituir.
            db.execute('''UPDATE anexos_sei
                         SET tipo_documento = ?, nome_arvore = ?, nivel_acesso = ?, hipotese_legal = ?
                         WHERE id = ?''',
                      (tipo_final, template, nivel_final, hip_final, row['id']))

        db.commit()
        db.close()
        log.info('Config salva | serie=%s | sigilo=%s | nome_arvore=%s | hipotese=%s | nivel=%s | registros=%d',
                 serie, sigilo, nome_arvore, hipotese, nivel, len(rows))
        return jsonify({'success': True, 'registros_atualizados': len(rows)})
    except Exception as e:
        log.error('ERRO ao salvar config: %s\n%s', e, traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/tipos-documento')
def get_tipos_documento():
    db = get_db()
    rows = db.execute('SELECT codigo, nome FROM tipo_documento ORDER BY nome').fetchall()
    db.close()
    return jsonify([{'codigo': r['codigo'], 'nome': r['nome']} for r in rows])


@app.route('/api/hipoteses-legais')
def get_hipoteses_legais():
    db = get_db()
    rows = db.execute('SELECT codigo, nome FROM hipotese_legal ORDER BY codigo').fetchall()
    db.close()
    return jsonify([{'codigo': r['codigo'], 'nome': r['nome']} for r in rows])


@app.route('/api/anexar', methods=['POST'])
def iniciar_anexacao():
    from sei import sei_state, run_sei, _fila_ocupada
    if _fila_ocupada():
        return jsonify({'error': 'Outra execucao (gerar/baixar/anexar) ja esta em andamento'}), 409
    db = get_db()
    pendentes = db.execute(
        "SELECT COUNT(*) FROM anexos_sei WHERE anexado IN (0, -1) "
        "AND pdf_anexo IS NOT NULL AND TRIM(pdf_anexo) != ''"
    ).fetchone()[0]
    db.close()
    if pendentes == 0:
        return jsonify({'error': 'Nenhum registro com PDF pendente '
                                 '(carregue o CSV e os PDFs primeiro)'}), 400
    if not verificar_chrome_debug():
        return jsonify({'error': 'Chrome debug (porta 9222) indisponivel'}), 500
    log.info('Iniciando anexacao no SEI via API | pendentes=%d', pendentes)
    t = threading.Thread(target=run_sei, daemon=True)
    t.start()
    return jsonify({'success': True, 'message': 'Processo iniciado', 'pendentes': pendentes})


@app.route('/api/anexar/pausar', methods=['POST'])
def anexar_pausar():
    from sei import sei_state
    if not sei_state["rodando"]:
        return jsonify({'error': 'Anexacao nao esta em execucao'}), 409
    sei_state["pausado"] = not sei_state["pausado"]
    log.info('Anexacao %s pelo usuario', 'pausada' if sei_state["pausado"] else 'retomada')
    return jsonify({'success': True, 'pausado': sei_state["pausado"]})


@app.route('/api/anexar/cancelar', methods=['POST'])
def anexar_cancelar():
    from sei import sei_state
    if not sei_state["rodando"]:
        return jsonify({'error': 'Anexacao nao esta em execucao'}), 409
    sei_state["cancelar"] = True
    log.info('Anexacao cancelada pelo usuario')
    return jsonify({'success': True})


@app.route('/api/status')
@app.route('/api/sei-status')
def sei_status():
    from sei import sei_state
    return jsonify({
        'rodando': sei_state["rodando"],
        'total': sei_state["total"],
        'processados': sei_state["processados"],
        'sucesso': sei_state["sucesso"],
        'falha': sei_state["falha"],
        'atual': sei_state["atual"],
        'erros': sei_state["erros"],
        'sucesso_lista': sei_state["sucesso_lista"],
        'falha_lista': sei_state["falha_lista"],
        'pausado': sei_state.get("pausado", False),
        'status_final': sei_state.get("status_final", ""),
        'passo': sei_state.get("passo", 0),
        'passo_desc': sei_state.get("passo_desc", "")
    })


@app.route('/api/sei-log')
def sei_log():
    from sei import sei_state
    return jsonify({'log': sei_state["log"]})


@app.route('/api/retry-falhas', methods=['POST'])
def retry_falhas():
    log.info('Resetando registros com falha para retry')
    db = get_db()
    db.execute("UPDATE anexos_sei SET anexado = 0 WHERE anexado = -1")
    db.commit()
    db.close()
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Geracao de processos (CSV da pasta csv/ -> processo novo no SEI)
# ---------------------------------------------------------------------------

def _norm_col(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', s or '')
    s = s.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', s).strip().upper()


def listar_csvs():
    if not os.path.isdir(CSV_DIR):
        return []
    return sorted(f for f in os.listdir(CSV_DIR) if f.lower().endswith('.csv'))


def _abrir_raw(raw):
    content = None
    for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']:
        try:
            content = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if content is None:
        content = raw.decode('latin-1', errors='replace')
    header = content.splitlines()[0] if content else ''
    delimiter = ';' if (';' in header and ',' not in header) else ','
    return csv.DictReader(io.StringIO(content), delimiter=delimiter)


def _abrir_csv(caminho):
    with open(caminho, 'rb') as f:
        raw = f.read()
    return _abrir_raw(raw)


def _processar_fila(itens):
    """Popula processos_gerados a partir de [(nome_arquivo, raw_bytes), ...]."""
    db = get_db()
    inseridos = atualizados = ignorados = lidos = 0
    erros = []
    for nome_arq, raw in itens:
        try:
            reader = _abrir_raw(raw)
        except Exception as e:
            erros.append(f'{nome_arq}: {e}')
            continue
        for i, row in enumerate(reader, start=2):
            try:
                if not row:
                    continue
                colunas = {_norm_col(k): k for k in row.keys() if k}

                def pegar(*cands):
                    for c in cands:
                        k = colunas.get(c)
                        if k:
                            return (row.get(k) or '').strip()
                    return ''

                cod = pegar('CODIGO BENEFICIARIO', 'CODIGO DO BENEFICIARIO',
                            'COD. BENEFICIARIO', 'CODIGO SIPRA')
                nome = pegar('NOME TITULAR 1', 'BENEFICIARIO', 'NOME')
                proc = pegar('NO PROCESSO SEI', 'N PROCESSO SEI', 'NUP', 'PROCESSO SEI')
                if not cod:
                    ignorados += 1
                    log.warning('CSV %s linha %d: codigo beneficiario vazio', nome_arq, i)
                    continue

                dados_json = json.dumps(
                    {k: (v or '').strip() for k, v in row.items() if k},
                    ensure_ascii=False
                )
                existe = db.execute(
                    'SELECT id, status FROM processos_gerados WHERE cod_beneficiario = ?',
                    (cod,)
                ).fetchone()
                if not existe:
                    db.execute(
                        'INSERT INTO processos_gerados '
                        '(cod_beneficiario, nome, processo_sei_original, dados_csv, status) '
                        'VALUES (?, ?, ?, ?, 0)',
                        (cod, nome, proc, dados_json)
                    )
                    inseridos += 1
                elif existe['status'] != 1:
                    db.execute(
                        'UPDATE processos_gerados SET nome = ?, processo_sei_original = ?, '
                        'dados_csv = ? WHERE id = ?',
                        (nome, proc, dados_json, existe['id'])
                    )
                    atualizados += 1
                else:
                    ignorados += 1
                lidos += 1
            except Exception as e:
                ignorados += 1
                erros.append(f'{nome_arq} linha {i}: {e}')
    db.commit()
    db.close()
    return {'lidos': lidos, 'inseridos': inseridos, 'atualizados': atualizados,
            'ignorados': ignorados, 'erros': erros[:20]}


def carregar_csvs_para_geracao(arquivos=None):
    """Le os CSV da pasta csv/ e popula a fila processos_gerados."""
    if not os.path.isdir(CSV_DIR):
        return {'error': f'Pasta nao encontrada: {CSV_DIR}'}
    arquivos = arquivos or listar_csvs()
    if not arquivos:
        return {'error': 'Nenhum arquivo .csv na pasta csv/'}

    itens = []
    erros = []
    for nome_arq in arquivos:
        caminho = os.path.join(CSV_DIR, os.path.basename(nome_arq))
        if not os.path.isfile(caminho):
            erros.append(f'Arquivo nao encontrado: {nome_arq}')
            continue
        try:
            with open(caminho, 'rb') as f:
                itens.append((nome_arq, f.read()))
        except Exception as e:
            erros.append(f'{nome_arq}: {e}')

    ret = _processar_fila(itens)
    ret['erros'] = (ret.get('erros') or []) + erros
    ret['success'] = True
    ret['arquivos'] = arquivos
    log.info('CSV carregado para geracao: %s', ret)
    return ret


@app.route('/api/tipos-processo')
def get_tipos_processo():
    db = get_db()
    rows = db.execute('SELECT codigo, nome, sigiloso FROM tipo_processo ORDER BY nome').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/gerar/config', methods=['GET'])
def get_gerar_config():
    db = get_db()
    row = db.execute('SELECT * FROM config_geracao LIMIT 1').fetchone()
    db.close()
    if not row:
        return jsonify(dict(DEFAULT_CONFIG_GERACAO))
    return jsonify(dict(row))


@app.route('/api/gerar/config', methods=['POST'])
def save_gerar_config():
    try:
        cfg = request.get_json(force=True)
        db = get_db()
        db.execute('DELETE FROM config_geracao')
        db.execute(
            'INSERT INTO config_geracao (tipo_processo, especificacao, interessados, '
            'observacoes, nivel_acesso, hipotese_legal) VALUES (?, ?, ?, ?, ?, ?)',
            (str(cfg.get('tipo_processo') or ''), str(cfg.get('especificacao') or ''),
             str(cfg.get('interessados') or ''), str(cfg.get('observacoes') or ''),
             str(cfg.get('nivel_acesso') or '1'),
             '4' if cfg.get('hipotese_legal') is None else str(cfg.get('hipotese_legal')))
        )
        db.commit()
        db.close()
        log.info('Config de geracao salva: %s', cfg)
        return jsonify({'success': True})
    except Exception as e:
        log.error('ERRO ao salvar config de geracao: %s\n%s', e, traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/gerar/csvs')
def get_gerar_csvs():
    return jsonify({'dir': CSV_DIR, 'arquivos': listar_csvs()})


@app.route('/api/gerar/carregar-csv', methods=['POST'])
def gerar_carregar_csv():
    try:
        body = request.get_json(silent=True) or {}
        arquivos = [body['arquivo']] if body.get('arquivo') else None
        ret = carregar_csvs_para_geracao(arquivos)
        if ret.get('error'):
            return jsonify(ret), 400
        return jsonify(ret)
    except Exception as e:
        log.error('ERRO ao carregar CSV para geracao: %s\n%s', e, traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/gerar/upload-csv', methods=['POST'])
def gerar_upload_csv():
    """Recebe o CSV enviado pela interface e popula a Fila de Geracao."""
    log.info('--- INICIO gerar/upload-csv ---')
    if 'csv_file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo CSV enviado'}), 400
    file = request.files['csv_file']
    if not file.filename:
        return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
    if not file.filename.lower().endswith('.csv'):
        return jsonify({'error': 'Arquivo deve ser CSV'}), 400
    try:
        raw = file.read()
        log.info('CSV recebido: %s | %d bytes', file.filename, len(raw))
        ret = _processar_fila([(file.filename, raw)])
        ret['success'] = True
        ret['arquivos'] = [file.filename]
        log.info('CSV enviado carregado na fila: %s', ret)
        return jsonify(ret)
    except Exception as e:
        log.error('ERRO ao processar CSV enviado: %s\n%s', e, traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/gerar/iniciar', methods=['POST'])
def gerar_iniciar():
    from sei import gerar_state, run_gerar, _fila_ocupada
    if _fila_ocupada():
        return jsonify({'error': 'Outra execucao (gerar/baixar/anexar) ja esta em andamento'}), 409
    db = get_db()
    pendentes = db.execute(
        'SELECT COUNT(*) FROM processos_gerados WHERE status IN (0, -1)'
    ).fetchone()[0]
    cfg = db.execute('SELECT tipo_processo FROM config_geracao LIMIT 1').fetchone()
    db.close()
    if not cfg or not (cfg['tipo_processo'] or '').strip():
        return jsonify({'error': 'Configure o Tipo do Processo antes de iniciar'}), 400
    if pendentes == 0:
        return jsonify({'error': 'Nenhum registro pendente na fila (carregue o CSV primeiro)'}), 400
    if not verificar_chrome_debug():
        return jsonify({'error': 'Chrome debug (porta 9222) indisponivel'}), 500
    log.info('Geracao de processos iniciada | pendentes=%d', pendentes)
    threading.Thread(target=run_gerar, daemon=True).start()
    return jsonify({'success': True, 'pendentes': pendentes})


@app.route('/api/gerar/status')
def gerar_status():
    from sei import gerar_state, keepalive_state
    db = get_db()
    pendentes = db.execute(
        'SELECT COUNT(*) FROM processos_gerados WHERE status IN (0, -1)'
    ).fetchone()[0]
    gerados = db.execute(
        'SELECT COUNT(*) FROM processos_gerados WHERE status = 1'
    ).fetchone()[0]
    falhas = db.execute(
        'SELECT COUNT(*) FROM processos_gerados WHERE status = -1'
    ).fetchone()[0]
    db.close()
    return jsonify({
        'rodando': gerar_state["rodando"],
        'total': gerar_state["total"],
        'processados': gerar_state["processados"],
        'sucesso': gerar_state["sucesso"],
        'falha': gerar_state["falha"],
        'atual': gerar_state["atual"],
        'erros': gerar_state["erros"],
        'sucesso_lista': gerar_state["sucesso_lista"],
        'falha_lista': gerar_state["falha_lista"],
        'pendentes': pendentes,
        'gerados': gerados,
        'falhas_db': falhas,
        'pausado': gerar_state.get("pausado", False),
        'status_final': gerar_state.get("status_final", ""),
        'passo': gerar_state.get("passo", 0),
        'passo_desc': gerar_state.get("passo_desc", ""),
        'keepalive': keepalive_state
    })


@app.route('/api/gerar/pausar', methods=['POST'])
def gerar_pausar():
    from sei import gerar_state
    if not gerar_state["rodando"]:
        return jsonify({'error': 'Geracao nao esta em execucao'}), 409
    gerar_state["pausado"] = not gerar_state["pausado"]
    log.info('Geracao %s pelo usuario', 'pausada' if gerar_state["pausado"] else 'retomada')
    return jsonify({'success': True, 'pausado': gerar_state["pausado"]})


@app.route('/api/gerar/cancelar', methods=['POST'])
def gerar_cancelar():
    from sei import gerar_state
    if not gerar_state["rodando"]:
        return jsonify({'error': 'Geracao nao esta em execucao'}), 409
    gerar_state["cancelar"] = True
    log.info('Geracao cancelada pelo usuario')
    return jsonify({'success': True})


@app.route('/api/gerar/exportar')
def gerar_exportar():
    """Relatorio CSV (BOM UTF-8, separador ;) com fila, geracao, download e anexo."""
    db = get_db()
    rows = [dict(r) for r in db.execute(
        'SELECT * FROM processos_gerados ORDER BY id').fetchall()]
    anexos = {}
    for r in db.execute('SELECT cod_sipra, pdf_anexo, anexado, data_anexo '
                        'FROM anexos_sei').fetchall():
        anexos[r['cod_sipra']] = dict(r)
    db.close()

    colunas_csv = []
    dados_linhas = []
    for r in rows:
        try:
            dados = json.loads(r.get('dados_csv') or '{}')
        except Exception:
            dados = {}
        if not isinstance(dados, dict):
            dados = {}
        dados_linhas.append(dados)
        for k in dados.keys():
            if k not in colunas_csv:
                colunas_csv.append(k)

    def situacao(valor, ok, erro):
        try:
            valor = int(valor or 0)
        except (TypeError, ValueError):
            valor = 0
        return ok if valor == 1 else (erro if valor == -1 else 'Pendente')

    cabecalho = list(colunas_csv) + [
        'Status geracao', 'Erro geracao', 'Processo SEI gerado', 'Data geracao',
        'Status download', 'Erro download', 'Arquivo download', 'Data download',
        'PDF anexo', 'Status anexo', 'Data anexo'
    ]

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=';', lineterminator='\r\n')
    writer.writerow(cabecalho)
    for r, dados in zip(rows, dados_linhas):
        cod = r.get('cod_beneficiario') or ''
        ax = anexos.get(cod) or {}
        writer.writerow(
            [dados.get(c, '') for c in colunas_csv] + [
                situacao(r.get('status'), 'Gerado', 'Erro'),
                r.get('erro') or '',
                r.get('processo_gerado') or '',
                r.get('data_geracao') or '',
                situacao(r.get('download'), 'Baixado', 'Erro'),
                r.get('erro_download') or '',
                r.get('arquivo_download') or '',
                r.get('data_download') or '',
                ax.get('pdf_anexo') or '',
                situacao(ax.get('anexado'), 'Anexado', 'Erro'),
                ax.get('data_anexo') or '',
            ])

    conteudo = ('\ufeff' + buf.getvalue()).encode('utf-8')
    log.info('Relatorio exportado: %d linha(s)', len(rows))
    return Response(
        conteudo, mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition':
                 'attachment; filename="relatorio_gerador_sei.csv"'})


@app.route('/api/log', methods=['GET'])
def log_unificado():
    """Log unificado das tres execucoes (aba Log)."""
    from sei import sei_state, gerar_state, baixar_state
    linhas = ([f'[ANEXAR] {l}' for l in sei_state.get("log", [])]
              + [f'[GERAR] {l}' for l in gerar_state.get("log", [])]
              + [f'[BAIXAR] {l}' for l in baixar_state.get("log", [])])
    return jsonify({'log': linhas[-500:]})


@app.route('/api/log', methods=['POST'])
def log_limpar():
    """Limpa o log das tres execucoes (botao Limpar log da aba Log)."""
    from sei import sei_state, gerar_state, baixar_state
    sei_state["log"] = []
    gerar_state["log"] = []
    baixar_state["log"] = []
    log.info('Log unificado limpo pelo usuario')
    return jsonify({'success': True})


@app.route('/api/gerar/log')
def gerar_log():
    from sei import gerar_state
    return jsonify({'log': gerar_state["log"]})


@app.route('/api/gerar/registros')
def gerar_registros():
    db = get_db()
    rows = db.execute('SELECT * FROM processos_gerados ORDER BY id').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/gerar/retry', methods=['POST'])
def gerar_retry():
    db = get_db()
    n = db.execute('SELECT COUNT(*) FROM processos_gerados WHERE status = -1').fetchone()[0]
    db.execute('UPDATE processos_gerados SET status = 0, erro = NULL WHERE status = -1')
    db.commit()
    db.close()
    log.info('Retry da geracao: %d registro(s) resetado(s)', n)
    return jsonify({'success': True, 'resetados': n})


@app.route('/api/gerar/limpar', methods=['POST'])
def gerar_limpar():
    from sei import _fila_ocupada
    if _fila_ocupada():
        return jsonify({'error': 'Ha uma execucao em andamento; aguarde terminar'}), 409
    db = get_db()
    n = db.execute('SELECT COUNT(*) FROM processos_gerados').fetchone()[0]
    db.execute('DELETE FROM processos_gerados')
    db.commit()
    db.close()
    log.info('Fila de geracao limpa: %d registro(s) removido(s)', n)
    return jsonify({'success': True, 'removidos': n})


# ---------------------------------------------------------------------------
# Downloads do PGT (aba Baixar)
# ---------------------------------------------------------------------------

@app.route('/api/baixar/status')
def baixar_status():
    from sei import baixar_state
    db = get_db()
    total = db.execute('SELECT COUNT(*) FROM processos_gerados').fetchone()[0]
    baixados = db.execute(
        'SELECT COUNT(*) FROM processos_gerados WHERE download = 1').fetchone()[0]
    falhas = db.execute(
        'SELECT COUNT(*) FROM processos_gerados WHERE download = -1').fetchone()[0]
    db.close()
    return jsonify({
        'rodando': baixar_state["rodando"],
        'total': baixar_state["total"],
        'processados': baixar_state["processados"],
        'sucesso': baixar_state["sucesso"],
        'falha': baixar_state["falha"],
        'atual': baixar_state["atual"],
        'erros': baixar_state["erros"],
        'pausado': baixar_state.get("pausado", False),
        'status_final': baixar_state.get("status_final", ""),
        'passo': baixar_state.get("passo", 0),
        'passo_desc': baixar_state.get("passo_desc", ""),
        'total_db': total,
        'baixados': baixados,
        'falhas_db': falhas,
        'pendentes': max(0, total - baixados - falhas)
    })


@app.route('/api/baixar/log')
def baixar_log():
    from sei import baixar_state
    return jsonify({'log': baixar_state["log"]})


@app.route('/api/baixar/iniciar', methods=['POST'])
def baixar_iniciar():
    from sei import baixar_state, run_baixar, _fila_ocupada
    if _fila_ocupada():
        return jsonify({'error': 'Outra execucao (gerar/baixar/anexar) ja esta em andamento'}), 409
    db = get_db()
    pendentes = db.execute(
        'SELECT COUNT(*) FROM processos_gerados WHERE COALESCE(download, 0) <> 1'
    ).fetchone()[0]
    db.close()
    if pendentes == 0:
        return jsonify({'error': 'Todos os espelhos ja foram baixados '
                                 '(carregue o CSV na aba Gerar primeiro)'}), 400
    if not verificar_chrome_debug():
        return jsonify({'error': 'Chrome debug (porta 9222) indisponivel'}), 500
    log.info('Downloads do PGT iniciados | pendentes=%d', pendentes)
    threading.Thread(target=run_baixar, daemon=True).start()
    return jsonify({'success': True, 'pendentes': pendentes})


@app.route('/api/baixar/pausar', methods=['POST'])
def baixar_pausar():
    from sei import baixar_state
    if not baixar_state["rodando"]:
        return jsonify({'error': 'Download nao esta em execucao'}), 409
    baixar_state["pausado"] = not baixar_state["pausado"]
    log.info('Download %s pelo usuario', 'pausado' if baixar_state["pausado"] else 'retomado')
    return jsonify({'success': True, 'pausado': baixar_state["pausado"]})


@app.route('/api/baixar/cancelar', methods=['POST'])
def baixar_cancelar():
    """Para a execucao e zera o progresso dos downloads (registros mantidos)."""
    from sei import baixar_state
    if baixar_state["rodando"]:
        baixar_state["cancelar"] = True
        log.info('Download cancelado pelo usuario (zerando progresso ao terminar)')
        return jsonify({'success': True, 'aguardando': True})
    db = get_db()
    n = db.execute(
        'UPDATE processos_gerados SET download = 0, erro_download = NULL, '
        'arquivo_download = NULL, data_download = NULL '
        'WHERE download IS NOT NULL AND download <> 0').rowcount
    db.commit()
    db.close()
    from sei import baixar_state as _bs
    _bs["status_final"] = 'cancelado'
    log.info('Fila de downloads cancelada: %d registro(s) zerado(s)', n)
    return jsonify({'success': True, 'zerados': n})


@app.route('/api/baixar/retry', methods=['POST'])
def baixar_retry():
    db = get_db()
    n = db.execute('SELECT COUNT(*) FROM processos_gerados WHERE download = -1').fetchone()[0]
    db.execute('UPDATE processos_gerados SET download = 0, erro_download = NULL '
               'WHERE download = -1')
    db.commit()
    db.close()
    log.info('Retry dos downloads: %d registro(s) resetado(s)', n)
    return jsonify({'success': True, 'resetados': n})


@app.route('/api/keepalive', methods=['GET'])
def keepalive_get():
    iniciar_keepalive_app()
    from sei import keepalive_state
    return jsonify(keepalive_state)


@app.route('/api/keepalive', methods=['POST'])
def keepalive_post():
    from sei import keepalive_state, keepalive_uma_vez
    body = request.get_json(silent=True) or {}
    if 'ativo' in body:
        keepalive_state['ativo'] = bool(body['ativo'])
        _salvar_keepalive_cfg(keepalive_state['ativo'], keepalive_state.get('intervalo'))
        log.info('Keep-alive %s', 'ativado' if keepalive_state['ativo'] else 'desativado')
    if body.get('intervalo'):
        try:
            keepalive_state['intervalo'] = max(15, int(body['intervalo']))
            _salvar_keepalive_cfg(keepalive_state['ativo'], keepalive_state['intervalo'])
        except (TypeError, ValueError):
            pass
    iniciar_keepalive_app()
    resultado = None
    if body.get('agora'):
        resultado = keepalive_uma_vez()
    return jsonify({'success': True, 'keepalive': keepalive_state, 'resultado': resultado})


if __name__ == '__main__':
    if processo_principal():
        # Abre uma aba do painel no navegador assim que o servidor responder
        threading.Thread(target=abrir_aba_do_servidor, daemon=True).start()
    # debug/reloader desligados por padrao: com o reloader o startup (Chrome
    # debug, keep-alive e aba do painel) rodaria duas vezes. Desenvolvimento:
    # GERADOR_SEI_DEBUG=1 python app.py
    debug = os.environ.get('GERADOR_SEI_DEBUG') == '1'
    app.run(debug=debug, use_reloader=debug, host='0.0.0.0', port=SERVIDOR_PORTA)
