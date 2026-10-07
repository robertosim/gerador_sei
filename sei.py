import os
import re
import time
import json
import threading
import traceback
from playwright.sync_api import sync_playwright
from database import (get_db, log_msg, DEFAULT_CONFIG, DEFAULT_CONFIG_GERACAO,
                      processar_nome_arvore_template, fonte_coringas,
                      buscar_coringa, _normalizar_coringa, dir_base)

BASE_DIR = dir_base()
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')
# Espelhos do PGT: "arquivos_pgt" dentro da pasta Downloads do Windows
# (criada na hora em que o download e iniciado).
DOWNLOADS_USER = os.path.join(
    os.environ.get('USERPROFILE') or os.path.expanduser('~'), 'Downloads')
ESPELHOS_DIR = os.path.join(DOWNLOADS_USER, 'arquivos_pgt')
PGT_URL = 'https://pgt.incra.gov.br/sipra/beneficiario'
PGT_TIMEOUT = 60000
PGT_TIMEOUT_DOWNLOAD = 180000

NIVEIS_ACESSO = {
    '0': ('optPublico', 'Publico'),
    '1': ('optRestrito', 'Restrito'),
    '2': ('optSigiloso', 'Sigiloso'),
}

sei_state = {
    "rodando": False,
    "cancelar": False,
    "pausado": False,
    "status_final": "",
    "total": 0,
    "processados": 0,
    "sucesso": 0,
    "falha": 0,
    "atual": "",
    "erros": [],
    "log": [],
    "sucesso_lista": [],
    "falha_lista": [],
    "passo": 0,
    "passo_desc": ""
}


def carregar_config():
    try:
        db = get_db()
        row = db.execute('SELECT serie, nome_arvore, hipotese, nivel FROM config_anexo LIMIT 1').fetchone()
        db.close()
        if row:
            cfg = dict(row)
            log_msg(f"SEI: Config carregada do banco: {cfg}")
            return cfg
    except Exception as e:
        log_msg(f"SEI: Erro ao ler config do banco: {e}")
    log_msg("SEI: Usando config padrao")
    return DEFAULT_CONFIG


def encontrar_frame(page, condicao):
    for frame in page.frames:
        try:
            if condicao(frame):
                return frame
        except:
            continue
    return None


def _log_step(cod_sipra, step, msg):
    _marcar_passo(sei_state, step, msg)
    log_msg(f"SEI [{cod_sipra}] PASSO {step}: {msg}")


def anexar_arquivo_no_sei(page, processo_sei, caminho_pdf, config=None, nome_arvore_db=None):
    if config is None:
        config = carregar_config()

    serie = config.get('serie', '82')
    hipotese = config.get('hipotese', '4')
    nivel = config.get('nivel', '1')
    nivel_id, nivel_nome = NIVEIS_ACESSO.get(nivel, ('optRestrito', 'Restrito'))
    nivel_publico = nivel_id == 'optPublico'

    nome_arvore = nome_arvore_db if nome_arvore_db else config.get('nome_arvore', 'CCIR')

    cod_sipra = os.path.basename(caminho_pdf).split('.')[0] if caminho_pdf else '???'

    log_msg(f"SEI [{cod_sipra}] Config -> Serie={serie}, Arvore={nome_arvore}, Hipotese={hipotese}, Nivel={nivel_nome}")

    # PASSO 1: Acessar SEI
    _log_step(cod_sipra, 1, "Acessando SEI...")
    try:
        page.goto("https://sei.incra.gov.br/sei", wait_until="networkidle", timeout=60000)
        time.sleep(5)
    except Exception as e:
        _log_step(cod_sipra, 1, f"FALHA ao acessar SEI: {e}")
        raise

    expirada = _sessao_expirada_sei(page)
    if expirada:
        _log_step(cod_sipra, 1, expirada)
        raise SessaoExpirada(expirada)

    # PASSO 2: Pesquisar processo
    _log_step(cod_sipra, 2, f"Pesquisando processo: {processo_sei}")
    try:
        page.locator('#txtPesquisaRapida').click()
        page.locator('#txtPesquisaRapida').fill(processo_sei)
        page.locator('#txtPesquisaRapida').press("Enter")
        page.wait_for_load_state("networkidle")
        time.sleep(5)
    except Exception as e:
        _log_step(cod_sipra, 2, f"FALHA ao pesquisar processo {processo_sei}: {e}")
        raise

    # PASSO 3: Encontrar frame com botao de incluir documento (por conteudo, nao por nome)
    _log_step(cod_sipra, 3, "Buscando frame com botao de incluir documento...")
    frame_arvore = None
    frame_arvore = encontrar_frame(page, lambda f: f.locator('img[title="Registrar Documento Externo"]').count() > 0)
    if frame_arvore:
        _log_step(cod_sipra, 3, f"Frame encontrado com 'Registrar Documento Externo' [{frame_arvore.name}]: {frame_arvore.url[:120]}")

    if not frame_arvore:
        frame_arvore = encontrar_frame(page, lambda f: f.locator('img[title="Incluir Documento"]').count() > 0)
        if frame_arvore:
            _log_step(cod_sipra, 3, f"Frame encontrado com 'Incluir Documento' [{frame_arvore.name}]: {frame_arvore.url[:120]}")

    if not frame_arvore:
        frames_info = []
        for i, f in enumerate(page.frames):
            try:
                url = f.url[:80] if f.url else '(sem url)'
                frames_info.append(f"Frame {i} [{f.name}]: {url}")
            except:
                frames_info.append(f"Frame {i}: (erro ao ler)")
        _log_step(cod_sipra, 3, f"FALHA: Nenhum frame com botao de incluir documento. Frames: {'; '.join(frames_info)}")

        # Tentar clicar em 'Externo' no ifrArvore para navegar ate o formulario
        _log_step(cod_sipra, 3, "Tentando clicar em 'Externo' no ifrArvore...")
        frame_ifr = None
        for f in page.frames:
            try:
                if f.name == 'ifrArvore':
                    frame_ifr = f
                    break
            except:
                continue

        if frame_ifr:
            try:
                externo_link = frame_ifr.locator('a.ancoraOpcao[href*="documento_receber"]').first
                if externo_link.count() > 0:
                    _log_step(cod_sipra, 3, "Clicando em 'Externo'...")
                    externo_link.click()
                    page.wait_for_load_state("networkidle")
                    time.sleep(5)
                    _log_step(cod_sipra, 3, f"Frame ifrArvore apos Externo: {frame_ifr.url[:120]}")
                else:
                    externo_link2 = frame_ifr.locator('a.ancoraOpcao:has-text("Externo")').first
                    if externo_link2.count() > 0:
                        _log_step(cod_sipra, 3, "Clicando em 'Externo' (fallback texto)...")
                        externo_link2.click()
                        page.wait_for_load_state("networkidle")
                        time.sleep(5)
                        _log_step(cod_sipra, 3, f"Frame ifrArvore apos Externo: {frame_ifr.url[:120]}")
                    else:
                        _log_step(cod_sipra, 3, "AVISO: Link 'Externo' nao encontrado no ifrArvore.")
            except Exception as e:
                _log_step(cod_sipra, 3, f"AVISO: Erro ao clicar 'Externo': {e}")

            # Apos clicar Externo, procurar botao novamente
            _log_step(cod_sipra, 3, "Buscando botao apos clicar Externo...")
            frame_arvore = encontrar_frame(page, lambda f: f.locator('img[title="Registrar Documento Externo"]').count() > 0)
            if not frame_arvore:
                frame_arvore = encontrar_frame(page, lambda f: f.locator('img[title="Incluir Documento"]').count() > 0)
            if frame_arvore:
                _log_step(cod_sipra, 3, f"Frame encontrado apos Externo [{frame_arvore.name}]: {frame_arvore.url[:120]}")

        if not frame_arvore:
            _log_step(cod_sipra, 3, "FALHA: Botao de incluir documento nao encontrado apos todas as tentativas.")
            return (False, "PASSO 3: Botao de incluir documento nao encontrado em nenhum frame")

    # PASSO 4: Clicar no botao de incluir documento
    titulo_encontrado = None
    for titulo in ['Registrar Documento Externo', 'Incluir Documento']:
        loc = frame_arvore.locator(f'img[title="{titulo}"]')
        if loc.count() > 0:
            titulo_encontrado = titulo
            break

    _log_step(cod_sipra, 4, f"Clicando em '{titulo_encontrado}'...")
    try:
        frame_arvore.locator(f'img[title="{titulo_encontrado}"]').click()
        page.wait_for_load_state("networkidle")
        time.sleep(5)
    except Exception as e:
        _log_step(cod_sipra, 4, f"FALHA ao clicar em '{titulo_encontrado}': {e}")
        raise

    # PASSO 4b: Clicar em 'Externo' no ifrVisualizacao (Escolha o Tipo do Documento)
    _log_step(cod_sipra, 4, "Verificando se precisa clicar em 'Externo' no formulario de tipo...")
    frame_tipo = None
    for f in page.frames:
        try:
            if f.name == 'ifrVisualizacao':
                frame_tipo = f
                break
        except:
            continue

    if frame_tipo:
        _log_step(cod_sipra, 4, f"Frame ifrVisualizacao encontrado: {frame_tipo.url[:120]}")
        try:
            externo_link = frame_tipo.locator('a.ancoraOpcao[href*="documento_receber"]').first
            if externo_link.count() > 0:
                _log_step(cod_sipra, 4, "Clicando em 'Externo' (a.ancoraOpcao[href*=documento_receber])...")
                externo_link.click()
                page.wait_for_load_state("networkidle")
                time.sleep(5)
                _log_step(cod_sipra, 4, f"Frame ifrVisualizacao apos Externo: {frame_tipo.url[:120]}")
            else:
                externo_link2 = frame_tipo.locator('a.ancoraOpcao:has-text("Externo")').first
                if externo_link2.count() > 0:
                    _log_step(cod_sipra, 4, "Clicando em 'Externo' (fallback texto)...")
                    externo_link2.click()
                    page.wait_for_load_state("networkidle")
                    time.sleep(5)
                    _log_step(cod_sipra, 4, f"Frame ifrVisualizacao apos Externo: {frame_tipo.url[:120]}")
                else:
                    _log_step(cod_sipra, 4, "AVISO: Link 'Externo' nao encontrado no ifrVisualizacao.")
        except Exception as e:
            _log_step(cod_sipra, 4, f"AVISO: Erro ao clicar 'Externo': {e}")
    else:
        _log_step(cod_sipra, 4, "AVISO: Frame ifrVisualizacao nao encontrado para clicar 'Externo'.")

    # PASSO 5: Encontrar frame do formulario
    _log_step(cod_sipra, 5, "Buscando frame do formulario (#selSerie)...")
    frame_form = None

    # Primeiro tentar no ifrVisualizacao (que navegou para documento_receber)
    if frame_tipo:
        try:
            if frame_tipo.locator('#selSerie').count() > 0:
                frame_form = frame_tipo
                _log_step(cod_sipra, 5, f"Formulario encontrado no ifrVisualizacao: {frame_tipo.url[:120]}")
        except:
            pass

    # Se nao encontrou, buscar em todos os frames
    if not frame_form:
        frame_form = encontrar_frame(page, lambda f: f.locator('#selSerie').count() > 0)

    if not frame_form:
        try:
            if page.locator('#selSerie').count() > 0:
                frame_form = page
        except:
            pass

    if not frame_form:
        frames_info = []
        for i, f in enumerate(page.frames):
            try:
                url = f.url[:80] if f.url else '(sem url)'
                has_sel = f.locator('#selSerie').count() > 0 if f.url else False
                frames_info.append(f"Frame {i} [{f.name}]: {url} [selSerie={'SIM' if has_sel else 'NAO'}]")
            except:
                frames_info.append(f"Frame {i}: (erro ao ler)")
        _log_step(cod_sipra, 5, f"FALHA: Formulario (selSerie) nao encontrado. Frames: {'; '.join(frames_info)}")
        return (False, f"PASSO 5: Formulario (selSerie) nao encontrado. Frames: {'; '.join(frames_info)}")

    _log_step(cod_sipra, 5, f"Formulario encontrado [{frame_form.name}]: {frame_form.url[:120]}")

    # PASSO 6: Tipo do Documento (serie)
    _log_step(cod_sipra, 6, f"Selecionando Tipo do Documento: serie={serie}...")
    try:
        frame_form.locator('#selSerie').select_option(serie)
        time.sleep(2)
    except Exception as e:
        _log_step(cod_sipra, 6, f"FALHA ao selecionar serie {serie}: {e}")
        raise

    # PASSO 7: Data de Elaboracao
    _log_step(cod_sipra, 7, "Preenchendo Data de Elaboracao...")
    try:
        data_atual = time.strftime("%d/%m/%Y")
        frame_form.locator('#txtDataElaboracao').click()
        frame_form.locator('#txtDataElaboracao').fill(data_atual)
        time.sleep(1)
    except Exception as e:
        _log_step(cod_sipra, 7, f"FALHA ao preencher data: {e}")
        raise

    # PASSO 8: Nome da Arvore
    _log_step(cod_sipra, 8, f"Preenchendo Nome da Arvore: {nome_arvore}...")
    try:
        frame_form.locator('#txtNomeArvore').click()
        frame_form.locator('#txtNomeArvore').fill(nome_arvore)
        time.sleep(1)
    except Exception as e:
        _log_step(cod_sipra, 8, f"FALHA ao preencher nome da arvore: {e}")
        raise

    # PASSO 9: Formato Nato-digital
    _log_step(cod_sipra, 9, "Selecionando Formato: Nato-digital...")
    try:
        frame_form.evaluate("""
            document.getElementById('optNato').checked = true;
            document.getElementById('optNato').click();
            selecionarFormatoDigitalizado();
        """)
        time.sleep(2)
    except Exception as e:
        _log_step(cod_sipra, 9, f"FALHA ao selecionar formato Nato-digital: {e}")
        raise

    # PASSO 10: Nivel de Acesso
    _log_step(cod_sipra, 10, f"Selecionando Nivel de Acesso: {nivel_nome}...")
    try:
        frame_form.evaluate(f"""
            document.getElementById('{nivel_id}').checked = true;
            document.getElementById('{nivel_id}').click();
            alterarNivelAcesso();
        """)
        time.sleep(3)
    except Exception as e:
        _log_step(cod_sipra, 10, f"FALHA ao selecionar nivel de acesso {nivel_nome}: {e}")
        raise

    # PASSO 11: Aguardar Hipotese Legal via AJAX + PASSO 12: definir.
    # O SEI so mostra a Hipotese Legal quando o nivel de acesso NAO e publico:
    # nivel publico pula as duas etapas (o passo nao aparece no log).
    if nivel_publico:
        log_msg(f"SEI [{cod_sipra}] Nivel de acesso publico: Hipotese Legal nao "
                f"exibida pelo SEI (etapas 11 e 12 ignoradas)")
    else:
        _log_step(cod_sipra, 11, f"Aguardando Hipotese Legal via AJAX (valor={hipotese})...")
        try:
            frame_form.wait_for_selector(f'#selHipoteseLegal option[value="{hipotese}"]', state="attached", timeout=15000)
        except Exception as e:
            _log_step(cod_sipra, 11, f"AVISO: Hipotese Legal option[value={hipotese}] nao encontrada via AJAX, aguardando 3s: {e}")
            time.sleep(3)

        # PASSO 12: Hipotese Legal
        _log_step(cod_sipra, 12, f"Definindo Hipotese Legal: valor={hipotese}...")
        try:
            frame_form.evaluate("""
                window.scrollBy(0, 500);
                var sel = document.getElementById('selHipoteseLegal');
                sel.style.display = 'block';
                sel.scrollIntoView({behavior: 'smooth', block: 'center'});
            """)
            time.sleep(1)
            frame_form.evaluate(f"""
                var sel = document.getElementById('selHipoteseLegal');
                sel.value = '{hipotese}';
                sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
            """)
            time.sleep(1)
        except Exception as e:
            _log_step(cod_sipra, 12, f"FALHA ao definir hipotese legal {hipotese}: {e}")
            raise

    # PASSO 13: Anexar PDF
    _log_step(cod_sipra, 13, f"Anexando PDF: {caminho_pdf}")
    try:
        frame_form.locator('#filArquivo').set_input_files(caminho_pdf)
        time.sleep(8)
    except Exception as e:
        _log_step(cod_sipra, 13, f"FALHA ao anexar PDF {caminho_pdf}: {e}")
        raise

    # PASSO 14: Clicar em Salvar
    _log_step(cod_sipra, 14, "Clicando em Salvar...")
    try:
        frame_form.locator('#btnSalvar').first.click()
        page.wait_for_load_state("networkidle")
        time.sleep(5)
    except Exception as e:
        _log_step(cod_sipra, 14, f"FALHA ao clicar em Salvar: {e}")
        raise

    # PASSO 15: Verificar resultado (so mensagens visiveis, como na extensao)
    _log_step(cod_sipra, 15, "Verificando resultado...")
    erros = []
    sucessos = []
    for frame in page.frames:
        for seletor, alvo in (('.infraMensagemErro', erros),
                              ('.infraMensagemSucesso', sucessos)):
            try:
                loc = frame.locator(seletor)
                for i in range(min(loc.count(), 3)):
                    el = loc.nth(i)
                    if not el.is_visible():
                        continue
                    txt = el.inner_text().strip()
                    if txt:
                        alvo.append(txt)
            except Exception:
                continue
    for texto in dict.fromkeys(sucessos):
        _log_step(cod_sipra, 15, f"Mensagem SEI: {texto}")

    if erros:
        msg = ' | '.join(dict.fromkeys(erros))[:400]
        _log_step(cod_sipra, 15, f"FALHA: SEI retornou erro: {msg}")
        return (False, f'PASSO 15: SEI retornou erro: {msg}')

    # PASSO 16: Confirmar (Enter)
    _log_step(cod_sipra, 16, "Pressionando Enter para confirmar...")
    try:
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
    except Exception as e:
        _log_step(cod_sipra, 16, f"AVISO: Falha ao pressionar Enter: {e}")

    _log_step(cod_sipra, 16, "SUCESSO: Documento anexado.")
    return (True, "")


