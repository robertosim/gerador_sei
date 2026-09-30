#!/usr/bin/env python3
"""check.py - Verificacao e instalacao automatica de dependencias do Gerador SEI.

Rode ANTES de iniciar o aplicativo:

    python check.py

O script verifica:
  1. Versao do Python (>= 3.10)
  2. pip disponivel
  3. Dependencias do requirements.txt (instala automaticamente as que faltarem)
  4. Google Chrome instalado (necessario para a automacao em modo debug)
  5. Navegador do Playwright (opcional - o app usa o Chrome via CDP)
  6. Portas 5000 (app) e 9222 (Chrome debug)
  7. Pastas do projeto (uploads/, csv/) e arquivos essenciais

Opcoes:
  --sem-instalar         So verifica, nao instala nada
  --instalar-navegador   Baixa o Chromium do Playwright, se ausente

Sai com codigo 0 quando tudo esta pronto; 1 quando ha falhas.
"""

import argparse
import os
import re
import socket
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS = os.path.join(BASE_DIR, 'requirements.txt')

PORTA_APP = 5000
PORTA_CHROME_DEBUG = 9222

ARQUIVOS_OBRIGATORIOS = [
    'app.py',
    'sei.py',
    'database.py',
    'tipos_processo.py',
    os.path.join('templates', 'index.html'),
    os.path.join('static', 'css', 'sei-style.css'),
]

PASTAS_OBRIGATORIAS = ['uploads', 'csv']

CHROME_PATHS = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    os.path.expanduser(r'~\AppData\Local\Google\Chrome\Application\chrome.exe'),
]

CORES = {
    'OK': '\033[92m',        # verde
    'INSTALADO': '\033[96m',  # ciano
    'AVISO': '\033[93m',     # amarelo
    'FALHA': '\033[91m',     # vermelho
    'INFO': '\033[90m',      # cinza
    'FIM': '\033[0m',
}

contagem = {'ok': 0, 'instalado': 0, 'aviso': 0, 'falha': 0}
CORES_ATIVAS = sys.stdout.isatty()


def _pintar(tag, msg):
    if CORES_ATIVAS:
        return f"{CORES[tag]}[{tag}]{CORES['FIM']} {msg}"
    return f"[{tag}] {msg}"


def ok(msg):
    contagem['ok'] += 1
    print(_pintar('OK', msg))


def instalado(msg):
    contagem['instalado'] += 1
    print(_pintar('INSTALADO', msg))


def aviso(msg):
    contagem['aviso'] += 1
    print(_pintar('AVISO', msg))


def falha(msg):
    contagem['falha'] += 1
    print(_pintar('FALHA', msg))


def info(msg):
    print(_pintar('INFO', msg))


def titulo(texto):
    print()
    print(texto)
    print('-' * len(texto))


# --------------------------------------------------------------------------
# Python / pip
# --------------------------------------------------------------------------

def checar_python():
    titulo('1. Python')
    versao = sys.version_info
    texto = f'{versao.major}.{versao.minor}.{versao.micro}'
    if versao >= (3, 10):
        ok(f'Python {texto} ({sys.executable})')
        return True
    falha(f'Python {texto} detectado; e necessario Python 3.10 ou superior')
    return False


def checar_pip():
    titulo('2. pip')
    try:
        import pip  # noqa: F401
        from pip import __version__ as versao_pip
        ok(f'pip {versao_pip} disponivel')
        return True
    except Exception as e:
        falha(f'pip nao disponivel ({e}). Instale com: python -m ensurepip --upgrade')
        return False


# --------------------------------------------------------------------------
# requirements.txt
# --------------------------------------------------------------------------

def ler_requirements():
    if not os.path.isfile(REQUIREMENTS):
        return []
    pacotes = []
    with open(REQUIREMENTS, 'r', encoding='utf-8') as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith('#'):
                continue
            pacotes.append(linha)
    return pacotes


def _extrair_nome(spec):
    return re.split(r'[<>=!~\[; ]', spec, maxsplit=1)[0].strip()


