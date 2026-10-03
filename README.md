# Gerador SEI

Sistema automatizado de **geração de processos**, **anexação de documentos** e **downloads de espelhos** no **SEI** e no **PGT** do INCRA, com interface web local (Flask) e automação web via Playwright.

---

## Visão Geral

O Gerador SEI recebe uma planilha CSV com os dados dos beneficiários e:

1. **Gera** o processo de cada beneficiário no SEI (aba **Gerar**);
2. **Baixa** o Espelho da Unidade Familiar de cada um no PGT (aba **Baixar**);
3. **Anexa** os PDFs de cada um ao respectivo processo SEI (aba **Anexar**).

Tudo é controlado por um único painel em `http://localhost:5000`, com barra de progresso, passo atual, pausa/cancelamento e log unificado por aba.

---

## Funcionalidades Principais

- **Upload de CSV**: importa a planilha (código SIPRA, nome, nº do processo) — **reimportar faz merge** (mantém PDF, status e registros fora do CSV)
- **Upload de PDFs**: carga em lote com associação automática pelo código SIPRA no nome do arquivo (**padrão duas letras + dígitos**: `MS001200000001`); o upload reporta `associados / novos / ignorados`
- **Geração de Processos**: CSV → processo novo no SEI, com captura do NUP gerado e exportação de relatório consolidado
- **Downloads do PGT**: baixa o Espelho da Unidade Familiar de cada beneficiário para `Downloads/arquivos_pgt` (pasta criada automaticamente), **reutilizando a aba do PGT já aberta e logada**
- **Anexação Automatizada**: navegação e preenchimento de formulários no SEI via Playwright
- **Painel de Controle**: interface em **abas (Gerar | Baixar | Anexar | Log)** com barra de progresso por aba, **passo atual** e **caixa dos últimos erros** em tempo real
- **Fila inteligente de anexação**: usa o processo do CSV ou, na falta, o **NUP gerado** na aba Gerar
- **Configuração flexível**: tipo de documento, grau de sigilo (`R=Reservado`, `U=Urgente`, `S=Sigiloso`), hipótese legal e nível de acesso — **Salvar Configurações** grava em `config_anexo` e aplica em massa nos registros (campo em branco mantém o valor que o registro já tinha)
- **Tratamento de erros**: pausa/cancelamento de cada execução (a pausa segura o robô **no passo atual**), retry dos registros que falharam e **sessão expirada aborta a execução**
- **Keep-alive**: recarrega a aba do SEI em intervalo configurável para manter a sessão viva
- **Limpeza por aba**: *Limpar registros* (anexar), *Limpar Tudo* (gerar) e *Limpar log*
- **Log detalhado**: log unificado de todas as operações (arquivo + aba Log)

---

## Estrutura do Projeto

```
gerador_sei/
├── app.py                  # Servidor Flask (API REST + interface web)
├── sei.py                  # Automação SEI/PGT (Playwright) — passos, pausa, sessão
├── database.py             # Camada de acesso ao banco SQLite
├── tipos_processo.py       # Tabela de tipos de processo do SEI
├── check.py                # Verificação/instalação de dependências
├── requirements.txt        # Dependências Python
├── iniciar.bat             # Verifica dependências, mata a porta 5000 e inicia o app
├── README.md               # Este arquivo
├── templates/
│   └── index.html          # Interface web (abas do painel)
├── static/css/
│   └── sei-style.css       # Estilo do painel (abas, progresso, tabelas)
├── uploads/                # PDFs enviados pelo usuário        [não versionado]
├── csv/                    # Planilhas CSV de entrada          [não versionado]
├── processos_sei.db         # Banco SQLite (gerado em execução) [não versionado]
└── processos_sei.log        # Log (gerado em execução)          [não versionado]
```

> Os espelhos do PGT vão para `Downloads/arquivos_pgt` (pasta do Windows,
> criada no início de cada execução) — fora do projeto de propósito.

> **Fora deste repositório** (mantidos apenas na máquina de desenvolvimento, já que
> não sobem para o GitHub): a pasta irmã `../Extensão Gerador SEI/`, que guarda a
> extensão Chrome (`extensao_gerador_sei/`) e os testes automatizados
> (`testes_extensao/`), além de tudo o que o `.gitignore` exclui (dados, banco,
> logs e estado de execução).