def _registrar_status(msg):
    sei_state["log"].append(msg)
    if len(sei_state["log"]) > 500:
        sei_state["log"] = sei_state["log"][-300:]


gerar_state = {
    "rodando": False,
    "cancelar": False,
    "pausado": False,
    "status_final": "",
    "total": 0,
    "processados": 0,
    "sucesso": 0,
    "falha": 0,
    "atual": "",
    "erros": [],
    "log": [],
    "sucesso_lista": [],
    "falha_lista": [],
    "passo": 0,
    "passo_desc": ""
}

baixar_state = {
    "rodando": False,
    "cancelar": False,
    "pausado": False,
    "status_final": "",
    "total": 0,
    "processados": 0,
    "sucesso": 0,
    "falha": 0,
    "atual": "",
    "erros": [],
    "log": [],
    "sucesso_lista": [],
    "falha_lista": [],
    "passo": 0,
    "passo_desc": ""
}


class InterrupcaoExecucao(BaseException):
    """Levantada quando o usuario cancela no meio de um registro.

    Herda de BaseException para nao ser engolida pelos mil except Exception
    dos passos (que converteriam a interrupcao numa falha do registro).
    """


class SessaoExpirada(Exception):
    """Sessao do SEI expirada (redirecionou para o login): aborta a execucao."""


def _sessao_expirada_sei(page):
    """Detecta login do SEI. Devolve a mensagem de erro ou None."""
    try:
        url = (page.url or '').lower()
    except Exception:
        return None
    if 'login' in url or 'logon' in url:
        return ('Sessao expirada no SEI: faca login no navegador Chrome '
                'e reinicie a execucao')
    return None


def _aguardar_retomada(state):
    """Pausa segura entre passos.

    Segura o robô no passo atual enquanto a execucao estiver pausada (como faz a
    extensao, que congela no tick atual e retoma do mesmo ponto) e aborta o
    registro atual com InterrupcaoExecucao se o usuario cancelar.
    """
    if not state.get("rodando"):
        return
    if state.get("cancelar"):
        raise InterrupcaoExecucao('cancelado')
    while state.get("pausado"):
        if state.get("cancelar"):
            raise InterrupcaoExecucao('cancelado')
        time.sleep(0.5)


def _marcar_passo(state, step, msg):
    state["passo"] = step
    state["passo_desc"] = msg
    _aguardar_retomada(state)


def _interromper(state):
    """True quando o usuario pediu pausa/cancelamento da execucao."""
    return bool(state.get("cancelar") or state.get("pausado"))


def _motivo_interrupcao(state):
    return 'cancelado' if state.get("cancelar") else 'pausado'


def _zerar_flags(state, status_final):
    state["rodando"] = False
    state["cancelar"] = False
    state["pausado"] = False
    state["status_final"] = status_final
    state["passo"] = 0
    state["passo_desc"] = ""

keepalive_state = {
    'ativo': True,
    'intervalo': 60,
    'ultima_recarga': None,
    'recargas': 0,
    'ultimo_erro': None,
    'ultimo_url': None,
    'thread_ativa': False,
}

# Mesmo formato do keepalive_state, mas para a aba do PGT (aba Baixar)
keepalive_pgt_state = {
    'ativo': True,
    'intervalo': 60,
    'ultima_recarga': None,
    'recargas': 0,
    'ultimo_erro': None,
    'ultimo_url': None,
    'thread_ativa': False,
}

KEEPALIVE_ESTADOS = {'sei': keepalive_state, 'pgt': keepalive_pgt_state}
_keepalive_ultimo_tick = {'sei': 0.0, 'pgt': 0.0}

SEI_DIALOGO = {'msg': '', 'hora': 0}


def _aceitar_dialog(d):
    try:
        SEI_DIALOGO['msg'] = str(d.message or '')
        SEI_DIALOGO['hora'] = time.time()
        log_msg(f'GERAR: Dialogo ({d.type}): {d.message}')
    except Exception:
        pass
    try:
        d.accept()
    except Exception:
        try:
            d.dismiss()
        except Exception:
            pass


def _dialogo_recente(janela=45):
    return SEI_DIALOGO['msg'] if time.time() - SEI_DIALOGO['hora'] < janela else ''


def _glog(cod, step, msg):
    txt = f"GERAR [{cod or '-'}] PASSO {step}: {msg}"
    log_msg(txt)
    _marcar_passo(gerar_state, step, msg)
    gerar_state["log"].append(txt)
    if len(gerar_state["log"]) > 500:
        gerar_state["log"] = gerar_state["log"][-300:]


def _blog(cod, step, msg):
    txt = f"BAIXAR [{cod or '-'}] PASSO {step}: {msg}"
    log_msg(txt)
    _marcar_passo(baixar_state, step, msg)
    baixar_state["log"].append(txt)
    if len(baixar_state["log"]) > 500:
        baixar_state["log"] = baixar_state["log"][-300:]


