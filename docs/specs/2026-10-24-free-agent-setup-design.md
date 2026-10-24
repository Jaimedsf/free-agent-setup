# free-agent-setup — Design

Data: 2026-10-24
Status: rascunho para revisão

## 1. Objetivo

Um repositório público com um instalador de **um comando** que prepara um ambiente de agente de IA
para programação (Hermes Agent + oh-my-hermes) na máquina de quem o executa. O instalador analisa o
hardware e as ferramentas já presentes e monta a melhor combinação **gratuita** de modelos: um modelo
local que caiba inteiro na GPU, provedores de nuvem com plano grátis e assinaturas que a pessoa já
tenha. Provedores pagos por token ficam fora da configuração.

### Critérios de sucesso

- Uma linha (`irm … | iex` no Windows, `curl … | bash` no Linux) leva uma máquina limpa até um Hermes
  funcional, com o plugin OMH carregado e um modelo principal que responde.
- Só entram na configuração modelos que **responderam de verdade** a um teste na conta da pessoa.
- O modelo local, quando houver, roda 100% na GPU (confirmado pelo `ollama ps`).
- Rodar de novo é seguro (idempotente) e existe rollback.
- O repositório não contém dados pessoais, caminhos de uma máquina específica nem segredos, e não
  menciona nenhum fornecedor de modelo pago que ficou de fora.

### Fora do escopo (v1)

- macOS.
- Tornar o modelo local o modelo principal quando há nuvem disponível.
- Plataformas de mensagens do Hermes (Telegram, Discord…) e o gateway como serviço.
- Planos pagos (Ollama Pro, créditos NVIDIA pagos etc.).

## 2. Arquitetura

Abordagem: **bootstrap mínimo por SO + toda a lógica num pacote Python**.

```
free-agent-setup/
├── install.ps1              # bootstrap Windows (~40 linhas)
├── install.sh               # bootstrap Linux (~40 linhas)
├── pyproject.toml           # pacote "freeagent", executado via `uv run`
├── src/freeagent/
│   ├── __main__.py          # CLI e orquestração das etapas
│   ├── i18n/{en,pt}.json    # mensagens do instalador
│   ├── catalog.json         # faixas de VRAM -> modelo local; candidatos de nuvem
│   ├── detect.py            # hardware, SO, idioma, ferramentas instaladas
│   ├── plan.py              # decisão pura: (detecção, catálogo) -> Plano
│   ├── install.py           # Ollama, Hermes, OMH pelos instaladores oficiais
│   ├── auth.py              # logins/chaves via comandos dos próprios produtos
│   ├── probe.py             # testes reais de modelos (resposta, GPU %, tok/s)
│   ├── configure.py         # edição estruturada do config do Hermes e do routing OMH
│   ├── backup.py            # backup e rollback
│   ├── redact.py            # mascaramento de segredos em logs e relatório
│   └── report.py            # resumo no terminal + freeagent-report.md
├── tests/                   # pytest, com fixtures de saídas de comandos
├── docs/                    # specs, README.pt-BR.md, troubleshooting
└── .github/workflows/ci.yml # lint, testes, dry-run, varredura de dados pessoais
```

### Bootstrap (`install.ps1` / `install.sh`)

1. Garante o `uv` (instalador oficial do uv, sem admin) e as ferramentas mínimas (git).
2. Baixa o repositório numa pasta temporária, ou usa o diretório atual quando executado de um
   clone.
3. Executa `uv run --project <pasta> python -m freeagent <args>`, repassando os argumentos.

O bootstrap não tem lógica de decisão, para continuar curto e fácil de ler antes de rodar.

### Fluxo de etapas

Cada etapa é uma função que recebe o estado acumulado e devolve `ok | skipped | failed` com motivo.
A falha de uma etapa opcional não interrompe as outras. São fatais apenas: falta de Python/uv,
falta de internet e falha ao instalar o Hermes.

1. **detect**: SO; GPU (fabricante, VRAM total e livre via `nvidia-smi` ou `rocm-smi`; sem GPU
   suportada = só CPU); RAM; núcleos; disco livre; idioma do sistema; presença e versão de Hermes,
   OMH, Ollama, Codex CLI e outras CLIs de agente; logins existentes (por exemplo, o Codex logado).
