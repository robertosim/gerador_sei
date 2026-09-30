import logging
import sqlite3
import os

from tipos_processo import TIPOS_PROCESSO

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'processos_sei.db')

DEFAULT_CONFIG = {
    'serie': '82',
    'sigilo': 'R',
    'nome_arvore': 'CCIR',
    'hipotese': '4',
    'nivel': '1'
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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


def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS anexos_sei (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cod_sipra TEXT NOT NULL,
        nome TEXT,
        processo_sei TEXT,
        pdf_anexo TEXT,
        anexado INTEGER DEFAULT 0,
        tipo_documento INTEGER,
        nome_arvore TEXT,
        nivel_acesso INTEGER DEFAULT 1,
        hipotese_legal INTEGER,
        data_anexo TEXT
    )''')
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
    conn.execute('''CREATE TABLE IF NOT EXISTS processos_gerados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cod_beneficiario TEXT NOT NULL,
        nome TEXT,
        processo_sei_original TEXT,
        dados_csv TEXT,
        processo_gerado TEXT,
        status INTEGER DEFAULT 0,
        erro TEXT,
        data_geracao TEXT
    )''')
    # Estado dos espelhos baixados na aba Baixar (mesmos campos da extensao)
    for ddl in (
        "ALTER TABLE processos_gerados ADD COLUMN download INTEGER DEFAULT 0",
        "ALTER TABLE processos_gerados ADD COLUMN erro_download TEXT",
        "ALTER TABLE processos_gerados ADD COLUMN arquivo_download TEXT",
        "ALTER TABLE processos_gerados ADD COLUMN data_download TEXT",
    ):
        try:
            conn.execute(ddl)
        except Exception:
            pass
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
    conn.commit()
    conn.close()


DEFAULT_CONFIG_GERACAO = {
    'tipo_processo': '100000508',  # Finalistico: Desenvolvimento de Assentamentos
    'especificacao': '{{Nome Titular 1}}',
    'interessados': '{{Nome Titular 1}}',
    'observacoes': '',
    'nivel_acesso': '1',
    'hipotese_legal': '4'
}


def log_msg(msg):
    """Registra no log do app quando ha handlers; caso contrario imprime."""
    lg = logging.getLogger('anexador')
    if lg.handlers:
        lg.info(msg)
    else:
        print(msg)