def _tuple_versao(versao):
    partes = []
    for pedaco in re.findall(r'\d+', versao or ''):
        partes.append(int(pedaco))
        if len(partes) == 4:
            break
    while len(partes) < 3:
        partes.append(0)
    return tuple(partes)


def versao_satisfaz(installada, spec):
    m = re.match(r'^(>=|<=|==|~=|>|<)\s*(.+)$', spec)
    if not m:
        return True
    op, alvo = m.group(1), m.group(2).strip()
    a, b = _tuple_versao(installada), _tuple_versao(alvo)
    if op == '>=':
        return a >= b
    if op == '<=':
        return a <= b
    if op == '==':
        return a == b or installada.strip() == alvo
    if op == '>':
        return a > b
    if op == '<':
        return a < b
    if op == '~=':
        return a >= b and a[:max(len(b) - 1, 1)] == b[:max(len(b) - 1, 1)]
    return True


def versao_instalada(nome):
    try:
        from importlib import metadata
        return metadata.version(nome)
    except Exception:
        return None


def checar_dependencias(sem_instalar):
    titulo('3. Dependencias Python (requirements.txt)')
    pacotes = ler_requirements()
    if not pacotes:
        falha(f'requirements.txt vazio ou ausente: {REQUIREMENTS}')
        return False

    faltando = []
    for spec in pacotes:
        nome = _extrair_nome(spec)
        instalada = versao_instalada(nome)
        if instalada is None:
            faltando.append(spec)
            aviso(f'{nome}: nao instalado')
        elif not versao_satisfaz(instalada, spec.replace(' ', '')):
            faltando.append(spec)
            aviso(f'{nome} {instalada} nao satisfaz "{spec}"')
        else:
            ok(f'{nome} {instalada}')

    if not faltando:
        return True
    if sem_instalar:
        falha(f'{len(faltando)} dependencia(s) faltando (remova --sem-instalar para instalar)')
        return False

    info('Instalando: ' + ', '.join(faltando))
    cmd = [sys.executable, '-m', 'pip', 'install'] + faltando
    try:
        retorno = subprocess.run(cmd, cwd=BASE_DIR)
    except Exception as e:
        falha(f'Falha ao executar pip: {e}')
        return False
    if retorno.returncode != 0:
        falha('pip retornou erro na instalacao')
        return False

    still = [s for s in faltando if versao_instalada(_extrair_nome(s)) is None]
    if still:
        falha('Ainda faltando apos instalacao: ' + ', '.join(still))
        return False
    for spec in faltando:
        instalado(f'{_extrair_nome(spec)} instalado')
    return True


def checar_navegador_playwright(instalar):
    titulo('4. Navegador do Playwright (opcional)')
    try:
        import playwright  # noqa: F401
    except Exception:
        aviso('playwright nao importavel (deve ter sido instalado no passo 3)')
        return True

    if _navegador_chromium_ok():
        ok('Chromium do Playwright presente')
        return True

    if not instalar:
        aviso('Chromium do Playwright ausente. O app NAO precisa dele (usa o Chrome '
              'via porta 9222). Para instalar: python check.py --instalar-navegador')
        return True

    info('Baixando o Chromium do Playwright...')
    try:
        retorno = subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'],
                                  cwd=BASE_DIR)
    except Exception as e:
        falha(f'Falha ao instalar navegador: {e}')
        return False
    if retorno.returncode != 0 or not _navegador_chromium_ok():
        falha('Nao foi possivel instalar o Chromium do Playwright')
        return False
    instalado('Chromium do Playwright instalado')
    return True


def _pasta_navegadores():
    env = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
    if env == '0':
        try:
            import playwright
            return os.path.join(os.path.dirname(playwright.__file__), 'driver',
                                'package', '.local-browsers')
        except Exception:
            return None
    if env:
        return env
    if os.name == 'nt':
        local = os.environ.get('LOCALAPPDATA')
        return os.path.join(local, 'ms-playwright') if local else None
    return os.path.expanduser('~/.cache/ms-playwright')