2. **plan**: função pura que decide o modelo local, os provedores de nuvem a ativar, as assinaturas
   reaproveitadas e o executor de código do OMH. Não tem efeitos colaterais, o que facilita testar.
3. **confirm**: mostra o plano com o motivo de cada item e pede um único `s/N` (`--yes` pula).
4. **install**: instala só o que falta, pelos instaladores oficiais:
   - Ollama (winget ou instalador oficial no Windows; script oficial no Linux);
   - Hermes Agent, **sem executar o assistente interativo dele** (no Windows, `-SkipSetup`);
   - oh-my-hermes pelo instalador oficial em venv.
   Antes de rodar cada instalador, mostra a URL de origem.
5. **auth**: cada provedor é opcional; se a pessoa pular, ele fica fora.
   - NVIDIA build: abre a página da chave; recebe a chave com entrada oculta; grava via
     `hermes auth add nvidia --type api-key`.
   - Ollama Cloud: `ollama signin` (navegador).
   - Codex: reaproveita o login da CLI existente via `hermes auth add openai-codex --type oauth`,
     só se o Codex CLI estiver instalado.
6. **probe**: para cada candidato, envia um prompt curto ("Responda apenas: OK") com timeout:
   - descarta os que retornam 4xx (402 sem plano, 404 inexistente, 400 não suportado) ou estouram o
     tempo;
   - mede a latência;
   - para o modelo local, mede tok/s e o % de GPU no `ollama ps` (detalhes na seção 3).
7. **configure**: com backup prévio, grava a configuração (seção 4) e roda `hermes config check`;
   se a checagem falhar, restaura o backup automaticamente.
8. **report**: resumo no terminal e `freeagent-report.md` local, com o que foi feito, os modelos
   aprovados e rejeitados (com o motivo), como trocar de modelo e como fazer rollback.

### Resolução do HERMES_HOME

Depois de instalar ou detectar o Hermes, o instalador descobre o diretório real que o Hermes usa
(no Windows nativo, `%LOCALAPPDATA%\hermes`; no Linux, `~/.hermes`), confirmando com o próprio
Hermes. Em seguida define `HERMES_HOME` (persistente no Windows, no perfil do shell no Linux)
**antes** de rodar o `omh setup`, para o OMH se registrar no mesmo diretório.

## 3. Escolha de modelos

### Modelo local (Ollama)

Faixas do `catalog.json`, usando a VRAM livre:

| VRAM livre | Modelo | Download | Contexto alvo |
|---|---|---|---|
| < 4 GB ou sem GPU | nenhum | — | — |
| 4–6 GB | `bonsai-2:4b` | 1,6 GB | 32k |
| 6–10 GB | `bonsai-2:9b` | 3,2 GB | 64k |
| 10–16 GB | `bonsai-2:9b` | 3,2 GB | 128k |
| ≥ 16 GB | `bonsai-2:27b` | 8,3 GB | 64k |

Procedimento:

1. Baixa o modelo e cria a variante `freeagent-local` com `num_ctx` = contexto alvo.
2. Executa um prompt de teste e lê o `ollama ps`.
3. Se o modelo não estiver em 100% GPU, divide o contexto por 2 (mínimo 16k) e repete.
4. Se continuar abaixo de 100% com 16k, desce uma faixa. Sem faixa possível, fica sem modelo local.

O catálogo é versionado e pode ser atualizado sem mexer no código.

### Modelo principal

O primeiro candidato aprovado no teste, nesta ordem:

1. NVIDIA build: `nvidia/nemotron-3-ultra-550b-a55b` (com chave grátis);
2. Ollama Cloud: `nemotron-3-ultra:cloud` (com login grátis);
3. Codex: o primeiro modelo aceito pela conta, de uma lista ordenada no catálogo;
4. modelo local, com aviso explícito sobre as limitações de contexto e de qualidade.

Os demais aprovados entram em `fallback_providers`, na mesma ordem.

### Modelos auxiliares

- `compression`: um modelo de nuvem aprovado com contexto grande; o local só se não houver
  nenhum de nuvem.
- `title_generation`, `session_search`, `web_extract`: o modelo local, quando existir, com
  `fallback_chain` para um modelo de nuvem aprovado.