---

## Pré-requisitos

- Python 3.10 ou superior
- Google Chrome instalado
- Sistema operacional Windows

---

## Instalação

### 1. Clonar o repositório

```bash
git clone https://github.com/robertosim/gerador_sei.git
cd gerador_sei
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Iniciar o Chrome em modo Remote Debugging

```bash
chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\ChromeDebug"
```

> **Importante**: o Chrome deve estar aberto em modo debug **antes** de iniciar o
> aplicativo, e é nele que você faz login no SEI (https://sei.incra.gov.br).

### 4. Iniciar o servidor

```bash
iniciar.bat
# ou
python app.py
```

O painel fica disponível em **http://localhost:5000**.

> `iniciar.bat` roda o `check.py`, **encerra qualquer servidor antigo que ocupe a
> porta 5000** e só então sobe o novo processo — assim o HTML editado é sempre o
> que aparece no navegador (o servidor também roda com `TEMPLATES_AUTO_RELOAD`).

---

## Uso

### Aba Gerar — processos

1. Carregue o CSV da aba **Gerar** (código, nome e nº do processo)
2. Escolha o **Tipo de Processo**, a especificação, interessados e nível de acesso
3. Clique em **Iniciar geração**: a barra mostra o % e, abaixo, `gerando X de Y`;
   o botão vira **Pausar**/**Continuar** e o **Cancelar** ao lado encerra a
   execução mantendo todos os registros da fila
4. **Exportar** gera `relatorio_gerador_sei.csv` com as colunas originais do CSV
   mais status/erros de geração, download e anexo, NUP gerado, arquivo baixado e
   datas (separador `;`, UTF-8 com BOM)

### Aba Baixar — espelhos do PGT

1. Os códigos dos beneficiários vêm do CSV carregado na aba Gerar
2. Faça login em https://pgt.incra.gov.br **na aba do PGT aberta no Chrome debug**
3. Clique em **Baixar**: a barra mostra `baixando X de Y`
4. O robô **reutiliza essa mesma aba do PGT** (não abre outra); se a sessão
   expirou, ele **aborta antes de clicar** em *Baixar relatório* — refaça o login
   e clique em Baixar de novo
5. **Cancelar** interrompe e **zera o progresso** (os registros ficam na fila);
   **Executar novamente (erros)** recoloca na fila os downloads com falha
6. Os arquivos vão para `Downloads/arquivos_pgt` com o nome original sugerido pelo
   PGT (ex.: `unidade-familiar-MS001200000001.pdf`); arquivo repetido ganha o
   sufixo `_<código>`

### Aba Anexar — documentos no SEI

1. Abra **"Configurações do Anexo SEI"** e confira os parâmetros:

   | Campo | Descrição | Valor padrão |
   |-------|-----------|--------------|
   | Tipo do Documento | Série do SEI (Anexo, Relatório, etc.) | Anexo (263) |
   | Nome na Árvore | Nome exibido na árvore; aceita coringas `{{Código SIPRA}}`, `{{Nome Titular 1}}`… | Espelho SIPRA |
   | Grau de Sigilo | Reservado, Urgente ou Sigiloso | Reservado |
   | Hipótese Legal | Fundamentação legal do acesso | Informação Pessoal (Art. 31 da Lei nº 12.527/2011) |
   | Nível de Acesso | Público, Restrito ou Sigiloso | Restrito |

   **Salvar Configurações** grava os parâmetros em `config_anexo` e atualiza em
   massa os campos `tipo_documento`, `nome_arvore`, `nivel_acesso` e
   `hipotese_legal` de todos os registros; um campo deixado em branco **não
   apaga** o valor que o registro já tinha.

2. **1. Carregar CSV** — colunas `CÓDIGO DO BENEFICIÁRIO`, `PROC SEI`,
   `BENEFICIÁRIO` (delimitador `;`, encoding UTF-8 ou CP1252)
3. **2. Carregar Anexos PDF** — selecione a **pasta** com os PDFs; a associação é
   feita por **expressão regular** comparando o código do CSV com o nome do
   arquivo. O código segue o padrão **duas letras + dígitos** (`MS001200000001`),
   então `unidade-familiar-MS001200000001.pdf`, `MS001200000001 - NOME.pdf` e
   `MS 001200000001.pdf` caem todos no mesmo registro. O nome do PDF associado
   aparece na aba **Anexar**, coluna **PDF Anexo**
4. Faça login no SEI e clique em **Anexar no SEI**, acompanhando o progresso
5. **Limpar registros** zera a tabela sem apagar os PDFs já enviados

---

## Processo de Anexação (17 passos)

| Passo | Ação | Descrição |
|-------|------|-----------|
| 1 | Acessar SEI | Navega para https://sei.incra.gov.br/sei (sessão expirada aborta a execução) |
| 2 | Pesquisar processo | Busca o processo pelo número na pesquisa rápida |
| 3 | Encontrar frame | Localiza o frame do botão "Registrar Documento Externo" |
| 4 | Clicar incluir | Clica no botão de incluir documento |
| 5 | Encontrar formulário | Localiza o frame com o formulário de dados |
| 6 | Tipo do Documento | Seleciona a série (ex.: Anexo - 263) |
| 7 | Data de Elaboração | Preenche com a data atual |
| 8 | Nome na Árvore | Preenche o nome (ex.: Espelho SIPRA) |
| 9 | Formato | Seleciona "Nato-digital" |
| 10 | Nível de Acesso | Público / Restrito / Sigiloso |
| 11 | Hipótese Legal | Aguarda o carregamento via AJAX e seleciona |
| 12 | Grau de Sigilo | Define o grau de sigilo |
| 13 | Hipótese Legal | Confirma a seleção |
| 14 | Anexar PDF | Faz upload do arquivo PDF |
| 15 | Salvar | Clica no botão Salvar |
| 16 | Verificar | Verifica `.infraMensagemErro`/sucesso do SEI (erro reprova o item) |
| 17 | Confirmar | Pressiona Enter para confirmar |

---

## Banco de Dados

Tabela `anexos_sei` (SQLite):

| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | INTEGER | Chave primária (autoincremento) |
| cod_sipra | TEXT | Código SIPRA do beneficiário (padrão 2 letras + dígitos) |
| nome | TEXT | Nome do beneficiário |
| processo_sei | TEXT | Número do processo SEI |
| pdf_anexo | TEXT | Nome do arquivo PDF associado (vem da aba Anexar) |
| anexado | INTEGER | Status: 0=pendente, 1=anexado, -1=erro |
| tipo_documento | INTEGER | Série do SEI gravada pela configuração |
| nome_arvore | TEXT | Nome na árvore (template com coringas já processado) |
| nivel_acesso | INTEGER | 0=Público, 1=Restrito, 2=Sigiloso |
| hipotese_legal | INTEGER | Código da hipótese legal |
| data_anexo | TEXT | Data/hora da anexação |

Há também:

- `config_anexo` — configuração da aba Anexar (`serie`, `sigilo`, `nome_arvore`,
  `hipotese`, `nivel`), regravada a cada *Salvar Configurações*
- `processos_gerados` — fila de geração da aba Gerar, com o estado dos downloads
  (`download`, `erro_download`, `arquivo_download`, `data_download`)
- `config_geracao` — configurações da aba Gerar
- `tipo_documento` e `hipotese_legal` — tabelas de apoio das séries e hipóteses

---

## API REST

### Geral

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/` | Interface web (abas Gerar / Baixar / Anexar / Log) |
| GET | `/api/stats` | Estatísticas gerais |
| GET/POST | `/api/config` | Obtém / salva configurações de anexo |
| GET/POST | `/api/log` | Log unificado (GET) / limpa o log (POST) |
| GET/POST | `/api/keepalive` | Status / controle do keep-alive |