def _navegador_chromium_ok():
    pasta = _pasta_navegadores()
    if not pasta or not os.path.isdir(pasta):
        return False
    try:
        entradas = os.listdir(pasta)
    except OSError:
        return False
    return any(e.startswith('chromium') and os.path.isdir(os.path.join(pasta, e))
               for e in entradas)


# --------------------------------------------------------------------------
# Chrome
# --------------------------------------------------------------------------

def checar_chrome():
    titulo('5. Google Chrome')
    caminho = next((p for p in CHROME_PATHS if os.path.exists(p)), None)
    if caminho:
        ok(f'Chrome encontrado: {caminho}')
        return True
    falha('Google Chrome nao encontrado. Instale em https://www.google.com/chrome/')
    info('Sem o Chrome nao ha como abrir o modo debug (porta 9222) nem automatizar o SEI.')
    return False


# --------------------------------------------------------------------------
# Portas e estrutura
# --------------------------------------------------------------------------

def porta_ocupada(porta, timeout=1):
    try:
        with socket.create_connection(('127.0.0.1', porta), timeout=timeout):
            return True
    except OSError:
        return False


def checar_portas():
    titulo('6. Portas')
    if porta_ocupada(PORTA_APP):
        aviso(f'Porta {PORTA_APP} ja em uso (o app pode ja estar rodando): '
              f'abra http://localhost:{PORTA_APP}')
    else:
        ok(f'Porta {PORTA_APP} livre para o app')

    if porta_ocupada(PORTA_CHROME_DEBUG):
        ok(f'Chrome debug ja ativo na porta {PORTA_CHROME_DEBUG}')
    else:
        info(f'Chrome debug ainda nao rodando (porta {PORTA_CHROME_DEBUG}); '
             'o app inicia automaticamente ao abrir.')
    return True


def checar_estrutura():
    titulo('7. Estrutura do projeto')
    tudo_ok = True

    for arquivo in ARQUIVOS_OBRIGATORIOS:
        caminho = os.path.join(BASE_DIR, arquivo)
        if os.path.isfile(caminho):
            ok(f'{arquivo}')
        else:
            falha(f'Arquivo ausente: {arquivo}')
            tudo_ok = False

    for pasta in PASTAS_OBRIGATORIAS:
        caminho = os.path.join(BASE_DIR, pasta)
        if os.path.isdir(caminho):
            ok(f'pasta {pasta}/')
        else:
            try:
                os.makedirs(caminho, exist_ok=True)
                instalado(f'pasta {pasta}/ criada')
            except OSError as e:
                falha(f'Nao foi possivel criar {pasta}/: {e}')
                tudo_ok = False
    return tudo_ok


def main():
    parser = argparse.ArgumentParser(description='Verifica e instala as dependencias do Gerador SEI.')
    parser.add_argument('--sem-instalar', action='store_true',
                        help='Apenas verifica, sem instalar nada')
    parser.add_argument('--instalar-navegador', action='store_true',
                        help='Baixa o Chromium do Playwright, se ausente')
    args = parser.parse_args()

    print('=' * 60)
    print(' Gerador SEI - verificacao de dependencias')
    print('=' * 60)

    resultados = [
        checar_python(),
        checar_pip(),
        checar_dependencias(args.sem_instalar),
        checar_navegador_playwright(args.instalar_navegador and not args.sem_instalar),
        checar_chrome(),
        checar_portas(),
        checar_estrutura(),
    ]

    titulo('Resumo')
    print(f"  ok: {contagem['ok']} | instalados: {contagem['instalado']} | "
          f"avisos: {contagem['aviso']} | falhas: {contagem['falha']}")

    if contagem['falha'] == 0 and all(resultados):
        print()
        print('Pronto! Inicie o aplicativo com:  python app.py')
        return 0

    print()
    print('Corrija as falhas acima e rode novamente:  python check.py')
    return 1


if __name__ == '__main__':
    sys.exit(main())