def carregar_config_geracao():
    try:
        db = get_db()
        row = db.execute('SELECT * FROM config_geracao LIMIT 1').fetchone()
        db.close()
        if row:
            cfg = dict(row)
            log_msg(f"GERAR: Config carregada do banco: {cfg}")
            return cfg
    except Exception as e:
        log_msg(f"GERAR: Erro ao ler config_geracao: {e}")
    return dict(DEFAULT_CONFIG_GERACAO)


def renderizar_template(template, registro=None):
    """Substitui {{...}} pelos valores do registro (tabela + colunas do CSV).

    Aceita colunas da tabela (cod_beneficiario, nome, processo_sei, ...),
    colunas do CSV (dados_csv) e apelidos ({{Código SIPRA}},
    {{Nome Titular 1}}, ...).

    Segmentos separados por '-' que ficarem vazios apos a substituicao
    sao descartados. Ex: "{{Nome Titular 1}} - {{Nome Titular 2}}" ->
    "JOAO SILVA" (quando titular 2 esta vazio).
    """
    if template is None:
        return ''
    template = str(template).strip()
    if not template:
        return ''

    mapa = fonte_coringas(registro)

    def coringa(match):
        valor = buscar_coringa(_normalizar_coringa(match.group(1)), mapa)
        return str(valor) if valor is not None and str(valor).strip() else ''

    partes = re.split(r'\s+-\s+', template)
    saida = []
    for parte in partes:
        rend = re.sub(r'\{\{\s*(.*?)\s*\}\}', coringa, parte)
        rend = re.sub(r'\s+', ' ', rend).strip()
        if rend:
            saida.append(rend)
    return ' - '.join(saida)


def _achar_frame_com(page, seletor):
    for f in page.frames:
        try:
            if f.locator(seletor).count() > 0:
                return f
        except Exception:
            continue
    return None


def _dump_frames(page):
    partes = []
    for i, f in enumerate(page.frames):
        try:
            partes.append(f"{i}[{f.name}]: {(f.url or '')[:80]}")
        except Exception:
            partes.append(f"{i}: (erro ao ler)")
    return '; '.join(partes)


def _preencher_campo(frame, seletores, valor, cod, step, nome, js_alvo=None, opcional=False):
    for sel in seletores:
        try:
            if frame.locator(sel).count() > 0:
                loc = frame.locator(sel).first
                loc.click()
                loc.fill(valor or '')
                _glog(cod, step, f"{nome} preenchido via {sel}")
                return True
        except Exception as e:
            _glog(cod, step, f"AVISO: {nome} seletor {sel} falhou: {e}")
    alvos = [js_alvo] if isinstance(js_alvo, str) else list(js_alvo or [])
    for alvo in alvos:
        if not alvo:
            continue
        try:
            ok = frame.evaluate("""([alvo, valor]) => {
                const cands = Array.from(document.querySelectorAll('textarea, input[type="text"]'));
                const el = cands.find(e => ((e.id || '') + ' ' + (e.name || '')).toLowerCase().includes(alvo));
                if (el) {
                    el.focus();
                    el.value = valor;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    return true;
                }
                return false;
            }""", [alvo, valor or ''])
            if ok:
                _glog(cod, step, f"{nome} preenchido via JS (alvo={alvo})")
                return True
        except Exception as e:
            _glog(cod, step, f"AVISO: {nome} fallback JS falhou (alvo={alvo}): {e}")
    if opcional:
        _glog(cod, step, f"AVISO: {nome} nao encontrado (campo opcional, seguindo)")
        return True
    _glog(cod, step, f"ERRO: {nome} nao encontrado | testados: {seletores}")
    return False


def _nivel_atual(frame):
    """Retorna o id do radio de nivel de acesso marcado ('' se nenhum, None se erro)."""
    try:
        return frame.evaluate("""() => {
            const r = document.querySelector('input[name="rdoNivelAcesso"]:checked');
            return r ? (r.id || r.value || '') : '';
        }""") or ''
    except Exception:
        return None


_JS_NIVEL = """(id) => {
    let r = document.getElementById(id);
    if (!r) {
        r = Array.from(document.querySelectorAll('input[name="rdoNivelAcesso"]'))
            .find(x => (x.id || '') === id);
    }
    if (!r) return {ok: false, motivo: 'radio nao encontrado'};
    if (r.disabled) return {ok: false, motivo: 'radio desabilitado pelo SEI'};
    // Nao marcar antes do click: checked=true previo cancela o evento change
    // e o onchange="alterarNivelAcesso()" nunca roda (nao carrega a Hipotese Legal).
    if (r.checked) {
        // ja marcado: click nao gera change, dispara manualmente o onchange
        r.dispatchEvent(new Event('change', {bubbles: true}));
    } else {
        r.click();
    }
    const atual = document.querySelector('input[name="rdoNivelAcesso"]:checked');
    return {ok: !!atual && atual.id === id,
            atual: atual ? (atual.id || atual.value) : '(nenhum)'};
}"""


def _selecionar_nivel_acesso(frame, nivel, cod, tentativas=4):
    nivel_id, nivel_nome = NIVEIS_ACESSO.get(str(nivel), NIVEIS_ACESSO['1'])

    # espera o fieldset #fldNivelAcesso carregar (form via ajax)
    for _ in range(10):
        try:
            if frame.evaluate("""() => !!document.querySelector('input[name="rdoNivelAcesso"]')"""):
                break
        except Exception:
            break
        time.sleep(1.5)

    for t in range(tentativas):
        ret = {'ok': False, 'motivo': 'nao executado'}
        try:
            ret = frame.evaluate(_JS_NIVEL, nivel_id)
        except Exception as e:
            _glog(cod, 6, f"AVISO: nivel via JS falhou (tentativa {t + 1}): {e}")
            ret = {'ok': False, 'motivo': str(e)}
        time.sleep(2)
        atual = _nivel_atual(frame)
        if atual == nivel_id:
            _glog(cod, 6, f"Nivel de acesso {nivel_nome} selecionado e confirmado (#{nivel_id})")
            return True

        # fallback: Playwright check com force (radio costuma ficar oculto)
        try:
            loc = frame.locator(f'#{nivel_id}')
            if loc.count() > 0 and loc.first.is_enabled():
                loc.first.check(timeout=8000, force=True)
        except Exception as e:
            _glog(cod, 6, f"AVISO: nivel check({nivel_id}) falhou: {e}")
        time.sleep(2)
        atual = _nivel_atual(frame)
        if atual == nivel_id:
            _glog(cod, 6, f"Nivel de acesso {nivel_nome} selecionado via check (#{nivel_id})")
            return True
        _glog(cod, 6, f"AVISO: nivel {nivel_id} nao confirmado (atual={atual!r}, js={ret}) "
                      f"- tentativa {t + 1}/{tentativas}")

    _glog(cod, 6, f"AVISO: nivel de acesso {nivel_nome} nao aplicado "
                  f"(atual={_nivel_atual(frame)!r}); mantendo padrao do SEI")
    return False


def _selecionar_hipotese_legal(page, valor, cod):
    """Seleciona a Hipotese Legal (#selHipoteseLegal) apos o nivel de acesso."""
    valor = str(valor or '').strip()
    if not valor or valor.lower() in ('null', 'none', '-'):
        _glog(cod, 6, 'AVISO: Hipotese legal nao configurada (mantendo padrao do SEI)')
        return False
    # O select so ganha opcoes apos alterarNivelAcesso() (ajax). Espera o carregamento.
    frame, carregado = None, False
    for _ in range(12):
        frame = (_achar_frame_com(page, '#selHipoteseLegal')
                 or _achar_frame_com(page, 'select[name="selHipoteseLegal"]'))
        if frame:
            try:
                if frame.locator('#selHipoteseLegal option').count() > 1:
                    carregado = True
                    break
            except Exception:
                pass
        time.sleep(1.5)
    if not frame:
        _glog(cod, 6, 'AVISO: select #selHipoteseLegal nao encontrado (nivel publico?)')
        return False
    if not carregado:
        _glog(cod, 6, 'AVISO: opcoes da Hipotese Legal vazias; chamando alterarNivelAcesso()')
        try:
            frame.evaluate("""() => {
                if (typeof alterarNivelAcesso === 'function') { alterarNivelAcesso(); return true; }
                return false;
            }""")
            for _ in range(6):
                time.sleep(1.5)
                if frame.locator('#selHipoteseLegal option').count() > 1:
                    carregado = True
                    break
        except Exception as e:
            _glog(cod, 6, f'AVISO: alterarNivelAcesso() falhou: {e}')
        if not carregado:
            _glog(cod, 6, 'AVISO: Hipotese Legal seguiu sem opcoes carregadas')
    try:
        frame.locator('#selHipoteseLegal').first.select_option(valor, timeout=8000)
        _glog(cod, 6, f'Hipotese legal {valor} selecionada via select_option')
        time.sleep(1)
        return True
    except Exception as e:
        _glog(cod, 6, f"AVISO: select_option hipotese ({valor}) falhou: {e}")
    try:
        ret = frame.evaluate("""(valor) => {
            const s = document.getElementById('selHipoteseLegal')
                || document.querySelector('select[name="selHipoteseLegal"]');
            if (!s) return false;
            const norm = t => (t || '').toLowerCase().normalize('NFD')
                .replace(/[\\u0300-\\u036f]/g, '');
            let opt = Array.from(s.options).find(o => o.value === valor);
            if (!opt) {
                const alvo = norm(valor);
                opt = Array.from(s.options).find(o => o.value && norm(o.text).includes(alvo));
            }
            if (!opt) return false;
            s.value = opt.value;
            s.dispatchEvent(new Event('change', {bubbles: true}));
            return opt.value + ' | ' + (opt.text || '').trim();
        }""", valor)
        if ret:
            _glog(cod, 6, f'Hipotese legal selecionada via JS: {ret}')
            time.sleep(1)
            return True
    except Exception as e:
        _glog(cod, 6, f"AVISO: hipotese legal via JS falhou: {e}")
    _glog(cod, 6, f'AVISO: Hipotese legal "{valor}" nao encontrada no select')
    return False


def _valor_campo(frame, seletores):
    for sel in seletores:
        try:
            if frame.locator(sel).count() > 0:
                return frame.locator(sel).first.input_value()
        except Exception:
            continue
    return None


def _revalidar_formulario(page, frame_form, campos, hipotese, cod):
    """Relocaliza o formulario e repreenche campos/hipotese apos re-renderizacao.

    Retorna (True, frame) quando tudo esta preenchido, ou (False, frame).
    """
    f2 = None
    for _ in range(8):
        f2 = _achar_frame_com(page, '#txtDescricao') or _achar_frame_com(page, '#btnSalvar')
        if f2:
            break
        time.sleep(1.5)
    if f2:
        frame_form = f2
    for seletores, esperado, nome, js_alvo, obrig in campos:
        if not (esperado or '').strip():
            continue
        atual = _valor_campo(frame_form, seletores)
        if atual is not None and atual.strip() == esperado.strip():
            continue
        _glog(cod, 6, f"AVISO: {nome} estava {(atual or '(vazio)')!r}; repreenchendo...")
        if not _preencher_campo(frame_form, seletores, esperado, cod, 6, nome, js_alvo=js_alvo) and obrig:
            return (False, frame_form)
    if hipotese and hipotese.lower() not in ('null', 'none', '-'):
        atual_hip = _valor_campo(frame_form, ['#selHipoteseLegal'])
        if atual_hip != hipotese:
            _glog(cod, 6, f"AVISO: Hipotese legal era {atual_hip!r}; reselecionando...")
            _selecionar_hipotese_legal(page, hipotese, cod)
    return (True, frame_form)