### Anexar

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/upload-csv` | Upload de planilha CSV (faz merge com a tabela) |
| POST | `/api/upload-pdfs` | Upload de PDFs |
| GET | `/api/registros` | Lista os registros |
| POST | `/api/limpar` | Limpa todos os registros |
| POST | `/api/atualizar-campo` | Edita um campo de um registro |
| POST | `/api/retry-falhas` | Reseta registros com erro para retry |
| GET | `/api/tipos-documento` | Sérias/documentos disponíveis |
| GET | `/api/hipoteses-legais` | Hipóteses legais disponíveis |
| GET | `/api/tipos-processo` | Tipos de processo disponíveis |
| POST | `/api/anexar` | Inicia a anexação (exige Chrome na porta 9222 e pendência) |
| POST | `/api/anexar/pausar` | Pausa / **retoma** a anexação (alterna) |
| POST | `/api/anexar/cancelar` | Cancela a anexação |
| GET | `/api/status` \| `/api/sei-status` | Status + passo atual da anexação |
| GET | `/api/sei-log` | Log da anexação |

### Gerar

| Método | Rota | Descrição |
|--------|------|-----------|
| GET/POST | `/api/gerar/config` | Obtém / salva configurações de geração |
| GET | `/api/gerar/csvs` | Lista os CSVs da pasta `csv/` |
| POST | `/api/gerar/carregar-csv` | Popula a fila a partir dos CSVs da pasta |
| POST | `/api/gerar/upload-csv` | Envia um CSV e popula a fila |
| POST | `/api/gerar/iniciar` | Inicia a geração |
| POST | `/api/gerar/pausar` | Pausa / **retoma** a geração (alterna) |
| POST | `/api/gerar/cancelar` | Cancela a geração |
| GET | `/api/gerar/status` | Status + passo atual da geração |
| GET | `/api/gerar/log` \| `/api/gerar/registros` | Log e fila de geração |
| GET | `/api/gerar/exportar` | Relatório CSV (`relatorio_gerador_sei.csv`) |
| POST | `/api/gerar/retry` \| `/api/gerar/limpar` | Repete falhas / limpa a fila |

### Baixar (PGT)

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/baixar/iniciar` | Inicia os downloads (exige Chrome na porta 9222) |
| POST | `/api/baixar/pausar` | Pausa / **retoma** os downloads (alterna) |
| POST | `/api/baixar/cancelar` | Cancela e **zera o progresso** (registros mantidos) |
| POST | `/api/baixar/retry` | Repete downloads com erro |
| GET | `/api/baixar/status` | Status + passo atual dos downloads |
| GET | `/api/baixar/log` | Log dos downloads |

