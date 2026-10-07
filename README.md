# Gerador SEI

Sistema automatizado de **geração de processos**, **anexação de documentos** e **downloads de espelhos** no **SEI** e na **PGT** do INCRA, com interface web local (Flask) e automação web via Playwright.

---

## Visão Geral

O Gerador SEI recebe uma planilha CSV com os dados dos beneficiários e:

1. **Gera** o processo de cada beneficiário no SEI (aba **Gerar**);
2. **Baixa** o Espelho da Unidade Familiar de cada um na PGT (aba **Baixar**);
3. **Anexa** os PDFs de cada um ao respectivo processo SEI (aba **Anexar**).

Tudo é controlado por um único painel em `http://localhost:5000`, com barra de progresso, passo atual, pausa/cancelamento e log unificado por aba.

---

## Funcionalidades Principais

- **Upload de CSV**: importa a planilha (código SIPRA e nome) — **reimportar faz merge** (mantém PDF, status e registros fora do CSV); o NUP não vem do CSV, é gravado em `processos_sei.processo_sei` pela geração
- **Upload de PDFs**: carga em lote com associação automática pelo código SIPRA no nome do arquivo (**padrão duas letras + dígitos**: `AB001200000001`); o upload reporta `associados / novos / ignorados`
- **Geração de Processos**: CSV → processo novo no SEI, com captura do NUP gerado e exportação de relatório consolidado
- **Downloads da PGT**: baixa o Espelho da Unidade Familiar de cada beneficiário para `Downloads/arquivos_pgt` (pasta criada automaticamente), **reutilizando a aba da PGT já aberta e logada**
- **Anexação Automatizada**: navegação e preenchimento de formulários no SEI via Playwright
- **Painel de Controle**: interface em **abas (Gerar | Baixar | Anexar | Log)** com barra de progresso por aba, **passo atual** e **caixa dos últimos erros** em tempo real
- **Fila de anexação**: usa o NUP gravado em `processos_sei.processo_sei` (gerado na aba Gerar); registro sem NUP fica de fora da fila até a geração
- **Configuração flexível**: tipo de documento, hipótese legal e nível de acesso — **Salvar Configurações** grava em `config_anexo` e aplica em massa nos registros (campo em branco mantém o valor que o registro já tinha)
- **Tratamento de erros**: pausa/cancelamento de cada execução (a pausa segura o robô **no passo atual**), retry dos registros que falharam e **sessão expirada aborta a execução**
- **Keep-alive de SEI e PGT**: dois controles independentes no rodapé (ativar/desativar, intervalo e *Recarregar agora*) que mantêm as sessões vivas — a preferência fica gravada na tabela `config_keepalive` (banco SQLite, não em arquivo JSON)
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

> Os espelhos da PGT vão para `Downloads/arquivos_pgt` (pasta do Windows,
> criada no início de cada execução) — fora do projeto de propósito.

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