def _capturar_nup(page, tentativas=25, cod=None):
    """Le o NUP apos o salvamento.

    Prioridade: no selecionado da arvore (.infraArvoreNoSelecionado) -> titulo/url.
    O corpo do frame NAO e usado como fonte principal porque traz NUPs de outros
    processos da arvore (captura errada).
    """
    padrao = re.compile(r'\d{3,8}\.\d{3,8}/\d{4}-\d{2}')

    def _achar(txt):
        if not txt:
            return None
        if not isinstance(txt, str):
            txt = str(txt)
        m = padrao.search(txt)
        if m:
            return m.group(0)
        # numero quebrado por <br>/newline: junta digitos e separadores
        limpo = re.sub(r'(?<=[\d./-])\s+(?=[\d./-])', '', txt)
        m = padrao.search(limpo)
        return m.group(0) if m else None

    def _achar_exclusivo(txt):
        """So aceita se o frame tiver exatamente 1 NUP distinto (evita pegar NUP de outro processo)."""
        if not txt:
            return None
        if not isinstance(txt, str):
            txt = str(txt)
        achados = list(dict.fromkeys(padrao.findall(txt)))
        return achados[0] if len(achados) == 1 else None

    js_no = ("() => Array.from(document.querySelectorAll("
             "'.infraArvoreNoSelecionado, [class*=ArvoreNoSelecionado]'))"
             ".map(e => (e.innerText || e.textContent || '').trim())"
             ".filter(Boolean)")
    js_corpo = ('() => document.body ? (document.body.innerText || "") : ""')

    paginas = []
    log_frames = False
    for i in range(tentativas):
        try:
            paginas = list(page.context.pages)
        except Exception:
            paginas = []
        if page not in paginas:
            paginas.insert(0, page)

        if cod is not None and not log_frames:
            dump = []
            for pg in paginas:
                for f in pg.frames:
                    try:
                        dump.append(f"[{f.name}] {(f.url or '')[:70]}")
                    except Exception:
                        dump.append('(frame ilegivel)')
            if any('ifrArvore' in d for d in dump):
                _glog(cod, 8, f"PASSO 8: frames apos Salvar: {'; '.join(dump)[:500]}")
                log_frames = True

        for pg in paginas:
            # 1) titulo/url da aba
            try:
                for origem, valor in (('titulo', pg.title()), ('url', pg.url)):
                    v = _achar(valor or '')
                    if v:
                        if cod is not None:
                            _glog(cod, 8, f'NUP {v} lido do {origem}')
                        return v
            except Exception:
                pass

            # 2) no selecionado da arvore (destino do redirect apos Salvar)
            frames = list(pg.frames)
            frames.sort(key=lambda f: 0 if f.name in ('ifrArvore', 'ifrVisualizacao') else 1)
            for f in frames:
                try:
                    loc = f.locator('.infraArvoreNoSelecionado')
                    n = loc.count()
                    for k in range(min(n, 5)):
                        el = loc.nth(k)
                        try:
                            t = el.inner_text(timeout=1500)
                        except Exception:
                            t = el.text_content() or ''
                        v = _achar(t)
                        if v:
                            if cod is not None:
                                _glog(cod, 8, f'NUP {v} lido do no da arvore '
                                              f'(frame [{f.name}]): {t.strip()[:80]!r}')
                            return v
                except Exception:
                    pass
                try:
                    for t in (f.evaluate(js_no) or []):
                        v = _achar(t)
                        if v:
                            if cod is not None:
                                _glog(cod, 8, f'NUP {v} lido do no da arvore via JS '
                                              f'(frame [{f.name}]): {t.strip()[:80]!r}')
                            return v
                except Exception:
                    pass

            # 3) fallback: texto do frame (so se o no da arvore nao existir e
            #    o frame tiver um unico NUP distinto)
            if i >= 2:
                for f in frames:
                    try:
                        v = _achar_exclusivo(f.evaluate(js_corpo))
                        if v:
                            if cod is not None:
                                _glog(cod, 8, f'NUP {v} lido do texto do frame [{f.name}]')
                            return v
                    except Exception:
                        continue
        time.sleep(2)

    if cod is not None:
        diag = []
        for pg in paginas:
            for f in pg.frames:
                try:
                    n = f.locator('.infraArvoreNoSelecionado').count()
                    corpo = f.evaluate(js_corpo) or ''
                    qtd = len(set(padrao.findall(corpo)))
                    diag.append(f"[{f.name}] nos_selecionados={n} nups_distintos={qtd}")
                except Exception as e:
                    diag.append(f"[{getattr(f, 'name', '?')}] erro={e}")
        _glog(cod, 8, f"PASSO 8: NUP nao encontrado em {tentativas * 2}s. "
                      f"Diagnostico: {'; '.join(diag)[:500]}")
    return None


def _resumo_pos_salvar(page):
    """Retorna url, titulo e trecho do corpo apos clicar em Salvar (para diagnostico)."""
    partes = []
    dlg = _dialogo_recente(janela=120)
    if dlg:
        partes.append(f"alerta={dlg[:200]!r}")
    try:
        partes.append(f"url={page.url[:150]}")
    except Exception as e:
        partes.append(f"url=(erro {e})")
    try:
        partes.append(f"titulo={page.title()!r}")
    except Exception:
        pass
    for i, pg in enumerate(page.context.pages):
        if pg is page:
            continue
        try:
            partes.append(f"aba{i}={pg.url[:150]}")
        except Exception:
            pass
    for f in page.frames:
        try:
            txt = (f.evaluate('() => document.body ? (document.body.innerText || "") : ""') or '').strip()
            if txt:
                partes.append(f"frame[{f.name}]={txt[:200]!r}")
        except Exception:
            continue
    return ' | '.join(partes)


def _exibir_todos_tipos(page, cod):
    """Clica no link 'Exibir todos os tipos' (ancExibirTiposProcedimento)."""
    frame = (_achar_frame_com(page, '#ancExibirTiposProcedimento')
             or _achar_frame_com(page, 'a[onclick*="exibirTiposProcedimento"]'))
    if frame:
        for sel in ['#ancExibirTiposProcedimento', 'a[onclick*="exibirTiposProcedimento"]']:
            try:
                if frame.locator(sel).count() > 0:
                    frame.locator(sel).first.click()
                    _glog(cod, 3, f'Todos os tipos exibidos via {sel}')
                    return True
            except Exception as e:
                _glog(cod, 3, f"AVISO: exibir todos os tipos ({sel}) falhou: {e}")
    for f in page.frames:
        try:
            ok = f.evaluate("""() => {
                const a = document.getElementById('ancExibirTiposProcedimento')
                    || document.querySelector('a[onclick*="exibirTiposProcedimento"]');
                if (a) { a.click(); return true; }
                if (typeof exibirTiposProcedimento === 'function') { exibirTiposProcedimento('T'); return true; }
                return false;
            }""")
            if ok:
                _glog(cod, 3, f'Todos os tipos exibidos via JS no frame [{f.name}]')
                return True
        except Exception:
            continue
    _glog(cod, 3, 'AVISO: link "Exibir todos os tipos" nao encontrado')
    return False


def _clicar_tipo_js(frame, codigo, tipo):
    """Fallback: localiza e clica no tipo por href (codigo) ou texto."""
    try:
        return bool(frame.evaluate("""([codigo, tipo]) => {
            const links = Array.from(document.querySelectorAll('a[href]'));
            let alvo = null;
            if (codigo) {
                alvo = links.find(a => (a.getAttribute('href') || '').includes('id_tipo_procedimento=' + codigo));
            }
            if (!alvo && tipo) {
                alvo = links.find(a => (a.textContent || '').trim().includes(tipo));
            }
            if (alvo) { alvo.click(); return true; }
            return false;
        }""", [codigo, tipo]))
    except Exception:
        return False