---

## Logs

- **Console**: saída em tempo real no terminal
- **Arquivo**: `processos_sei.log` (rotação automática, 5 MB, 3 backups)
- **Interface**: aba **Log** com o log unificado (Gerar, Baixar e Anexar)
- **POST `/api/log`**: limpa o arquivo de log pelo painel (*Limpar log*)

---

## Solução de Problemas

| Problema | Solução |
|----------|---------|
| Chrome não conecta | Verifique se o Chrome está em modo debug (porta 9222) |
| Interface desatualizada | Use `iniciar.bat` (mata o servidor antigo da porta 5000) |
| CSV não carrega | Verifique o encoding (UTF-8 ou CP1252) e o delimitador (`;`) |
| PDF não associa | O nome do arquivo precisa conter o código do CSV no padrão **2 letras + dígitos** (`MS001200000001`), com ou sem separadores |
| Configuração não salva | Abra as Configurações do Anexo pela própria aba Anexar e clique em **Salvar Configurações**; veja o log em `processos_sei.log` |
| Download não começa | Sessão expirada no PGT aborta de propósito; refaça o login na aba do PGT |
| Onde ficam os espelhos | `C:\Users\<usuário>\Downloads\arquivos_pgt` (criada automaticamente ao iniciar o download) |
| Anexação falha no SEI | Verifique se está logado no SEI no Chrome debugado |
| Formulário não encontrado | O SEI pode ter alterado a estrutura de frames |
| Sessão expirada | A execução aborta de propósito; refaça o login e reinicie |

---

## Tecnologias

- **Backend**: Python 3 + Flask
- **Automação**: Playwright (Python)
- **Banco de dados**: SQLite
- **Frontend**: HTML5 + CSS3 + JavaScript vanilla
- **Navegador**: Google Chrome (modo Remote Debugging)

---

## Autor

Desenvolvido para uso interno do **INCRA** — Instituto Nacional de Colonização e Reforma Agrária.