### Atalhos para `/model`

Para cada modelo aprovado é criado um atalho em `model_aliases`, com nomes que não colidem com os
atalhos embutidos do Hermes. O instalador verifica cada atalho com
`hermes chat --oneshot -m <atalho>` e confere no log o provedor e o modelo que realmente
responderam.

### oh-my-hermes

- Executor de código padrão: `codex`, quando o Codex CLI estiver logado; caso contrário, `hermes`.
- As cadeias de modelos (`omh model-chains set`) e as do executor (`omh coding category-maestro set
  codex …`) são reescritas para conter **apenas modelos aprovados**, em três níveis (pesado,
  intermediário e rápido), com o nível rápido preferindo o modelo local.
- Executores e modelos de fornecedores pagos por token não entram na configuração.

## 4. Edição de configuração

- O YAML é editado com **ruamel.yaml**, em modo round-trip para preservar os comentários. Nunca por
  substituição de texto.
- Antes de gravar: valida que não haverá chaves duplicadas e que blocos como `model_aliases`,
  `fallback_providers` e `auxiliary` ficam no nível certo. Um bloco comentado (`# model_aliases:`)
  não é confundido com o real.
- As chaves gravadas pelo instalador ficam registradas num arquivo de estado
  (`freeagent-state.json`), para que uma nova execução atualize só o que é dela.

## 5. Erros, backup e rollback

- Backup de `config.yaml`, `.env`, `auth.json` e `~/.omh/routing/` em
  `<HERMES_HOME>/freeagent-backups/<timestamp>/` antes de qualquer escrita.
- `--rollback` restaura o backup mais recente e informa o que voltou.
- Toda chamada externa tem timeout; falhas de rede em etapas opcionais são registradas e puladas.
- Mensagens de erro dizem o que falhou, o efeito e o comando para tentar de novo.

## 6. Segurança e privacidade

- Chaves são lidas com entrada oculta e entregues só ao comando de autenticação do próprio Hermes.
  Não são gravadas por este instalador nem aparecem em logs ou relatórios.
- `redact.py` mascara padrões de segredos (`nvapi-…`, `sk-…`, tokens Bearer, JWT) em tudo o que é
  exibido ou gravado.
- O repositório não contém caminhos absolutos de usuário, nomes, e-mails ou chaves. O CI varre o
  repositório a cada push procurando esses padrões.
- O instalador não envia telemetria.

## 7. Idioma

- As mensagens do instalador ficam em `i18n/en.json` e `i18n/pt.json`. O idioma vem do sistema
  (`Get-Culture` no Windows, `LANG` no Linux), e `--lang pt|en` força um deles.
- Há dois READMEs completos: `README.md` (inglês) e `docs/README.pt-BR.md`.

## 8. CLI

```
freeagent [--dry-run] [--yes] [--lang pt|en] [--skip-local] [--skip-cloud] [--rollback]
```

- `--dry-run`: executa detect e plan e mostra o plano, sem instalar nem escrever nada.
- `--yes`: pula a confirmação; os logins com navegador continuam opcionais.

## 9. Testes

- **Unitários (pytest):**
  - parsing de `nvidia-smi`, `rocm-smi` e `ollama ps` a partir de fixtures;
  - `plan` para cada faixa de VRAM e combinação de provedores;
  - edição de YAML: preserva comentários, bloco `# model_aliases:` comentado, chave duplicada
    pré-existente e reexecução idempotente;
  - `redact`;
  - rollback.
- **CI (GitHub Actions):** Windows e Ubuntu: ruff, pytest, `--dry-run` e a varredura de dados
  pessoais e segredos.
- **Validação manual antes de publicar:** execução completa em Windows com um `HERMES_HOME`
  temporário e isolado, e em Linux via WSL.

## 10. Riscos

- **Catálogos de terceiros mudam** (nomes de modelos, planos grátis). Mitigação: o teste real decide;
  o catálogo é um arquivo de dados fácil de atualizar.
- **Instaladores oficiais mudam de flags.** Mitigação: o bootstrap verifica a versão e falha com uma
  mensagem clara, e o CI faz o dry-run.
- **Mudanças no formato do config do Hermes.** Mitigação: `hermes config check` depois de gravar, com
  rollback automático.