def gerar_processo_no_sei(page, cfg, cod=''):
    """Cria um processo no SEI: Iniciar Processo -> tipo -> form -> Salvar.

    Retorna (True, nup) ou (False, detalhe_erro).
    """
    tipo = str(cfg.get('tipo_processo') or '').strip()
    if not tipo:
        return (False, 'PASSO 0: Tipo do processo nao configurado (config_geracao.tipo_processo)')
    espec = str(cfg.get('especificacao') or '')
    inter = str(cfg.get('interessados') or '')
    obs = str(cfg.get('observacoes') or '')
    nivel = str(cfg.get('nivel_acesso') or '1')
    hipotese = str(cfg.get('hipotese_legal') or '')

    # PASSO 1: Acessar SEI
    _glog(cod, 1, "Acessando SEI...")
    try:
        page.goto("https://sei.incra.gov.br/sei", wait_until="networkidle", timeout=60000)
        time.sleep(5)
    except Exception as e:
        return (False, f"PASSO 1: Falha ao acessar SEI: {e}")

    expirada = _sessao_expirada_sei(page)
    if expirada:
        _glog(cod, 1, expirada)
        raise SessaoExpirada(expirada)

    # PASSO 2: Clicar em "Iniciar Processo"
    _glog(cod, 2, 'Clicando em "Iniciar Processo" (menu lateral)...')
    clicou = False
    for f in page.frames:
        try:
            loc = f.locator('a[link="procedimento_escolher_tipo"]')
            if loc.count() == 0:
                loc = f.locator('a[href*="procedimento_escolher_tipo"]')
            if loc.count() > 0:
                loc.first.click()
                clicou = True
                _glog(cod, 2, f'Link clicado no frame [{f.name}]')
                break
        except Exception as e:
            _glog(cod, 2, f"AVISO: erro ao clicar no frame [{getattr(f, 'name', '?')}]: {e}")
    if not clicou:
        return (False, f'PASSO 2: Link "Iniciar Processo" nao encontrado. Frames: {_dump_frames(page)}')
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    time.sleep(4)

    # PASSO 3: Escolher tipo de processo
    codigo = tipo if tipo.isdigit() else ''
    _glog(cod, 3, f"Escolhendo tipo de processo: {tipo}...")
    frame_tipos = None
    for _ in range(10):
        frame_tipos = _achar_frame_com(page, '#tblTipoProcedimento')
        if frame_tipos:
            break
        time.sleep(2)
    if not frame_tipos:
        return (False, f'PASSO 3: Tabela #tblTipoProcedimento nao encontrada. Frames: {_dump_frames(page)}')

    loc = None
    for tentativa in range(2):
        loc = None
        try:
            if codigo:
                loc = frame_tipos.locator(f'a[href*="id_tipo_procedimento={codigo}"]')
                if loc.count() == 0:
                    loc = frame_tipos.locator(f'[href*="id_tipo_procedimento={codigo}"]')
            if loc is None or loc.count() == 0:
                loc = frame_tipos.locator(f'a:has-text("{tipo}")')
            if loc.count() > 0:
                break
        except Exception as e:
            _glog(cod, 3, f"AVISO: busca do tipo falhou (frame removido?): {e}")
            loc = None
        if tentativa == 0:
            _glog(cod, 3, f'Tipo "{tipo}" nao visivel; clicando em "Exibir todos os tipos"...')
            if not _exibir_todos_tipos(page, cod):
                break
            time.sleep(4)
            for _ in range(5):
                f2 = _achar_frame_com(page, '#tblTipoProcedimento')
                if f2:
                    frame_tipos = f2
                    break
                time.sleep(2)
    clicou_tipo = False
    try:
        achou = loc is not None and loc.count() > 0
    except Exception:
        achou = False
    if achou:
        try:
            loc.first.click()
            clicou_tipo = True
        except Exception as e:
            return (False, f'PASSO 3: Falha ao clicar no tipo "{tipo}": {e}')
    else:
        _glog(cod, 3, f'AVISO: tipo "{tipo}" nao achado por seletor, tentando via JS...')
        clicou_tipo = _clicar_tipo_js(frame_tipos, codigo, tipo)
    if not clicou_tipo:
        return (False, f'PASSO 3: Tipo "{tipo}" nao encontrado na tabela de tipos')
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    time.sleep(4)

    # PASSO 4: Localizar formulario
    _glog(cod, 4, "Buscando formulario de geracao (#txtDescricao/#txtEspecificacao)...")
    frame_form = None
    sel_form = None
    for _ in range(15):
        for sel in ['#txtDescricao', '#txtEspecificacao', 'textarea[id*="Especificacao"]',
                    '#txtInteressados', '#btnSalvar']:
            frame_form = _achar_frame_com(page, sel)
            if frame_form:
                sel_form = sel
                break
        if frame_form:
            break
        time.sleep(2)
    if not frame_form:
        for f in page.frames:
            try:
                if f.locator('#btnSalvar').count() > 0 and f.locator('input[type="text"], textarea').count() > 0:
                    frame_form = f
                    sel_form = 'btnSalvar+campos'
                    break
            except Exception:
                continue
    if not frame_form:
        return (False, f'PASSO 4: Formulario de geracao nao encontrado. Frames: {_dump_frames(page)}')
    _glog(cod, 4, f"Formulario encontrado [{frame_form.name}] via {sel_form}: {frame_form.url[:120]}")

    # PASSO 5: Preencher campos
    if not _preencher_campo(frame_form, ['#txtDescricao', 'input[id="txtDescricao"]',
                                         '#txtEspecificacao', 'textarea[id*="Especificacao"]',
                                         'input[id*="Especificacao"]'],
                            espec, cod, 5, 'Especificacao',
                            js_alvo=['especificacao', 'descricao']):
        return (False, 'PASSO 5: Campo Especificacao nao encontrado no formulario')
    _preencher_campo(frame_form, ['#txtInteressados', 'textarea[id*="Interessado"]',
                                  'input[id*="Interessado"]'],
                     inter, cod, 5, 'Interessados', js_alvo=['interessado'])
    _preencher_campo(frame_form, ['#txaObservacoes', '#txtObservacoes',
                                  'textarea[id*="bservac"]', 'textarea[id*="Observac"]',
                                  'input[id*="bservac"]', 'input[id*="Observac"]'],
                     obs, cod, 5, 'Observacoes',
                     js_alvo=['observacoes', 'bservac', 'observacao'], opcional=True)

    # PASSO 6: Nivel de acesso (fieldset #fldNivelAcesso)
    esperado_nivel = NIVEIS_ACESSO.get(nivel, NIVEIS_ACESSO['1'])[0]
    _selecionar_nivel_acesso(frame_form, nivel, cod)

    # PASSO 6b: Hipotese legal (aparece apos a troca de nivel de acesso).
    # So roda quando o nivel de acesso NAO e publico: o SEI nao exibe o
    # select de Hipotese Legal para nivel publico.
    nivel_publico = esperado_nivel == 'optPublico'
    hipotese_reval = '' if nivel_publico else hipotese
    if not nivel_publico:
        _selecionar_hipotese_legal(page, hipotese, cod)

    campos = [
        (['#txtDescricao', 'input[id="txtDescricao"]', '#txtEspecificacao',
          'textarea[id*="Especificacao"]', 'input[id*="Especificacao"]'],
         espec, 'Especificacao', ['especificacao', 'descricao'], True),
        (['#txtInteressados', 'textarea[id*="Interessado"]', 'input[id*="Interessado"]'],
         inter, 'Interessados', ['interessado'], False),
        (['#txaObservacoes', '#txtObservacoes', 'textarea[id*="bservac"]',
          'textarea[id*="Observac"]', 'input[id*="bservac"]', 'input[id*="Observac"]'],
         obs, 'Observacoes', ['observacoes', 'bservac', 'observacao'], False),
    ]

    # PASSO 6c: Revalidar campos (troca de nivel pode recarregar o formulario)
    ok6c, frame_form = _revalidar_formulario(page, frame_form, campos, hipotese_reval, cod)
    if not ok6c:
        return (False, 'PASSO 6c: Campo Especificacao nao encontrado apos nivel/hipotese legal')

    # PASSO 6d: Confere se o radio do nivel ficou marcado antes de salvar
    atual_nivel = _nivel_atual(frame_form)
    if atual_nivel != esperado_nivel:
        _glog(cod, 6, f"AVISO: Nivel de acesso era {atual_nivel or '(nenhum)'}; "
                      f"reselecionando {esperado_nivel}...")
        _selecionar_nivel_acesso(frame_form, nivel, cod)
        ok6d, frame_form = _revalidar_formulario(page, frame_form, campos, hipotese_reval, cod)
        if not ok6d:
            return (False, 'PASSO 6d: Campo perdido apos reselecao do nivel de acesso')
        atual_nivel = _nivel_atual(frame_form)
        if atual_nivel != esperado_nivel:
            nome_nivel = NIVEIS_ACESSO.get(nivel, ('', '?'))[1]
            return (False, f'PASSO 6d: Nivel de acesso NAO aplicado no radio '
                           f'(SEI: {atual_nivel or "(nenhum)"} | configurado: {esperado_nivel} {nome_nivel})')
    _glog(cod, 6, f'Nivel de acesso confirmado antes de salvar: {atual_nivel}')

    # PASSO 7: Salvar
    _glog(cod, 7, "Clicando em Salvar...")
    try:
        if frame_form.locator('#btnSalvar, #btnInfraSalvar, input[value="Salvar"]').count() == 0:
            raise ValueError('sem botao Salvar no frame atual')
    except Exception:
        f3 = _achar_frame_com(page, '#btnSalvar') or _achar_frame_com(page, '#btnInfraSalvar')
        if f3:
            frame_form = f3
            _glog(cod, 7, f"Frame do formulario relocalizado [{f3.name}]: {f3.url[:120]}")
    btn_sel = None
    for sel in ['#btnSalvar', '#btnInfraSalvar', 'input[value="Salvar"]', 'button:has-text("Salvar")']:
        try:
            if frame_form.locator(sel).count() > 0:
                btn_sel = sel
                break
        except Exception:
            continue
    if not btn_sel:
        return (False, f'PASSO 7: Botao Salvar nao encontrado. Frames: {_dump_frames(page)}')
    try:
        frame_form.locator(btn_sel).first.click()
    except Exception as e:
        return (False, f'PASSO 7: Falha ao clicar em Salvar: {e}')
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    time.sleep(5)
    try:
        _glog(cod, 7, f"Apos Salvar: {page.url[:150]} | abas={len(page.context.pages)}")
    except Exception:
        pass
    dlg = _dialogo_recente()
    if dlg:
        _glog(cod, 7, f"AVISO: alerta do SEI apos Salvar: {dlg[:250]}")

    # PASSO 7b: Verificar mensagens de erro do SEI
    erros = []
    avisos = []
    paginas = list(page.context.pages)
    if page not in paginas:
        paginas.append(page)
    for pg in paginas:
        for f in pg.frames:
            for sel, alvo in [('.infraMensagemErro', erros), ('.infraAviso', avisos),
                              ('.infraMensagem', avisos), ('#divInfraAviso', avisos)]:
                try:
                    loc = f.locator(sel)
                    for i in range(min(loc.count(), 3)):
                        el = loc.nth(i)
                        if not el.is_visible():
                            continue
                        txt = el.inner_text().strip()
                        if txt:
                            alvo.append(txt)
                except Exception:
                    continue
    avisos = list(dict.fromkeys(avisos))
    if avisos:
        _glog(cod, 7, f"AVISO SEI: {' | '.join(avisos)[:300]}")
    erros = list(dict.fromkeys(erros))
    if erros:
        return (False, f'PASSO 7: SEI retornou erro: {" | ".join(erros)[:400]}')

    # PASSO 8: Capturar NUP gerado
    _glog(cod, 8, "Capturando NUP do processo gerado...")
    nup = _capturar_nup(page, cod=cod)
    if not nup:
        return (False, f'PASSO 8: Processo salvo mas NUP nao encontrado. '
                       f'| {_resumo_pos_salvar(page)} | Frames: {_dump_frames(page)}')
    _glog(cod, 8, f"SUCESSO: NUP {nup}")
    return (True, nup)


def run_gerar():
    if gerar_state["rodando"]:
        log_msg("GERAR: Ja esta em execucao.")
        return

    gerar_state["rodando"] = True
    gerar_state["cancelar"] = False
    gerar_state["pausado"] = False
    gerar_state["status_final"] = ""
    gerar_state["total"] = 0
    gerar_state["processados"] = 0
    gerar_state["sucesso"] = 0
    gerar_state["falha"] = 0
    gerar_state["atual"] = ""
    gerar_state["erros"] = []
    gerar_state["log"] = []
    gerar_state["sucesso_lista"] = []
    gerar_state["falha_lista"] = []
    gerar_state["passo"] = 0
    gerar_state["passo_desc"] = ""

    status_final = 'concluido'
    _glog('-', 0, 'Inicio da geracao de processos')

    try:
        cfg = carregar_config_geracao()

        db = get_db()
        rows = db.execute(
            "SELECT * FROM processos_sei WHERE status IN (0, -1) ORDER BY id"
        ).fetchall()
        db.close()

        if not rows:
            _glog('-', 0, 'Nenhum registro pendente para gerar')
            return

        gerar_state["total"] = len(rows)
        _glog('-', 0, f'{len(rows)} registro(s) na fila (pendentes ou com erro)')

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            page = context.new_page()
            page.on('dialog', _aceitar_dialog)
            context.on('page', lambda pg: pg.on('dialog', _aceitar_dialog))

            for row in rows:
                if _interromper(gerar_state):
                    status_final = _motivo_interrupcao(gerar_state)
                    _glog('-', 0, f'Interrompido pelo usuario ({status_final}) '
                                  f'| Processados: {gerar_state["processados"]}')
                    break

                reg = dict(row)
                cod = reg.get('cod_beneficiario') or ''
                nome = reg.get('nome') or ''
                gerar_state["atual"] = f"{cod} - {nome}"
                _glog(cod, 0, f'Processando: {cod} - {nome}')

                cfg_linha = dict(cfg)
                cfg_linha['especificacao'] = renderizar_template(cfg.get('especificacao'), reg)
                cfg_linha['interessados'] = renderizar_template(cfg.get('interessados'), reg)
                cfg_linha['observacoes'] = renderizar_template(cfg.get('observacoes'), reg)
                _glog(cod, 0, f"Espec: {cfg_linha['especificacao']!r} | "
                              f"Interessados: {cfg_linha['interessados']!r} | "
                              f"Nivel: {cfg_linha.get('nivel_acesso') or '1'} | "
                              f"Hipotese: {cfg_linha.get('hipotese_legal') or '(nenhuma)'}")

                sessao_expirada = False
                try:
                    ok, detalhe = gerar_processo_no_sei(page, cfg_linha, cod)
                except InterrupcaoExecucao:
                    status_final = _motivo_interrupcao(gerar_state)
                    _glog('-', 0, f'Interrompido no meio do registro {cod} ({status_final}) '
                                  f'| Processados: {gerar_state["processados"]}')
                    break
                except SessaoExpirada as e:
                    ok, detalhe = False, str(e)
                    sessao_expirada = True
                except Exception as e:
                    ok, detalhe = False, f"Excecao: {e}"
                    log_msg(traceback.format_exc())

                db = get_db()
                if ok:
                    db.execute(
                        "UPDATE processos_sei SET processo_sei = ?, status = 1, "
                        "erro = NULL, data_geracao = ? WHERE id = ?",
                        (detalhe, time.strftime('%Y-%m-%d %H:%M:%S'), reg['id'])
                    )
                    gerar_state["sucesso"] += 1
                    gerar_state["sucesso_lista"].append({'cod': cod, 'nup': detalhe})
                    _glog(cod, 99, f'SUCESSO: {detalhe}')
                else:
                    db.execute(
                        "UPDATE processos_sei SET status = -1, erro = ? WHERE id = ?",
                        (detalhe, reg['id'])
                    )
                    gerar_state["falha"] += 1
                    gerar_state["erros"].append({"cod": cod, "nome": nome, "erro": detalhe})
                    gerar_state["falha_lista"].append({"cod": cod, "erro": detalhe})
                    _glog(cod, 99, f'FALHA: {detalhe}')
                db.commit()
                db.close()

                if sessao_expirada:
                    status_final = 'sessao_expirada'
                    _glog('-', 0, f'ABORTADO: {detalhe}')
                    gerar_state["processados"] += 1
                    break

                gerar_state["processados"] += 1

            page.close()
            browser.close()

    except InterrupcaoExecucao:
        status_final = _motivo_interrupcao(gerar_state)
        _glog('-', 0, f'Interrompido pelo usuario ({status_final}) '
                      f'| Processados: {gerar_state["processados"]}')
    except Exception as e:
        _glog('-', 0, f'ERRO GERAL: {e}')
        log_msg(traceback.format_exc())
        status_final = 'erro'
    finally:
        _zerar_flags(gerar_state, status_final)
        gerar_state["atual"] = ""
        _glog('-', 0, f"Finalizado ({status_final}) | Sucesso: {gerar_state['sucesso']} "
                      f"| Falha: {gerar_state['falha']}")