> **O aplicativo inicia o Chrome debug sozinho**: ao rodar (`GeradorSEI.exe` ou
> `python app.py`) ele verifica a **porta 9222** numa thread separada e, se o
> Chrome nao estiver em modo debug, abre o Chrome com
> `--remote-debugging-port=9222` e o perfil `C:\ChromeDebug` (mesmo comando
> acima). O login no SEI (https://sei.incra.gov.br) é feito nesse Chrome; se a
> porta ja responder, nada e reaberto.

### 4. Iniciar o servidor

```bash
iniciar.bat
# ou
python app.py
```

O painel fica disponível em **http://localhost:5000**.

> **Abas abertas na subida do app** (nesta ordem, no Chrome debug):
> **1. dashboard (painel) → 2. SEI → 3. PGT**. Aba que já existe não é
> duplicada; sem Chrome debug, só o dashboard cai no navegador padrão.
> `GERADOR_SEI_SEM_ABA=1` não abre nenhuma aba.

> `iniciar.bat` roda o `check.py`, **encerra qualquer servidor antigo que ocupe a
> porta 5000** e só então sobe o novo processo — assim o HTML editado é sempre o
> que aparece no navegador (o servidor também roda com `TEMPLATES_AUTO_RELOAD`).

---

## Uso

### Aba Gerar — processos

1. Carregue o CSV da aba **Gerar** (código e nome; a coluna de nº do processo é ignorada)
2. Escolha o **Tipo de Processo**, a especificação, interessados e nível de acesso
3. Clique em **Iniciar geração**: a barra mostra o % e, abaixo, `gerando X de Y`;
   o botão vira **Pausar**/**Continuar** e o **Cancelar** ao lado encerra a
   execução mantendo todos os registros da fila
4. **Exportar** gera `relatorio_gerador_sei.csv` com as colunas originais do CSV
   mais status/erros de geração, download e anexo, NUP gerado, arquivo baixado e
   datas (separador `;`, UTF-8 com BOM)

### Aba Baixar — espelhos da PGT

1. Os códigos dos beneficiários vêm do CSV carregado na aba Gerar
2. Faça login em https://pgt.incra.gov.br **na aba da PGT aberta no Chrome debug**
3. Clique em **Baixar**: a barra mostra `baixando X de Y`
4. O robô **reutiliza essa mesma aba da PGT** (não abre outra); se a sessão
   expirou, ele **aborta antes de clicar** em *Baixar relatório* — refaça o login
   e clique em Baixar de novo
5. **Cancelar** interrompe e **zera o progresso** (os registros ficam na fila);
   **Executar novamente (erros)** recoloca na fila os downloads com falha
6. Os arquivos vão para `Downloads/arquivos_pgt` com o nome original sugerido pela
   PGT (ex.: `unidade-familiar-AB001200000001.pdf`); arquivo já existente é
   **sobrescrito** — o nome nunca ganha sufixo

### Aba Anexar — documentos no SEI

1. Abra **"Configurações do Anexo SEI"** e confira os parâmetros:

   | Campo | Descrição | Valor padrão |
   |-------|-----------|--------------|
   | Tipo do Documento | Série do SEI (Anexo, Relatório, etc.) | Anexo (263) |
   | Nome na Árvore | Nome exibido na árvore; aceita coringas `{{Código SIPRA}}`, `{{Nome Titular 1}}` e **colunas do CSV** (ex.: `{{Lote}}`) | Espelho SIPRA |
   | Hipótese Legal | Fundamentação legal do acesso (só quando o nível **não** é Público) | Informação Pessoal (Art. 31 da Lei nº 12.527/2011) |
   | Nível de Acesso | Público, Restrito ou Sigiloso | Restrito |

   **Salvar Configurações** grava os parâmetros em `config_anexo` e atualiza em
   massa os campos `tipo_documento`, `nome_arvore`, `nivel_acesso` e
   `hipotese_legal` de todos os registros; um campo deixado em branco **não
   apaga** o valor que o registro já tinha.

   **Coringas `{{...}}`** — valem nos campos *Especificação* e *Nome na Árvore*,
   na aba Anexar:

   | Origem | Exemplos |
   |--------|----------|
   | Campos da tabela | `{{Código SIPRA}}`, `{{Nome}}`, `{{Processo SEI}}`, `{{NUP}}`, `{{PDF Anexo}}`, `{{Nível de Acesso}}` |
   | Apelidos de titulares | `{{Nome Titular 1}}`, `{{Nome Titular 2}}` |
   | **Colunas do CSV carregado** | `{{Lote}}`, `{{Data Tabela}}`, `{{NO PROCESSO SEI}}` — qualquer cabeçalho, sem depender de mapeamento |

   A busca ignora maiúsculas/acentos e casa por fragmento (`{{Nome Titular}}`
   acha `NOME TITULAR 1`). Coringa sem dado fica visível no nome (ex.:
   `{{Lote}}`); na geração do documento, um segmento vazio — ex.
   `{{Nome Titular 1}} - {{Nome Titular 2}}` com só um titular — é
   removido junto com o separador.

2. **1. Carregar CSV** — colunas `CÓDIGO DO BENEFICIÁRIO`, `PROC SEI`,
   `BENEFICIÁRIO` (delimitador `;`, encoding UTF-8 ou CP1252)
3. **2. Carregar Anexos PDF** — selecione a **pasta** com os PDFs; a associação é
   feita por **expressão regular** comparando o código do CSV com o nome do
   arquivo. O código segue o padrão **duas letras + dígitos** (`AB001200000001`),
   então `unidade-familiar-AB001200000001.pdf`, `AB001200000001 - NOME.pdf` e
   `AB 001200000001.pdf` caem todos no mesmo registro. O nome do PDF associado
   aparece na aba **Anexar**, coluna **PDF Anexo**
4. Faça login no SEI e clique em **Anexar no SEI**, acompanhando o progresso;
   no sucesso a linha vira **Anexado** e a coluna **Data Anexo** recebe a
   data/hora (`AAAA-MM-DD HH:MM:SS`) — em falha, nova tentativa ou PDF
   substituído, a data é zerada
5. **Limpar registros** zera a tabela sem apagar os PDFs já enviados

### Keep-alive (rodapé — SEI e PGT)

O rodapé tem **duas linhas independentes**, uma para o **SEI** e outra para o
**PGT**, cada uma com:

| Controle | O que faz |
|----------|-----------|
| **Ativar / Desativar** | liga ou desliga só aquele keep-alive |
| **a cada N s** | intervalo da recarga (mínimo 15 s) |
| **Recarregar agora** | recarrega a aba na hora (mesmo com o keep-alive desligado) |

Regras de recarga:

- só roda com o app **ocioso** (nenhuma fila de gerar/baixar/anexar em execução);
- recarrega a aba **já aberta** no Chrome debug; se não existir, cria uma única
  vez e reutiliza nas próximas;
- sessão expirada (redirecionou para login / acesso não autorizado) é reportada
  no rodapé e no log — refaça o login manualmente;
- o estado é **gravado no banco** (`config_keepalive`) e sobrevive a reinícios;
  o antigo `keepalive.json` é migrado na primeira execução e apagado.

---

## Processo de Anexação (16 passos)

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
| 11 | Hipótese Legal | Aguarda o carregamento via AJAX (ignorado em nível Público) |
| 12 | Hipótese Legal | Seleciona a hipótese legal (ignorado em nível Público) |
| 13 | Anexar PDF | Faz upload do arquivo PDF |
| 14 | Salvar | Clica no botão Salvar |
| 15 | Verificar | Verifica `.infraMensagemErro`/sucesso do SEI (erro reprova o item) |
| 16 | Confirmar | Pressiona Enter para confirmar |

---

## Banco de Dados

Relação principal (chave estrangeira real, `PRAGMA foreign_keys = ON`):

```
processos_sei (1)  <──────────  (N)  anexos_sei
             cod_beneficiario          cod_sipra
```

Tabela `processos_sei` (antes `processos_gerados`; a coluna `processo_gerado`
virou `processo_sei` e `processo_sei_original`, o NUP do CSV, foi removida):

| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | INTEGER | Chave primária (autoincremento) |
| cod_beneficiario | TEXT | Código SIPRA (índice único; é a chave do 1:N com `anexos_sei`) |
| nome | TEXT | Nome do beneficiário (vem do CSV; é o que a aba Anexar exibe) |
| dados_csv | TEXT | Linha do CSV em JSON (alimenta os templates da geração) |
| processo_sei | TEXT | NUP do processo (gerado na aba Gerar; é o NUP exibido na aba Anexar) |
| status | INTEGER | 0=pendente, 1=gerado, -1=erro; `NULL` = placeholder criado pela aba Anexar (fora da fila) |
| erro | TEXT | Mensagem da falha de geração |
| data_geracao | TEXT | Data/hora da geração |
| download | INTEGER | Estado do download na aba Baixar: 0=pendente, 1=baixado, -1=erro |
| erro_download | TEXT | Mensagem da falha de download |
| arquivo_download | TEXT | Arquivo baixado |
| data_download | TEXT | Data/hora do download |

Tabela `anexos_sei` — um registro por anexo; `nome` e `processo_sei` foram
removidos daqui (vem do processo pai via JOIN):

| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | INTEGER | Chave primária (autoincremento) |
| cod_sipra | TEXT | Código SIPRA — **FK** para `processos_sei.cod_beneficiario` |
| pdf_anexo | TEXT | Nome do arquivo PDF associado (vem da aba Anexar) |
| anexado | INTEGER | Status: 0=pendente, 1=anexado, -1=erro |
| tipo_documento | INTEGER | Série do SEI gravada pela configuração |
| nome_arvore | TEXT | Nome na árvore (template com coringas já processado) |
| nivel_acesso | INTEGER | 0=Público, 1=Restrito, 2=Sigiloso |
| hipotese_legal | INTEGER | Código da hipótese legal |
| data_anexo | TEXT | Data/hora da anexação |

Bancos antigos são migrados sozinhos na inicialização (`init_db`):
`processos_gerados` vira `processos_sei`, `anexos_sei` é recriado com a FK e
anexos sem processo pai ganham um processo criado a partir da linha antiga.

Há também:

- `config_anexo` — configuração da aba Anexar (`serie`, `nome_arvore`,
  `hipotese`, `nivel`), regravada a cada *Salvar Configurações*
- `config_geracao` — configurações da aba Gerar
- `config_keepalive` — preferência do keep-alive por alvo (`sei`, `pgt`), com
  `ativo` e `intervalo`; substitui o antigo `keepalive.json`
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
| GET/POST | `/api/keepalive` | Estado dos keep-alives (GET: `sei` e `pgt`); POST grava `ativo`/`intervalo` ou recarrega na hora (`agora`) para o alvo `alvo=sei\|pgt` |

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
| PDF não associa | O nome do arquivo precisa conter o código do CSV no padrão **2 letras + dígitos** (`AB001200000001`), com ou sem separadores |
| Configuração não salva | Abra as Configurações do Anexo pela própria aba Anexar e clique em **Salvar Configurações**; veja o log em `processos_sei.log` |
| Download não começa | Sessão expirada na PGT aborta de propósito; refaça o login na aba da PGT |
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

## Suporte

Desenvolvido por **Roberto Simões**

| Canal | Contato |
|-------|---------|
| E-mail | robsimoes@gmail.com |
| WhatsApp | +55 (48) 99679-3828 |
| LinkedIn | linkedin.com/in/robertosim |

Desenvolvido para uso interno do **INCRA** — Instituto Nacional de Colonização e Reforma Agrária.
