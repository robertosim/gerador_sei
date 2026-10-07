import logging
import re
import sqlite3
import os
import sys
import json

from tipos_processo import TIPOS_PROCESSO


def dir_base():
    """Pasta onde ficam os dados do app.

    Executavel (.exe): a pasta do proprio executavel. Codigo-fonte: a pasta
    do projeto. Assim banco, logs, uploads e CSVs ficam sempre ao lado do
    que o usuario roda, mesmo dentro do .exe unico (que extrai em temp).
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = dir_base()
DB_PATH = os.path.join(BASE_DIR, 'processos_sei.db')

DEFAULT_CONFIG = {
    'serie': '82',
    'nome_arvore': 'CCIR',
    'hipotese': '4',
    'nivel': '1'
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


TIPOS_DOCUMENTO = [
    (46, 'Abaixo-Assinado'), (769, 'Acesso ao Serviço de Ingresso de Famílias - PGT'),
    (8, 'Acórdão'), (106, 'Acordo'), (794, 'Acordo de Adesão - TERRA CIDADÃ'),
    (729, 'Acordo de Adesão - UMC'), (795, 'Acordo de Cooperação - TERRA CIDADÃ'),
    (95, 'Agenda'), (262, 'Alegações'), (48, 'Alvará'), (116, 'Anais'),
    (7, 'Análise'), (626, 'Análise de Processo Disciplinar'), (263, 'Anexo'),
    (778, 'Anexo - Modelo de Ordem de Serviço'), (666, 'Anexo VIII - Requisição de Licença Capacitação'),
    (745, 'Anexo XI - Acordo de Adesão'), (746, 'Anexo XII - Acordo de Cooperação'),
    (96, 'Anotação'), (117, 'Anteprojeto'), (115, 'Apartado'), (118, 'Apólice'),
    (119, 'Apostila'), (275, 'Apresentação'), (400, 'Aprovação'),
    (480, 'ART - Anotação de Responsabilidade Técnica'), (395, 'Artigo'),
    (67, 'Ata'), (74, 'Atestado'), (286, 'Atesto'), (753, 'Atividade de Manutenção Preventiva'),
    (3, 'Ato'), (52, 'Áudio'), (120, 'Auto'), (269, 'Autorização'),
    (294, 'Autorização de Empenho'), (695, 'Autorização de Pagamento - AP'),
    (687, 'Autorização de Saída de Volume de Material'), (380, 'Avaliação'),
    (121, 'Aviso'), (703, 'Aviso de Dispensa Eletrônica'), (32, 'Balancete'),
    (33, 'Balanço'), (122, 'Bilhete'), (34, 'Boletim'), (97, 'Boleto'),
    (785, 'Cadastro'), (211, 'Calendário'), (270, 'Canhoto'), (377, 'Capa'),
    (80, 'Carta'), (209, 'Cartão'), (123, 'Cartaz'), (87, 'Carteira'),
    (399, 'Cartilha'), (124, 'Cédula'), (81, 'Certidão'), (610, 'Certidão de Quitação'),
    (721, 'Certidão de Tempo Contribuição IN 128'), (683, 'Certidão de Tempo de Contribuição IN 77'),
    (802, 'Certidão Processual'), (803, 'Certificação Processual'), (82, 'Certificado'),
    (391, 'Check List'), (125, 'Cheque'), (655, 'Citação'), (280, 'CNH'),
    (210, 'CNPJ'), (673, 'Comissão de Ética - Relatório Final'),
    (726, 'Compartilhamento de Imóvel e Rateio de Despesas'), (35, 'Comprovante'),
    (531, 'Comunicação'), (14, 'Comunicado'), (271, 'Confirmação'), (197, 'Consulta'),
    (36, 'Conta'), (72, 'Conteúdo de Mídia'), (126, 'Contracheque'), (112, 'Contrarrazões'),
    (37, 'Contrato'), (105, 'Convenção'), (232, 'Convênio'), (127, 'Convite'),
    (38, 'Correspondência'), (29, 'Cota'), (272, 'Cotação'), (88, 'CPF'),
    (128, 'Crachá'), (98, 'Credencial'), (129, 'Cronograma'), (39, 'Croqui'),
    (130, 'Currículo'), (40, 'Dacon'), (198, 'Debênture'), (41, 'Decisão'),
    (83, 'Declaração'), (801, 'Declaração de Utilização de Modelos AGU/MGI'),
    (131, 'Decreto'), (42, 'Defesa'), (656, 'Defesa escrita'), (43, 'Degravacão'),
    (132, 'Deliberação'), (44, 'Demonstração'), (133, 'Demonstrativo'),
    (45, 'Denúncia'), (134, 'Depoimento'), (5, 'Despacho'), (93, 'Despacho (AGU)'),
    (750, 'Despacho com Comprovante de Postagem'), (276, 'Diagnóstico'),
    (135, 'Diário'), (77, 'Diploma'), (199, 'Diretriz'), (136, 'Dissertação'),
    (264, 'Documento'), (137, 'Dossiê'), (68, 'Edital'), (528, 'Elogio'),
    (30, 'E-mail'), (138, 'Embargos'), (139, 'Emenda'), (544, 'Ementa'),
    (140, 'Escala'), (108, 'Esclarecimento'), (141, 'Escritura'),
    (49, 'Escrituração'), (50, 'Estatuto'), (279, 'Estratégia'), (282, 'Estudo'),
    (277, 'Exame'), (265, 'Exposição'), (142, 'Exposição de Motivos'),
    (51, 'Extrato'), (627, 'Extrato de TAC'), (738, 'Extrato de Termo Aditivo'),
    (84, 'Fatura'), (143, 'Ficha'), (742, 'Ficha de Avaliação do RTID'),
    (144, 'Fluxograma'), (200, 'Folder'), (99, 'Folha'), (266, 'Folheto'),
    (145, 'Formulário'), (818, 'Formulário - Usuário SCDP'),
    (710, 'Formulário 1 CAF Cadastro SR INCRA'), (712, 'Formulário 2 CAF Cadastro Responsável Legal'),
    (713, 'Formulário 3 CAF - Responsável Técnico da SR'), (711, 'Formulário 4 CAF Dados do Emissor(a) na SR'),
    (773, 'Formulário Cadastro Usuário Requisição de Material'), (384, 'Foto'),
    (201, 'Grade Curricular'), (146, 'Guia'), (79, 'Histórico'),
    (295, 'Histórico de Gestão do Contrato'), (109, 'Impugnação'), (202, 'Indicação'),
    (92, 'Informação'), (16, 'Informe'), (273, 'Inscrição'), (203, 'Instrução'),
    (310, 'Instrução Normativa'), (312, 'Instrução Normativa Conjunta'),
    (313, 'Instrução Normativa Conjunta_Minuta'), (311, 'Instrução Normativa_Minuta'),
    (784, 'Instrumento'), (110, 'Intenção'), (372, 'Intimação'), (147, 'Inventário'),
    (368, 'LAF - Laudo Agronômico de Fiscalização'), (54, 'Laudo'),
    (578, 'Laudo Final de Classificação de Material'), (148, 'Lei'), (55, 'Licença'),
    (100, 'Lista'), (582, 'Lista de Verificação (CheckList)'), (267, 'Listagem'),
    (56, 'Livro'), (365, 'LVA - Laudo de Vistoria e Avaliação'), (69, 'Mandado'),
    (734, 'Manifestação Acerca da Proposta de Portaria'), (149, 'Manifesto'),
    (113, 'Manual'), (150, 'Mapa'), (576, 'Mapa Controle Desempenho Manutenção Veículo'),
    (212, 'Matéria'), (78, 'Material'), (151, 'Medida Provisória'), (57, 'Memória'),
    (152, 'Memorial'), (153, 'Mensagem'), (204, 'Minuta'),
    (786, 'Minuta ANEXO XI - Termo de Adesão'), (730, 'Minuta de Acordo de Adesão - UMC'),
    (702, 'Minuta de Aviso de Dispensa Eletrônica'), (790, 'Minuta de Decreto'),
    (592, 'Minuta de Despacho'), (304, 'Minuta de Exposição de Motivos'),
    (731, 'Minuta de Plano de Trabalho para Acordo Adesão'),
    (698, 'MINUTA DE PORTARIA CONJUNTA'), (718, 'Minuta de Portaria de Pessoal'),
    (735, 'Minuta de Portaria de Reconhecimento'), (716, 'Minuta de Portaria Normativa'),
    (736, 'Minuta de Termo Aditivo ao Título de Domínio'),
    (749, 'Minuta de Termo de Fomento'), (804, 'Minuta de Voto'),
    (805, 'Minuta do Documento de Formalização da Demanda'),
    (777, 'Minuta do Termo de Credenciamento'),
    (733, 'Minuta Manifestação Acerca da Proposta de Portaria'),
    (743, 'Minuta Parcelamento de Débito'), (154, 'Moção'), (376, 'Modelo'),
    (213, 'Movimentação'), (58, 'Norma'), (91, 'Nota'),
    (625, 'Nota Técnica para Juízo de Admissibilidade'), (540, 'Notícia'),
    (59, 'Notificação'), (11, 'Ofício'), (205, 'Ofício-Circular'), (206, 'Orçamento'),
    (207, 'Ordem'), (756, 'Ordem de Serviço (modelo)'),
    (599, 'Ordem de Serviço de Demanda CIT'), (598, 'Ordens de Serviço de Demanda - CIT'),
    (155, 'Organograma'), (156, 'Orientação'), (278, 'Página'), (396, 'Palestra'),
    (157, 'Panfleto'), (725, 'Parcelamento de Débito'), (191, 'Parecer'),
    (758, 'Parecer Técnico'), (158, 'Passaporte'), (159, 'Pauta'), (107, 'Pedido'),
    (781, 'Pedido de PassKey - SIAFI'), (363, 'Pesquisa'),
    (300, 'Pesquisa/Análise de Preços'), (160, 'Petição'), (706, 'PGD - Plano de Trabalho'),
    (705, 'PGD - Relatório de Execução e Avaliação'),
    (704, 'PGD - Termo de Adesão do Servidor'), (104, 'Planilha'), (73, 'Plano'),
    (796, 'Plano de Trab - Acordo de Adesão - TERRA CIDADÃ'),
    (797, 'Plano de Trab -Acordo de Cooperação - TERRA CIDADÃ'),
    (345, 'Plano de Trabalho'), (732, 'Plano de Trabalho para Acordo Adesão - UMC'),
    (161, 'Planta'), (10, 'Portaria'), (699, 'Portaria Conjunta'),
    (720, 'Portaria de Pessoal'), (719, 'Portaria Normativa'), (162, 'Precatório'),
    (60, 'Procuração'), (163, 'Programa'), (348, 'Programação'), (101, 'Projeto'),
    (75, 'Prontuário'), (208, 'Pronunciamento'), (85, 'Proposta'), (164, 'Prospecto'),
    (165, 'Protocolo'), (744, 'Protocolo de Intenções'), (166, 'Prova'),
    (103, 'Publicação'), (502, 'Quadro'), (167, 'Questionário'),
    (362, 'RAMT - Relátorio de Análise de Mercado de Terras'), (168, 'Receita'),
    (169, 'Recibo'), (61, 'Reclamação'), (111, 'Recurso'), (27, 'Referendo'),
    (170, 'Regimento'), (62, 'Registro'), (171, 'Regulamento'), (102, 'Relação'),
    (697, 'Relação de Mobiliário e Bens'), (367, 'Relação de Títulos'),
    (63, 'Relatório'), (352, 'Relatório Swot'), (172, 'Release'), (173, 'Representação'),
    (64, 'Requerimento'), (696, 'Requerimento Concessão Ajuda de Custo/Transporte'),
    (812, 'Requerimento para atendimento de demandas diversas'), (65, 'Requisição'),
    (1, 'Resolução'), (76, 'Resultado'), (174, 'Resumo'), (309, 'Retificação'),
    (89, 'RG'), (175, 'Roteiro'), (176, 'Sentença'), (529, 'Simplifique'),
    (177, 'Sinopse'), (178, 'Solicitação'), (530, 'Sugestão'), (268, 'Sumário'),
    (2, 'Súmula'), (179, 'Tabela'), (180, 'Telegrama'), (90, 'Termo'),
    (737, 'Termo Aditivo ao Título de Domínio'), (657, 'Termo de Ajustamento de Conduta'),
    (754, 'Termo de Ciência'), (755, 'Termo de Ciência (MINUTA)'),
    (820, 'Termo de Compromisso de Manutenção de Sigilo'),
    (800, 'Termo de Confidencialidade e Sigilo'), (776, 'Termo de Credenciamento'),
    (728, 'Termo de Doação'), (624, 'Termo de Encerramento e Remessa - Disciplinar'),
    (748, 'Termo de Fomento'), (654, 'Termo de Indiciação'),
    (798, 'Termo de Responsabilidade e Compro - TERRA CIDADÃ'),
    (446, 'Termo de Responsabilidade SNCR - TERRA CIDADÃ'),
    (715, 'Termo de Verificação de Bens em Estoque'),
    (811, 'Termo de Vista a Processos SEI-Incra'), (181, 'Tese'), (182, 'Testamento'),
    (684, 'TIC - Análise para Internalização'), (727, 'TIC - Caderno de Cotação'),
    (757, 'TIC - Declaração de Disponibilidade Orçamentária'),
    (752, 'TIC - Detalhamento das Especificações'),
    (767, 'TIC - Detalhamento dos Componentes Datacenter'),
    (722, 'TIC - Laudo Técnico - Infraestrutura'),
    (779, 'TIC - Ordem de Serviço (Modelo TR)'), (821, 'TIC - Termo de Ciência'),
    (740, 'TIC - Termo de Ciência e Concordância'), (723, 'TIC - Termo de Compromisso'),
    (782, 'Ticket'), (183, 'Título'), (53, 'Vídeo'), (71, 'Volume'),
    (94, 'Voto'), (274, 'Voucher'),
]

HIPOTESE_LEGAL = [
    (1, 'Controle Interno (Art. 26, § 3º, da Lei nº 10.180/2001)'),
    (2, 'Direito Autoral (Art. 24, III, da Lei nº 9.610/1998)'),
    (3, 'Documento Preparatório (Art. 7º, § 3º, da Lei nº 12.527/2011)'),
    (22, 'Fase Interna - Processo Licitatório (Artigo 5º, caput Lei nº 14.133/2021)'),
    (19, 'Fase Interna de Processo Licitatório (Artigo 3º, caput e §3º, da lei nº 8.666/1993)'),
    (23, 'Incidentes Cibernéticos (art. 15 do Decreto nº 10.748, de 16/05/2021)'),
    (4, 'Informação Pessoal (Art. 31 da Lei nº 12.527/2011)'),
    (5, 'Informações Privilegiadas de Sociedades Anônimas (Art. 155, § 2º, da Lei nº 6.404/1976)'),
    (6, 'Interceptação de Comunicações Telefônicas (Art. 8º, caput, da Lei nº 9.296/1996)'),
    (7, 'Investigação de Responsabilidade de Servidor (Art. 150 da Lei nº 8.112/1990)'),
    (8, 'Livros e Registros Contábeis Empresariais (Art. 1.190 do Código Civil)'),
    (9, 'Operações Bancárias (Art. 1º da Lei Complementar nº 105/2001)'),
    (10, 'Proteção da Propriedade Intelectual de Software (Art. 2º da Lei nº 9.609/1998)'),
    (11, 'Protocolo -Pendente Análise de Restrição de Acesso (Art. 6º, III, da Lei nº 12.527/2011)'),
    (12, 'Segredo de Justiça no Processo Civil (Art. 189 do Código de Processo Civil)'),
    (13, 'Segredo de Justiça no Processo Penal (Art. 201, § 6º, do Código de Processo Penal)'),
    (14, 'Segredo Industrial (Art. 195, XIV, Lei nº 9.279/1996)'),
    (15, 'Sigilo das Comunicações (Art. 3º, V, da Lei nº 9.472/1997)'),
    (16, 'Sigilo de Empresa em Situação Falimentar (Art. 169 da Lei nº 11.101/2005)'),
    (17, 'Sigilo do Inquérito Policial (Art. 20 do Código de Processo Penal)'),
    (18, 'Situação Econômico-Financeira de Sujeito Passivo (Art. 198, caput, da Lei nº 5.172/1966 - CTN)'),
]


# ---------------------------------------------------------------------------
# Esquema novo:
#   processos_sei  (antes processos_gerados) - 1 registro por beneficiario;
#                 `processo_gerado` passou a se chamar `processo_sei` (NUP) e
#                 `processo_sei_original` (NUP do CSV) foi descartada.
#   anexos_sei     - N anexos por processo; `nome` e `processo_sei` foram
#                 removidos (hoje vem do processo pai) e a FK
#                 cod_sipra -> processos_sei.cod_beneficiario garante a
#                 relacao 1:N.
# ---------------------------------------------------------------------------

DDL_PROCESSOS_SEI = '''CREATE TABLE IF NOT EXISTS processos_sei (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cod_beneficiario TEXT NOT NULL,
    nome TEXT,
    dados_csv TEXT,
    processo_sei TEXT,
    status INTEGER DEFAULT 0,
    erro TEXT,
    data_geracao TEXT,
    download INTEGER DEFAULT 0,
    erro_download TEXT,
    arquivo_download TEXT,
    data_download TEXT
)'''

DDL_ANEXOS_SEI = '''CREATE TABLE IF NOT EXISTS anexos_sei (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cod_sipra TEXT NOT NULL,
    pdf_anexo TEXT,
    anexado INTEGER DEFAULT 0,
    tipo_documento INTEGER,
    nome_arvore TEXT,
    nivel_acesso INTEGER DEFAULT 1,
    hipotese_legal INTEGER,
    data_anexo TEXT,
    FOREIGN KEY (cod_sipra) REFERENCES processos_sei(cod_beneficiario)
)'''

COLUNAS_DOWNLOAD = ('download INTEGER DEFAULT 0', 'erro_download TEXT',
                    'arquivo_download TEXT', 'data_download TEXT')


def _existe_tabela(conn, nome):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                        (nome,)).fetchone() is not None


def _colunas_tabela(conn, tabela):
    return [r[1] for r in conn.execute(f'PRAGMA table_info({tabela})')]


def _fk_anexos_presente(conn):
    try:
        linhas = conn.execute('PRAGMA foreign_key_list(anexos_sei)').fetchall()
    except sqlite3.Error:
        return False
    return any(l[2] == 'processos_sei' and l[3] == 'cod_sipra' and l[4] == 'cod_beneficiario'
               for l in linhas)


def _migrar_processos(conn):
    """processos_gerados -> processos_sei (processo_gerado -> processo_sei)."""
    if not _existe_tabela(conn, 'processos_gerados'):
        return
    cols = _colunas_tabela(conn, 'processos_gerados')
    # Colunas de download criadas por versoes antigas: garante antes de copiar.
    for ddl in COLUNAS_DOWNLOAD:
        nome_col = ddl.split()[0]
        if nome_col not in cols:
            try:
                conn.execute(f'ALTER TABLE processos_gerados ADD COLUMN {ddl}')
                cols.append(nome_col)
            except sqlite3.Error:
                pass
    if not _existe_tabela(conn, 'processos_sei'):
        conn.execute(DDL_PROCESSOS_SEI)
    alvo = _colunas_tabela(conn, 'processos_sei')
    pares = [(c, c) for c in cols if c in alvo]
    if 'processo_gerado' in cols and 'processo_sei' in alvo:
        pares.append(('processo_gerado', 'processo_sei'))
    vazio = conn.execute('SELECT COUNT(*) FROM processos_sei').fetchone()[0] == 0
    if pares and vazio:
        conn.execute(
            f"INSERT INTO processos_sei ({', '.join(d for _, d in pares)}) "
            f"SELECT {', '.join(o for o, _ in pares)} FROM processos_gerados")
    conn.execute('DROP TABLE processos_gerados')
    log_msg(f'MIGRACAO: processos_gerados -> processos_sei '
            f'({len(pares)} coluna(s) copiada(s))')


def _migrar_anexos(conn):
    """Recria anexos_sei sem nome/processo_sei e com a FK para processos_sei."""
    if not _existe_tabela(conn, 'anexos_sei'):
        return
    cols = _colunas_tabela(conn, 'anexos_sei')
    precisa = 'nome' in cols or 'processo_sei' in cols or not _fk_anexos_presente(conn)
    if not precisa:
        return

    # Codigos sem processo pai: a linha antiga ja trazia nome/NUP, entao cria
    # o pai a partir dela (status NULL = fora da fila de geracao).
    nome_sql = 'a.nome' if 'nome' in cols else 'NULL'
    nup_sql = 'a.processo_sei' if 'processo_sei' in cols else 'NULL'
    conn.execute(f'''
        INSERT INTO processos_sei (cod_beneficiario, nome, processo_sei, status)
        SELECT a.cod_sipra,
               MAX(CASE WHEN TRIM(COALESCE({nome_sql}, '')) <> '' THEN {nome_sql} END),
               MAX(CASE WHEN TRIM(COALESCE({nup_sql}, '')) <> '' THEN {nup_sql} END),
               NULL
          FROM anexos_sei a
         WHERE TRIM(COALESCE(a.cod_sipra, '')) <> ''
           AND NOT EXISTS (SELECT 1 FROM processos_sei p
                            WHERE p.cod_beneficiario = a.cod_sipra)
         GROUP BY a.cod_sipra''')

    conn.execute('DROP TABLE IF EXISTS anexos_sei_novo')
    conn.execute('''CREATE TABLE anexos_sei_novo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cod_sipra TEXT NOT NULL,
        pdf_anexo TEXT,
        anexado INTEGER DEFAULT 0,
        tipo_documento INTEGER,
        nome_arvore TEXT,
        nivel_acesso INTEGER DEFAULT 1,
        hipotese_legal INTEGER,
        data_anexo TEXT,
        FOREIGN KEY (cod_sipra) REFERENCES processos_sei(cod_beneficiario)
    )''')
    mantidas = [c for c in cols if c not in ('nome', 'processo_sei')]
    conn.execute(f"INSERT INTO anexos_sei_novo ({', '.join(mantidas)}) "
                 f"SELECT {', '.join(mantidas)} FROM anexos_sei")
    conn.execute('DROP TABLE anexos_sei')
    conn.execute('ALTER TABLE anexos_sei_novo RENAME TO anexos_sei')
    removidas = [c for c in cols if c not in mantidas]
    log_msg(f'MIGRACAO: anexos_sei recriado com FK '
            f'(removidas: {", ".join(removidas) or "nenhuma"})')


def init_db():
    conn = get_db()
    # A recriacao das tabelas desliga/religa FKs; a pragma nao vale dentro de
    # transacao, entao desliga antes de qualquer DML e nao volta a ligar aqui
    # (cada nova conexao, via get_db, ja liga).
    conn.execute('PRAGMA foreign_keys = OFF')
    _migrar_processos(conn)
    conn.execute(DDL_PROCESSOS_SEI)
    _migrar_anexos(conn)
    conn.execute(DDL_ANEXOS_SEI)
    try:
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_processos_sei_cod '
                     'ON processos_sei(cod_beneficiario)')
    except sqlite3.IntegrityError as e:
        log_msg(f'AVISO: indice unico em processos_sei.cod_beneficiario nao criado ({e})')
    conn.execute('''CREATE TABLE IF NOT EXISTS tipo_documento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo INTEGER NOT NULL UNIQUE,
        nome TEXT NOT NULL
    )''')
    if conn.execute('SELECT COUNT(*) FROM tipo_documento').fetchone()[0] == 0:
        conn.executemany('INSERT INTO tipo_documento (codigo, nome) VALUES (?, ?)', TIPOS_DOCUMENTO)
    conn.execute('''CREATE TABLE IF NOT EXISTS hipotese_legal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo INTEGER NOT NULL UNIQUE,
        nome TEXT NOT NULL
    )''')
    if conn.execute('SELECT COUNT(*) FROM hipotese_legal').fetchone()[0] == 0:
        conn.executemany('INSERT INTO hipotese_legal (codigo, nome) VALUES (?, ?)', HIPOTESE_LEGAL)
    conn.execute('''CREATE TABLE IF NOT EXISTS config_anexo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        serie TEXT DEFAULT '263',
        sigilo TEXT DEFAULT 'R',
        nome_arvore TEXT DEFAULT 'Espelho SIPRA',
        hipotese TEXT DEFAULT '4',
        nivel TEXT DEFAULT '1'
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS config_geracao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo_processo TEXT DEFAULT '',
        especificacao TEXT DEFAULT '{{Nome Titular 1}}',
        interessados TEXT DEFAULT '{{Nome Titular 1}}',
        observacoes TEXT DEFAULT '',
        nivel_acesso TEXT DEFAULT '1',
        hipotese_legal TEXT DEFAULT '4'
    )''')
    try:
        conn.execute("ALTER TABLE config_geracao ADD COLUMN hipotese_legal TEXT DEFAULT '4'")
    except Exception:
        pass
    if conn.execute('SELECT COUNT(*) FROM config_geracao').fetchone()[0] == 0:
        conn.execute('''INSERT INTO config_geracao (tipo_processo, especificacao, interessados,
                        observacoes, nivel_acesso, hipotese_legal)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (DEFAULT_CONFIG_GERACAO['tipo_processo'], DEFAULT_CONFIG_GERACAO['especificacao'],
                      DEFAULT_CONFIG_GERACAO['interessados'], DEFAULT_CONFIG_GERACAO['observacoes'],
                      DEFAULT_CONFIG_GERACAO['nivel_acesso'], DEFAULT_CONFIG_GERACAO['hipotese_legal']))
    else:
        # Instalacao antiga sem tipo escolhido: ja deixa o padrao selecionado
        # (Finalistico: Desenvolvimento de Assentamentos).
        conn.execute("UPDATE config_geracao SET tipo_processo = ? "
                     "WHERE tipo_processo IS NULL OR TRIM(tipo_processo) = ''",
                     (DEFAULT_CONFIG_GERACAO['tipo_processo'],))
    conn.execute('''CREATE TABLE IF NOT EXISTS tipo_processo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo INTEGER NOT NULL UNIQUE,
        nome TEXT NOT NULL,
        sigiloso INTEGER DEFAULT 0
    )''')
    if conn.execute('SELECT COUNT(*) FROM tipo_processo').fetchone()[0] == 0:
        conn.executemany('INSERT OR IGNORE INTO tipo_processo (codigo, nome, sigiloso) VALUES (?, ?, ?)',
                         TIPOS_PROCESSO)
    _criar_config_keepalive(conn)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Keep-alive (SEI e PGT): preferencia gravada NO BANCO (substitui o
# keepalive.json, que era migrado na primeira execucao e depois apagado)
# ---------------------------------------------------------------------------

KEEPALIVE_ALVOS = ('sei', 'pgt')
KEEPALIVE_PADRAO = {'ativo': True, 'intervalo': 60}


def _criar_config_keepalive(conn):
    """Cria a tabela de keep-alive e migra o keepalive.json antigo, se existir."""
    conn.execute('''CREATE TABLE IF NOT EXISTS config_keepalive (
        alvo TEXT PRIMARY KEY,
        ativo INTEGER NOT NULL DEFAULT 1,
        intervalo INTEGER NOT NULL DEFAULT 60
    )''')
    if conn.execute('SELECT COUNT(*) FROM config_keepalive').fetchone()[0] > 0:
        return
    ativo, intervalo, origem = 1, 60, 'padrao'
    caminho = os.path.join(dir_base(), 'keepalive.json')
    if os.path.exists(caminho):
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                d = json.load(f)
            ativo = 1 if d.get('ativo', True) else 0
            intervalo = int(d.get('intervalo', 60) or 60)
            origem = 'keepalive.json (migrado e apagado)'
            os.remove(caminho)
        except Exception as e:
            origem = f'padrao (keepalive.json ilegivel: {e})'
    conn.executemany('INSERT INTO config_keepalive (alvo, ativo, intervalo) VALUES (?, ?, ?)',
                     [(alvo, ativo, intervalo) for alvo in KEEPALIVE_ALVOS])
    log_msg(f'KEEPALIVE: preferencia gravada no banco a partir do {origem} '
            f'(ativo={bool(ativo)}, intervalo={intervalo}s)')


def ler_keepalive(alvo='sei'):
    """Le a preferencia de keep-alive (ativo/intervalo) do banco."""
    if alvo not in KEEPALIVE_ALVOS:
        alvo = 'sei'
    try:
        conn = get_db()
        row = conn.execute('SELECT ativo, intervalo FROM config_keepalive WHERE alvo = ?',
                           (alvo,)).fetchone()
        conn.close()
        if row:
            return {'ativo': bool(row['ativo']), 'intervalo': int(row['intervalo'] or 60)}
    except Exception as e:
        log_msg(f'KEEPALIVE: erro ao ler config do banco: {e}')
    return dict(KEEPALIVE_PADRAO)


def salvar_keepalive(alvo='sei', ativo=None, intervalo=None):
    """Grava a preferencia de keep-alive no banco. Retorna a config final."""
    if alvo not in KEEPALIVE_ALVOS:
        alvo = 'sei'
    cfg = ler_keepalive(alvo)
    if ativo is not None:
        cfg['ativo'] = bool(ativo)
    if intervalo:
        cfg['intervalo'] = max(15, int(intervalo))
    try:
        conn = get_db()
        conn.execute('INSERT OR REPLACE INTO config_keepalive (alvo, ativo, intervalo) VALUES (?, ?, ?)',
                     (alvo, 1 if cfg['ativo'] else 0, cfg['intervalo']))
        conn.commit()
        conn.close()
        return cfg
    except Exception as e:
        log_msg(f'KEEPALIVE: erro ao gravar config no banco: {e}')
        return None


DEFAULT_CONFIG_GERACAO = {
    'tipo_processo': '100000508',  # Finalistico: Desenvolvimento de Assentamentos
    'especificacao': '{{Nome Titular 1}}',
    'interessados': '{{Nome Titular 1}}',
    'observacoes': '',
    'nivel_acesso': '1',
    'hipotese_legal': '4'
}


def log_msg(msg):
    """Registra no log do app quando ha handlers; caso contrario imprime.

    Os handlers ficam no logger RAIZ (logging.basicConfig), entao checar
    apenas o logger 'anexador' escondia as mensagens do SEI/gerar/baixar
    do arquivo de log (no .exe elas iam so para o console).
    """
    lg = logging.getLogger('anexador')
    if lg.handlers or logging.getLogger().handlers:
        lg.info(msg)
    else:
        print(msg)


def _normalizar_coringa(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', s or '')
    s = s.encode('ascii', 'ignore').decode('ascii')
    s = s.lower().strip()
    s = s.replace('_', ' ').replace('-', ' ')
    s = re.sub(r'\s+', ' ', s)
    return s


def _tem_valor(v):
    return v is not None and str(v).strip() != ''


# Apelidos amigaveis: chave normalizada -> campos (primeiro com valor vence).
# Cobre as duas tabelas: cod_sipra (aba Anexar) e cod_beneficiario (aba Gerar).
ALIASES_CORINGA = {
    'codigo sipra': ('cod_sipra', 'cod_beneficiario'),
    'cod sipra': ('cod_sipra', 'cod_beneficiario'),
    'codsipra': ('cod_sipra', 'cod_beneficiario'),
    'codigo beneficiario': ('cod_sipra', 'cod_beneficiario'),
    'codigo do beneficiario': ('cod_sipra', 'cod_beneficiario'),
    'cod beneficiario': ('cod_sipra', 'cod_beneficiario'),
    'nome titular 1': ('nome',),
    'nome titular': ('nome',),
    'nome beneficiario': ('nome',),
    'nome': ('nome',),
    'beneficiario': ('nome',),
    'titular': ('nome',),
    'titular 1': ('nome',),
    'n processo sei': ('processo_sei',),
    'no processo sei': ('processo_sei',),
    'numero processo sei': ('processo_sei',),
    'processo sei': ('processo_sei',),
    'processo': ('processo_sei',),
    'nup': ('processo_sei',),
    'nup processo': ('processo_sei',),
    'processo_sei': ('processo_sei',),
    'pdf anexo': ('pdf_anexo',),
    'pdf': ('pdf_anexo',),
    'arquivo': ('pdf_anexo',),
    'pdf_anexo': ('pdf_anexo',),
    'tipo documento': ('tipo_documento_nome', 'tipo_documento'),
    'tipo do documento': ('tipo_documento_nome', 'tipo_documento'),
    'tipo': ('tipo_documento_nome', 'tipo_documento'),
    'serie': ('tipo_documento', 'tipo_documento_nome'),
    'tipo_documento': ('tipo_documento',),
    'tipo_documento_nome': ('tipo_documento_nome',),
    'hipotese legal': ('hipotese_legal_nome', 'hipotese_legal'),
    'hipotese': ('hipotese_legal_nome', 'hipotese_legal'),
    'hipotese_legal': ('hipotese_legal',),
    'hipotese_legal_nome': ('hipotese_legal_nome',),
    'nivel acesso': ('nivel_acesso',),
    'nivel de acesso': ('nivel_acesso',),
    'nivel': ('nivel_acesso',),
    'nivel_acesso': ('nivel_acesso',),
    'data anexo': ('data_anexo',),
    'data_anexo': ('data_anexo',),
    'data geracao': ('data_geracao',),
    'data download': ('data_download',),
}


def fonte_coringas(registro=None, dados_csv=None):
    """Monta {chave normalizada: valor} para resolver os coringas {{...}}.

    Tres fontes, nesta ordem de precedencia:
      1. colunas da propria tabela do registro (cod_sipra/cod_beneficiario,
         nome, processo_sei, pdf_anexo, ...);
      2. colunas do CSV (guardadas na coluna dados_csv como JSON) - so
         preenchem chaves que a tabela nao tem;
      3. apelidos amigaveis ({{Código SIPRA}}, {{Nome Titular 1}}, {{NUP}},
         {{Serie}}, ...).

    Args:
        registro: dict/sqlite.Row do banco (pode trazer dados_csv), ou
            string legada contendo apenas o cod_sipra.
        dados_csv: dict ou JSON das colunas do CSV (opcional; quando nao vem
            no registro, e lido do proprio registro).
    """
    campos = {}
    if isinstance(registro, str):
        campos = {'cod_sipra': registro}
    elif registro is not None:
        try:
            campos = dict(registro)
        except Exception:
            campos = {'cod_sipra': str(registro)}

    bruto = dados_csv if dados_csv is not None else campos.get('dados_csv')
    if isinstance(bruto, dict):
        colunas = bruto
    elif isinstance(bruto, str) and bruto.strip():
        try:
            colunas = json.loads(bruto)
        except Exception:
            colunas = {}
    else:
        colunas = {}
    if not isinstance(colunas, dict):
        colunas = {}

    mapa = {}
    for chave, valor in campos.items():
        if chave == 'dados_csv':
            continue
        norm = _normalizar_coringa(str(chave))
        if norm:
            mapa[norm] = valor
    for chave, valor in colunas.items():
        norm = _normalizar_coringa(str(chave))
        if norm and norm not in mapa:
            mapa[norm] = valor
    for apelido, alvos in ALIASES_CORINGA.items():
        if _tem_valor(mapa.get(apelido)):
            continue
        for alvo in alvos:
            if _tem_valor(campos.get(alvo)):
                mapa[apelido] = campos[alvo]
                break
    return mapa


def buscar_coringa(chave_norm, mapa):
    """Valor nao-vazio da chave normalizada ('' quando nao ha).

    Primeiro a busca exata; se nada casar, a difusa: a chave como trecho do
    nome da coluna e depois por subconjunto de tokens (regra que a aba Gerar
    ja usava: "{{Nome Titular}}" acha a coluna "NOME TITULAR 1"). A coluna
    so vence quando tem valor: coringa com dado vazio cai na proxima fonte.
    """
    if not chave_norm:
        return ''
    valor = mapa.get(chave_norm)
    if _tem_valor(valor):
        return valor
    for k, v in mapa.items():
        if _tem_valor(v) and chave_norm in k:
            return v
    alvo = set(chave_norm.split())
    if alvo:
        for k, v in mapa.items():
            if _tem_valor(v) and alvo.issubset(set(k.split())):
                return v
    return ''


def processar_nome_arvore_template(template_str, registro=None, dados_csv=None):
    """Mesla campos coringas {{...}} com valores do registro.

    Aceita colunas da propria tabela (cod_sipra, nome, processo_sei,
    pdf_anexo, ...), colunas do CSV (dados_csv) e apelidos
    ({{Código SIPRA}}, {{Nome Titular 1}}, {{NUP}}, ...).

    Exemplo: "TD {{Código SIPRA}} - Lote {{Lote}}" ->
             "TD SC0123 - Lote 12"

    Coringa sem valor no registro fica visivel no texto (em vez de virar
    string vazia), assim a coluna "Nome na Arvore" nunca some e o problema
    (falta de CSV, por exemplo) aparece na cara.

    Args:
        template_str: texto com zero ou N coringas entre {{ }}.
        registro: dict/sqlite.Row com os campos do banco (pode trazer
            dados_csv), ou string legada contendo apenas o cod_sipra.
        dados_csv: dict ou JSON das colunas do CSV (opcional).
    """
    if not template_str:
        return template_str

    mapa = fonte_coringas(registro, dados_csv)

    def _substituir(match):
        valor = buscar_coringa(_normalizar_coringa(match.group(1)), mapa)
        if not _tem_valor(valor):
            # Sem dado no registro: mantem o coringa em vez de apagar.
            return match.group(0)
        return str(valor)

    return re.sub(r'\{\{\s*(.*?)\s*\}\}', _substituir, template_str)