def _fila_ocupada():
    return bool(sei_state.get("rodando") or gerar_state.get("rodando")
                or baixar_state.get("rodando"))


_SQL_PENDENCIAS_ANEXAR = """
    SELECT a.id, a.cod_sipra, a.pdf_anexo, a.nome_arvore, a.anexado, a.data_anexo,
           pg.nome, pg.processo_sei, pg.dados_csv
      FROM anexos_sei a
      LEFT JOIN processos_sei pg ON pg.cod_beneficiario = a.cod_sipra
     WHERE a.anexado IN (0, -1)
       AND a.pdf_anexo IS NOT NULL AND TRIM(a.pdf_anexo) != ''
       AND TRIM(COALESCE(pg.processo_sei, '')) != ''
"""


def pendencias_anexar():
    db = get_db()
    rows = db.execute(_SQL_PENDENCIAS_ANEXAR).fetchall()
    db.close()
    return rows


def diagnostico_pendencias():
    db = get_db()
    total = db.execute(
        "SELECT COUNT(*) FROM anexos_sei WHERE anexado IN (0, -1)"
    ).fetchone()[0]
    com_pdf = db.execute(
        "SELECT COUNT(*) FROM anexos_sei WHERE anexado IN (0, -1) "
        "AND pdf_anexo IS NOT NULL AND TRIM(pdf_anexo) != ''"
    ).fetchone()[0]
    db.close()

    prontos = len(pendencias_anexar())
    partes = []
    if com_pdf - prontos > 0:
        partes.append(f'{com_pdf - prontos} sem numero de processo '
                      f'(gere o NUP na aba Gerar)')
    if total - com_pdf > 0:
        partes.append(f'{total - com_pdf} sem PDF (carregue os PDFs na aba Anexar)')
    if not partes:
        return 'Nenhum registro pendente para anexar'
    return 'Nenhum registro pronto para anexar: ' + ' | '.join(partes)


def _glog_ka(msg):
    log_msg(f'KEEPALIVE: {msg}')


def _achar_aba_sei(browser):
    """Procura entre TODAS as abas de TODOS os contexts a que tem a URL do SEI.

    Retorna (pagina, indice) ou (None, None). Nunca cria aba.
    """
    for ctx in browser.contexts:
        for idx, pg in enumerate(ctx.pages):
            try:
                if pg.is_closed():
                    continue
                if 'sei.incra.gov.br' in (pg.url or ''):
                    return pg, idx
            except Exception:
                continue
    return None, None


def _achar_aba_pgt(browser):
    """Procura a aba do PGT ja aberta (com login ja feito) em todos os contexts.

    Retorna (pagina, indice) ou (None, None). Nunca cria aba.
    """
    for ctx in browser.contexts:
        for idx, pg in enumerate(ctx.pages):
            try:
                if pg.is_closed():
                    continue
                if 'pgt.incra.gov.br' in (pg.url or ''):
                    return pg, idx
            except Exception:
                continue
    return None, None


def keepalive_uma_vez():
    """Recarrega a ABA do SEI ja aberta no Chrome debug (mantem sessao ativa).

    - Identifica a(s) aba(s) abertas e recarrega somente a que tem a URL do SEI.
    - Nunca abre aba nova se ja existir uma do SEI (reutiliza a mesma).
    - Se nenhuma aba do SEI existir, abre uma unica vez (sera reutilizada).
    - So recarrega quando o app esta ocioso (nenhuma fila em processamento).
    """
    if not keepalive_state['ativo']:
        return {'ok': False, 'motivo': 'desativado'}
    if _fila_ocupada():
        keepalive_state['ultimo_erro'] = 'Pausado: fila em processamento'
        log_msg('KEEPALIVE: pausado (fila em processamento)')
        return {'ok': False, 'motivo': 'ocupado'}
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            abas = []
            for ctx in browser.contexts:
                for pg in ctx.pages:
                    try:
                        abas.append(pg.url or '(sem url)')
                    except Exception:
                        abas.append('(erro ao ler)')
            _glog_ka(f'{len(abas)} aba(s) aberta(s): {"; ".join(u[:60] for u in abas)}')

            page, idx = _achar_aba_sei(browser)
            aberta = page is not None
            if aberta:
                # Reutiliza a aba ja aberta: apenas recarrega
                _glog_ka(f'Reutilizando aba #{idx} com a URL do SEI')
                try:
                    page.bring_to_front()
                except Exception:
                    pass
                page.reload(wait_until="domcontentloaded", timeout=45000)
            else:
                # Nenhuma aba do SEI: abre uma unica vez (sera reutilizada)
                _glog_ka('Nenhuma aba do SEI aberta: criando uma unica vez')
                page = browser.contexts[0].new_page()
                page.goto("https://sei.incra.gov.br/sei", wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            url = page.url or ''
            browser.close()

        keepalive_state['ultimo_url'] = url
        keepalive_state['ultima_recarga'] = time.strftime('%Y-%m-%d %H:%M:%S')
        keepalive_state['recargas'] += 1
        if 'login' in url.lower():
            keepalive_state['ultimo_erro'] = 'Sessao expirada (redirecionou para login)'
            log_msg('KEEPALIVE: AVISO - redirecionado para login; refazer login manualmente')
        else:
            keepalive_state['ultimo_erro'] = None
            log_msg(f'KEEPALIVE: aba recarregada ({"existente" if aberta else "nova"}): {url}')
        return {'ok': True, 'url': url}
    except Exception as e:
        keepalive_state['ultimo_erro'] = str(e)
        log_msg(f'KEEPALIVE: erro ao recarregar SEI: {e}')
        if 'ECONNREFUSED' in str(e) or 'connect' in str(e).lower():
            log_msg('KEEPALIVE: porta do Chrome fechada; tentando iniciar o Chrome debug...')
            try:
                from app import verificar_chrome_debug
                threading.Thread(target=verificar_chrome_debug, daemon=True).start()
            except Exception as e2:
                log_msg(f'KEEPALIVE: nao foi possivel iniciar o Chrome debug: {e2}')
        return {'ok': False, 'motivo': str(e)}


def keepalive_pgt_uma_vez():
    """Recarrega a ABA do PGT ja aberta no Chrome debug (mantem sessao ativa).

    - Identifica a aba do PGT e recarrega; se nenhuma existir, abre uma unica
      vez (sera reutilizada nas proximas).
    - So recarrega quando o app esta ocioso (nenhuma fila em processamento).
    """
    if not keepalive_pgt_state['ativo']:
        return {'ok': False, 'motivo': 'desativado'}
    if _fila_ocupada():
        keepalive_pgt_state['ultimo_erro'] = 'Pausado: fila em processamento'
        log_msg('KEEPALIVE PGT: pausado (fila em processamento)')
        return {'ok': False, 'motivo': 'ocupado'}
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page, idx = _achar_aba_pgt(browser)
            aberta = page is not None
            if aberta:
                _glog_ka(f'PGT: reutilizando aba #{idx} com a URL do PGT')
                try:
                    page.bring_to_front()
                except Exception:
                    pass
                page.reload(wait_until="domcontentloaded", timeout=45000)
            else:
                _glog_ka('PGT: nenhuma aba do PGT aberta: criando uma unica vez')
                page = browser.contexts[0].new_page()
                page.goto(PGT_URL, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            url = page.url or ''
            browser.close()

        keepalive_pgt_state['ultimo_url'] = url
        keepalive_pgt_state['ultima_recarga'] = time.strftime('%Y-%m-%d %H:%M:%S')
        keepalive_pgt_state['recargas'] += 1
        url_l = (url or '').lower()
        fora_do_pgt = ('pgt.incra.gov.br' not in url_l
                       or 'login' in url_l
                       or 'acesso-nao-autorizado' in url_l
                       or 'sessao-expirada' in url_l)
        if fora_do_pgt:
            keepalive_pgt_state['ultimo_erro'] = 'Sessao expirada ou acesso nao autorizado'
            log_msg('KEEPALIVE PGT: AVISO - fora da pagina do PGT '
                    f'({url}); refazer login manualmente')
        else:
            keepalive_pgt_state['ultimo_erro'] = None
            log_msg(f'KEEPALIVE PGT: aba recarregada ({"existente" if aberta else "nova"}): {url}')
        return {'ok': True, 'url': url}
    except Exception as e:
        keepalive_pgt_state['ultimo_erro'] = str(e)
        log_msg(f'KEEPALIVE PGT: erro ao recarregar PGT: {e}')
        if 'ECONNREFUSED' in str(e) or 'connect' in str(e).lower():
            log_msg('KEEPALIVE PGT: porta do Chrome fechada; tentando iniciar o Chrome debug...')
            try:
                from app import verificar_chrome_debug
                threading.Thread(target=verificar_chrome_debug, daemon=True).start()
            except Exception as e2:
                log_msg(f'KEEPALIVE PGT: nao foi possivel iniciar o Chrome debug: {e2}')
        return {'ok': False, 'motivo': str(e)}


def keepalive_uma_vez_alvo(alvo='sei'):
    """Roda uma recarga manual do alvo ('sei'/'pgt') e rearma o intervalo."""
    alvo = alvo if alvo in KEEPALIVE_ESTADOS else 'sei'
    funcao = keepalive_uma_vez if alvo == 'sei' else keepalive_pgt_uma_vez
    resultado = funcao()
    _keepalive_ultimo_tick[alvo] = time.time()
    return resultado


def keepalive_loop():
    """Thread unica: recarrega SEI e/ou PGT conforme o intervalo de cada um."""
    log_msg(f'KEEPALIVE: thread iniciada (SEI a cada {keepalive_state["intervalo"]}s, '
            f'PGT a cada {keepalive_pgt_state["intervalo"]}s)')
    for alvo in _keepalive_ultimo_tick:
        _keepalive_ultimo_tick[alvo] = time.time()
    while True:
        time.sleep(5)
        agora = time.time()
        for alvo, state, funcao in (('sei', keepalive_state, keepalive_uma_vez),
                                    ('pgt', keepalive_pgt_state, keepalive_pgt_uma_vez)):
            if not state.get('ativo'):
                continue
            intervalo = max(15, int(state.get('intervalo') or 60))
            if agora - _keepalive_ultimo_tick[alvo] < intervalo:
                continue
            _keepalive_ultimo_tick[alvo] = agora
            try:
                funcao()
            except Exception as e:
                state['ultimo_erro'] = str(e)
                log_msg(f'KEEPALIVE {alvo.upper()}: erro no loop: {e}')


def iniciar_keepalive(ativo=None, intervalo=None, alvo='sei'):
    """Sincroniza o keep-alive de um alvo ('sei'/'pgt') e garante a thread.

    ativo=None mantem o valor atual, para nunca sobrescrever a escolha
    do usuario de deixar o keep-alive desativado.
    """
    state = KEEPALIVE_ESTADOS.get(alvo) or keepalive_state
    alvo = alvo if alvo in KEEPALIVE_ESTADOS else 'sei'
    if ativo is not None:
        state['ativo'] = bool(ativo)
    if intervalo:
        state['intervalo'] = int(intervalo) or 60
    if keepalive_state.get('thread_ativa'):
        log_msg(f'KEEPALIVE: {alvo.upper()} '
                f'{"ativado" if state["ativo"] else "desativado"} '
                f'(a cada {state["intervalo"]}s); thread ja ativa')
        return
    keepalive_state['thread_ativa'] = True
    keepalive_pgt_state['thread_ativa'] = True
    t = threading.Thread(target=keepalive_loop, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Downloads do PGT (aba Baixar): Espelho da Unidade Familiar
# ---------------------------------------------------------------------------

def _pgt_norm(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = s.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', s).strip().lower()


def _pgt_visivel(page, loc):
    try:
        return loc.count() > 0 and loc.first.is_visible()
    except Exception:
        return False


def _pgt_campo(page):
    """Campo de busca do codigo do beneficiario (o id pode estar no wrapper)."""
    seletores = [
        'input#codigoBeneficiario', '#codigoBeneficiario',
        'input[formcontrolname="codigo"]',
        'input[formcontrolname*="codigo" i]',
        'input[id*="codigo" i]', 'input[name*="codigo" i]',
        'input[id*="cod_benef" i]', 'input[name*="cod_benef" i]',
        'input[placeholder*="codigo" i]',
        'input#nomeTitular', '#nomeTitular',
        'input[id*="titular" i]', 'input[name*="titular" i]',
    ]
    for sel in seletores:
        try:
            loc = page.locator(sel).first
            if _pgt_visivel(page, loc):
                return loc
        except Exception:
            continue
    try:
        campos = page.locator('input:visible:not([type="hidden"])')
        for i in range(min(campos.count(), 30)):
            el = campos.nth(i)
            try:
                desc = ' '.join(filter(None, [
                    el.get_attribute('id') or '', el.get_attribute('name') or '',
                    el.get_attribute('placeholder') or '']))
            except Exception:
                desc = ''
            if not re.search(r'login|senha|usuario|email|cpf|data|valor', desc, re.I):
                return el
    except Exception:
        pass
    return None


def _pgt_botao(page, trecho, limite=300):
    """Botao/link visivel cujo texto contem o trecho (normalizado)."""
    alvo = _pgt_norm(trecho)
    try:
        candidatos = page.locator('button, a, input[type="submit"], [role="button"]')
    except Exception:
        return None
    n = min(candidatos.count(), limite)
    for i in range(n):
        el = candidatos.nth(i)
        try:
            if not el.is_visible():
                continue
            txt = el.inner_text() or el.get_attribute('value') or ''
            if alvo in _pgt_norm(txt):
                return el
        except Exception:
            continue
    return None


def _pgt_link_detalhe(page, cod):
    """Link 'Detalhar' da linha que contem o codigo pesquisado."""
    alvo = str(cod or '').strip()
    try:
        links = page.locator('a[href*="detalhar-unidade-familiar"]')
        n = links.count()
    except Exception:
        return None
    if not n:
        return None
    re_cod = re.compile(r'(^|\D)' + re.escape(alvo) + r'(\D|$)') if alvo else None
    for i in range(n):
        a = links.nth(i)
        try:
            if not a.is_visible():
                continue
            linha = a.evaluate(
                "el => (el.closest('tr, [role=\"row\"], li, mat-row') "
                "|| (el.parentElement && el.parentElement.parentElement) "
                "|| el).innerText || ''")
        except Exception:
            linha = ''
        if re_cod and re_cod.search(linha or ''):
            return a
    if n == 1 and not alvo:
        return links.first
    return links.first if n == 1 else None


def _pgt_mensagem(page):
    re_msg = re.compile(r'nenhum registro|nao encontrado|nenhum resultado|'
                        r'sem resultado|nenhuma informacao|nao ha dados|acesso negado', re.I)
    try:
        candidatos = page.locator('[role="alert"], .erro, .alerta, .alert, .mensagem,'
                                  ' .msg, .aviso, span, p, div')
        n = candidatos.count()
    except Exception:
        return None
    for i in range(min(n, 400)):
        el = candidatos.nth(i)
        try:
            if not el.is_visible():
                continue
            t = re.sub(r'\s+', ' ', el.inner_text() or '').strip()
        except Exception:
            continue
        if t and len(t) < 300 and re_msg.search(t):
            return t
    return None


def _pgt_sessao_expirada(page):
    try:
        if 'login' in (page.url or '').lower() or 'logon' in (page.url or '').lower():
            return True
        return page.locator('input[type="password"]').count() > 0
    except Exception:
        return False


def baixar_espelho(page, cod, nome=''):
    """Baixa o Espelho da Unidade Familiar de um beneficiario no PGT.

    Fluxo (mesmo da extensao): abrir busca -> digitar codigo -> Pesquisar
    -> aguardar resultado -> detalhar -> Baixar relatorio -> salvar arquivo.
    """
    _blog(cod, 1, 'Abrindo a busca de beneficiarios...')
    page.goto(PGT_URL, wait_until='domcontentloaded', timeout=PGT_TIMEOUT)
    time.sleep(2)

    if _pgt_sessao_expirada(page):
        return (False, 'Sessao expirada no PGT: refaca o login manualmente')
    if '/sipra/' not in (page.url or ''):
        return (False, f'Fora da pagina de busca do PGT: {page.url}')

    _blog(cod, 2, f'Digitando o codigo {cod} e pesquisando...')
    campo = _pgt_campo(page)
    if not campo:
        return (False, 'Campo #codigoBeneficiario nao encontrado na pagina')
    campo.fill(str(cod))
    time.sleep(0.4)

    pesquisar = _pgt_botao(page, 'pesquis')
    if pesquisar:
        pesquisar.click()
        modo = 'botao Pesquisar'
    else:
        campo.press('Enter')
        modo = 'Enter'
    _blog(cod, 3, f'Busca disparada via {modo}; aguardando o resultado...')

    link = None
    prazo = time.time() + 45
    while time.time() < prazo:
        if _interromper(baixar_state):
            return (False, 'Interrompido pelo usuario')
        link = _pgt_link_detalhe(page, cod)
        if link:
            break
        time.sleep(1.5)
    if not link:
        msg = _pgt_mensagem(page) or 'resultado nao encontrado'
        return (False, f'Codigo {cod} nao localizado no PGT: {msg}')

    _blog(cod, 4, 'Abrindo o detalhe do beneficiario...')
    link.click()
    try:
        page.wait_for_url('**/detalhar-unidade-familiar/**', timeout=20000)
    except Exception:
        pass
    time.sleep(2)

    if _pgt_sessao_expirada(page):
        return (False, 'Sessao expirada no PGT: refaca o login manualmente')

    botao = None
    prazo = time.time() + 30
    while time.time() < prazo:
        botao = _pgt_botao(page, 'baixar relat')
        if botao:
            break
        time.sleep(1)
    if not botao:
        return (False, 'Botao "Baixar relatorio" nao encontrado na pagina de detalhe')

    _blog(cod, 5, 'Clicando em "Baixar relatorio"...')
    os.makedirs(ESPELHOS_DIR, exist_ok=True)
    with page.expect_download(timeout=PGT_TIMEOUT_DOWNLOAD) as info:
        botao.click()
    download = info.value

    # Espera os bytes chegarem; download interrompido nao vira arquivo.
    falha = download.failure()
    if falha:
        return (False, f'Download interrompido no PGT: {falha}')

    # Sempre o nome original sugerido pelo PGT dentro de Downloads/arquivos_pgt.
    # Arquivo ja existente e sobrescrito: o nome nunca ganha sufixo "_<codigo>".
    nome_original = os.path.basename(download.suggested_filename or f'espelho_{cod}.pdf')
    alvo = os.path.join(ESPELHOS_DIR, nome_original)
    if os.path.exists(alvo):
        try:
            os.remove(alvo)
        except OSError as e:
            log_msg(f'BAIXAR [{cod}]: aviso ao remover {alvo}: {e}')

    try:
        download.save_as(alvo)
    except Exception as e:
        # Os bytes ja estao no cache do Chrome: grava manualmente.
        cache = None
        try:
            cache = download.path()
        except Exception:
            cache = None
        if not cache or not os.path.exists(cache):
            return (False, f'Falha ao salvar o download: {e}')
        with open(cache, 'rb') as origem, open(alvo, 'wb') as destino:
            destino.write(origem.read())
        log_msg(f'BAIXAR [{cod}]: save_as falhou ({e}); bytes copiados de {cache}')

    arquivo = os.path.basename(alvo)
    _blog(cod, 6, f'Arquivo salvo em {ESPELHOS_DIR}: {arquivo}')
    return (True, arquivo)


def run_baixar():
    if baixar_state["rodando"]:
        log_msg("BAIXAR: Ja esta em execucao.")
        return

    baixar_state["rodando"] = True
    baixar_state["cancelar"] = False
    baixar_state["pausado"] = False
    baixar_state["status_final"] = ""
    baixar_state["total"] = 0
    baixar_state["processados"] = 0
    baixar_state["sucesso"] = 0
    baixar_state["falha"] = 0
    baixar_state["atual"] = ""
    baixar_state["erros"] = []
    baixar_state["log"] = []
    baixar_state["sucesso_lista"] = []
    baixar_state["falha_lista"] = []
    baixar_state["passo"] = 0
    baixar_state["passo_desc"] = ""

    status_final = 'concluido'
    _blog('-', 0, 'Inicio dos downloads do PGT')

    try:
        # Garante a pasta de destino antes de qualquer clique no PGT.
        try:
            os.makedirs(ESPELHOS_DIR, exist_ok=True)
            _blog('-', 0, f'Pasta de destino: {ESPELHOS_DIR}')
        except Exception as e:
            _blog('-', 0, f'ERRO ao criar a pasta {ESPELHOS_DIR}: {e}')
            status_final = 'erro'
            return

        db = get_db()
        rows = db.execute(
            "SELECT * FROM processos_sei "
            "WHERE COALESCE(download, 0) <> 1 ORDER BY id"
        ).fetchall()
        db.close()

        if not rows:
            _blog('-', 0, 'Nenhum espelho pendente para baixar')
            return

        baixar_state["total"] = len(rows)
        _blog('-', 0, f'{len(rows)} espelho(s) pendente(s)')

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")

            # A aba do PGT ja esta aberta e logada: reutiliza ela. Abrir uma
            # aba nova obrigaria a refazer o login e jogaria a busca do zero.
            page, idx = _achar_aba_pgt(browser)
            aba_propria = page is None
            if aba_propria:
                _blog('-', 0, 'Nenhuma aba do PGT aberta: abrindo uma nova')
                context = browser.contexts[0]
                page = context.new_page()
            else:
                _blog('-', 0, f'Reutilizando a aba #{idx} do PGT ja aberta (logada)')
                context = page.context
                try:
                    page.bring_to_front()
                except Exception:
                    pass
            page.on('dialog', _aceitar_dialog)
            context.on('page', lambda pg: pg.on('dialog', _aceitar_dialog))

            # Comeca pela pagina de busca por codigo do beneficiario.
            try:
                if '/sipra/beneficiario' not in (page.url or ''):
                    _blog('-', 0, f'Abrindo a busca de beneficiarios: {PGT_URL}')
                    page.goto(PGT_URL, wait_until='domcontentloaded', timeout=PGT_TIMEOUT)
                else:
                    _blog('-', 0, 'Aba do PGT ja esta na pagina de busca de beneficiarios')
                time.sleep(2)
            except Exception as e:
                _blog('-', 0, f'AVISO ao abrir a busca do PGT: {e}')

            if _pgt_sessao_expirada(page):
                # Nao adianta seguir: todos os registros dariam falha e ainda
                # seriam marcados como erro na fila.
                _blog('-', 0, 'Sessao expirada no PGT: faca login na aba do PGT '
                              'e clique em Baixar de novo')
                browser.close()
                status_final = 'erro'
                return

            for row in rows:
                if _interromper(baixar_state):
                    status_final = _motivo_interrupcao(baixar_state)
                    _blog('-', 0, f'Interrompido pelo usuario ({status_final}) '
                                  f'| Processados: {baixar_state["processados"]}')
                    break

                reg = dict(row)
                cod = reg.get('cod_beneficiario') or ''
                nome = reg.get('nome') or ''
                baixar_state["atual"] = f"{cod} - {nome}"
                _blog(cod, 0, f'Processando: {cod} - {nome}')

                interrompido = False
                ok, detalhe = False, ''
                for tentativa in (1, 2):
                    if _interromper(baixar_state):
                        interrompido, ok = True, False
                        break
                    try:
                        ok, detalhe = baixar_espelho(page, cod, nome)
                    except InterrupcaoExecucao:
                        interrompido, ok = True, False
                        break
                    except Exception as e:
                        ok, detalhe = False, f"Excecao: {e}"
                        log_msg(traceback.format_exc())
                    if ok:
                        break
                    _blog(cod, 0, f'Tentativa {tentativa} falhou: {detalhe}')
                    time.sleep(2)

                if interrompido:
                    status_final = _motivo_interrupcao(baixar_state)
                    _blog('-', 0, f'Interrompido no meio do registro {cod} ({status_final}) '
                                  f'| Processados: {baixar_state["processados"]}')
                    break

                db = get_db()
                agora = time.strftime('%Y-%m-%d %H:%M:%S')
                if ok:
                    db.execute(
                        "UPDATE processos_sei SET download = 1, erro_download = NULL, "
                        "arquivo_download = ?, data_download = ? WHERE id = ?",
                        (detalhe, agora, reg['id'])
                    )
                    baixar_state["sucesso"] += 1
                    baixar_state["sucesso_lista"].append({'cod': cod, 'arquivo': detalhe})
                    _blog(cod, 99, f'SUCESSO: {detalhe}')
                else:
                    db.execute(
                        "UPDATE processos_sei SET download = -1, erro_download = ?, "
                        "data_download = ? WHERE id = ?",
                        (detalhe, agora, reg['id'])
                    )
                    baixar_state["falha"] += 1
                    baixar_state["erros"].append({"cod": cod, "nome": nome, "erro": detalhe})
                    baixar_state["falha_lista"].append({"cod": cod, "erro": detalhe})
                    _blog(cod, 99, f'FALHA: {detalhe}')
                db.commit()
                db.close()

                baixar_state["processados"] += 1

            # So fecha a aba se ela foi criada por nos: a do usuario fica
            # aberta (e logada) para a proxima execucao.
            if aba_propria:
                page.close()
            else:
                _blog('-', 0, 'Aba do PGT mantida aberta (reutilizada)')
            browser.close()

    except InterrupcaoExecucao:
        status_final = _motivo_interrupcao(baixar_state)
        _blog('-', 0, f'Interrompido pelo usuario ({status_final}) '
                      f'| Processados: {baixar_state["processados"]}')
    except Exception as e:
        _blog('-', 0, f'ERRO GERAL: {e}')
        log_msg(traceback.format_exc())
        status_final = 'erro'
    finally:
        cancelado = bool(baixar_state.get("cancelar"))
        if cancelado:
            # Cancelar zera o progresso dos downloads; os registros ficam na fila.
            try:
                db = get_db()
                db.execute(
                    "UPDATE processos_sei SET download = 0, erro_download = NULL, "
                    "arquivo_download = NULL, data_download = NULL "
                    "WHERE download IS NOT NULL AND download <> 0"
                )
                db.commit()
                db.close()
            except Exception as e:
                cancelado = False
                log_msg(f'BAIXAR: AVISO ao zerar progresso: {e}')
        _zerar_flags(baixar_state, status_final)
        baixar_state["atual"] = ""
        if cancelado:
            _blog('-', 0, 'Cancelado: progresso de download zerado (registros mantidos)')
        _blog('-', 0, f"Finalizado ({status_final}) | Sucesso: {baixar_state['sucesso']} "
                      f"| Falha: {baixar_state['falha']}")


def run_sei():
    if sei_state["rodando"]:
        log_msg("SEI: Ja esta em execucao.")
        return

    sei_state["rodando"] = True
    sei_state["cancelar"] = False
    sei_state["pausado"] = False
    sei_state["status_final"] = ""
    sei_state["total"] = 0
    sei_state["processados"] = 0
    sei_state["sucesso"] = 0
    sei_state["falha"] = 0
    sei_state["atual"] = ""
    sei_state["erros"] = []
    sei_state["log"] = []
    sei_state["sucesso_lista"] = []
    sei_state["falha_lista"] = []
    sei_state["passo"] = 0
    sei_state["passo_desc"] = ""

    status_final = 'concluido'
    _registrar_status("Inicio do processamento")

    try:
        config = carregar_config()

        rows = pendencias_anexar()

        if not rows:
            status_final = 'sem_pendencias'
            _registrar_status("Nenhum registro pendente ou com erro para anexar")
            log_msg("SEI: Nenhum registro pendente ou com erro para anexar.")
            return

        sei_state["total"] = len(rows)
        _registrar_status(f"{len(rows)} registro(s) na fila (pendente(s) ou com erro)")
        log_msg(f"SEI: {len(rows)} registro(s) na fila (pendente(s) ou com erro).")

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            page = context.new_page()
            page.on('dialog', _aceitar_dialog)
            context.on('page', lambda pg: pg.on('dialog', _aceitar_dialog))

            for row in rows:
                if _interromper(sei_state):
                    status_final = _motivo_interrupcao(sei_state)
                    _registrar_status(f'Interrompido pelo usuario ({status_final}) '
                                      f'| Processados: {sei_state["processados"]}')
                    break

                reg = dict(row)
                cod_sipra = reg['cod_sipra']
                nome = reg['nome'] or ''
                # NUP do processo pai (processos_sei.processo_sei)
                processo_sei = (reg.get('processo_sei') or '').strip()
                pdf_nome = reg['pdf_anexo']
                caminho_pdf = os.path.join(UPLOADS_DIR, pdf_nome)

                sei_state["atual"] = f"{cod_sipra} - {nome}"
                _registrar_status(f"Processando: {cod_sipra} - {nome}")
                log_msg(f"SEI: Processando {cod_sipra} | {nome} | Proc: {processo_sei}")

                if not os.path.exists(caminho_pdf):
                    msg = f"Arquivo nao encontrado: {pdf_nome}"
                    log_msg(f"SEI: AVISO: {msg}")
                    _registrar_status(f"ERRO: {msg}")
                    sei_state["falha"] += 1
                    sei_state["erros"].append({"cod_sipra": cod_sipra, "nome": nome, "erro": msg})
                    db = get_db()
                    db.execute("UPDATE anexos_sei SET anexado = -1, data_anexo = NULL "
                               "WHERE id = ?", (reg['id'],))
                    db.commit()
                    db.close()
                    continue

                sessao_expirada = False
                try:
                    # O banco guarda o TEMPLATE (ex.: {{Nome}}); resolve agora,
                    # com os dados atuais do registro, e so cai no padrao da
                    # configuracao se sobrar texto vazio.
                    nome_arvore_tpl = (reg.get('nome_arvore') or '').strip() \
                        or str(config.get('nome_arvore') or '').strip()
                    nome_arvore_final = processar_nome_arvore_template(nome_arvore_tpl, reg) or nome_arvore_tpl
                    sucesso, detalhe_erro = anexar_arquivo_no_sei(page, processo_sei, caminho_pdf, config, nome_arvore_final)
                except InterrupcaoExecucao:
                    status_final = _motivo_interrupcao(sei_state)
                    _registrar_status(f'Interrompido no meio do registro {cod_sipra} ({status_final}) '
                                      f'| Processados: {sei_state["processados"]}')
                    break
                except SessaoExpirada as e:
                    sucesso, detalhe_erro = False, str(e)
                    sessao_expirada = True
                except Exception as e:
                    sucesso, detalhe_erro = False, f"Excecao: {e}"
                    log_msg(traceback.format_exc())

                if sucesso:
                    db = get_db()
                    db.execute(
                        "UPDATE anexos_sei SET anexado = 1, data_anexo = ? "
                        "WHERE id = ?",
                        (time.strftime('%Y-%m-%d %H:%M:%S'), reg['id'])
                    )
                    db.commit()
                    db.close()
                    sei_state["sucesso"] += 1
                    sei_state["sucesso_lista"].append(cod_sipra)
                    _registrar_status(f"OK: {cod_sipra} - {nome}")
                    log_msg(f"SEI: {cod_sipra} anexado com sucesso.")
                else:
                    sei_state["falha"] += 1
                    erro_detalhe = detalhe_erro or "Falha ao anexar (sem detalhe)"
                    sei_state["erros"].append({"cod_sipra": cod_sipra, "nome": nome, "erro": erro_detalhe})
                    sei_state["falha_lista"].append({"cod_sipra": cod_sipra, "erro": erro_detalhe})
                    db = get_db()
                    db.execute("UPDATE anexos_sei SET anexado = -1, data_anexo = NULL "
                               "WHERE id = ?", (reg['id'],))
                    db.commit()
                    db.close()
                    _registrar_status(f"FALHA: {cod_sipra} - {nome} | {erro_detalhe}")
                    log_msg(f"SEI: FALHA ao anexar {cod_sipra}. {erro_detalhe}")

                if sessao_expirada:
                    status_final = 'sessao_expirada'
                    _registrar_status(f'ABORTADO: {detalhe_erro}')
                    sei_state["processados"] += 1
                    break

                sei_state["processados"] += 1

            page.close()
            browser.close()

    except InterrupcaoExecucao:
        status_final = _motivo_interrupcao(sei_state)
        _registrar_status(f"Interrompido pelo usuario ({status_final}) "
                          f"| Processados: {sei_state['processados']}")
    except Exception as e:
        _registrar_status(f"ERRO GERAL: {e}")
        log_msg(f"SEI: ERRO GERAL: {e}")
        status_final = 'erro'
    finally:
        _registrar_status(f"Finalizado ({status_final}) | Sucesso: {sei_state['sucesso']} "
                          f"| Falha: {sei_state['falha']}")
        log_msg(f"SEI: Finalizado ({status_final}). Sucesso={sei_state['sucesso']} "
                f"Falha={sei_state['falha']}")
        sei_state["atual"] = ""
        _zerar_flags(sei_state, status_final)


if __name__ == '__main__':
    run_sei()
