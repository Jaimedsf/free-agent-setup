# free-agent-setup

[English](../README.md) · [Problemas comuns](troubleshooting.md)

Um comando monta no seu computador um **agente de programação com IA, gratuito e ajustado ao seu hardware**: o
[Hermes Agent](https://hermes-agent.nousresearch.com/) com os workflows do [oh-my-hermes](https://github.com/rlaope/oh-my-hermes).
O instalador analisa a máquina, escolhe a melhor combinação de modelos **gratuitos** e testa cada modelo na sua conta
antes de gravar no config.

## Instalação

**Windows** (PowerShell):

```powershell
irm https://raw.githubusercontent.com/Jaimedsf/free-agent-setup/main/install.ps1 | iex
```

**Linux**:

```bash
curl -fsSL https://raw.githubusercontent.com/Jaimedsf/free-agent-setup/main/install.sh | bash
```

Primeiro aparece o plano e você confirma uma vez. Nada é instalado antes disso.

## O que ele faz

1. **Detecta** o sistema, a GPU e a VRAM livre (NVIDIA ou AMD), a RAM, a CPU, o disco, o idioma e as ferramentas que
   já existem (Hermes, oh-my-hermes, Ollama, Codex CLI e outras CLIs de agente).
2. **Planeja**: escolhe um modelo local que caiba na GPU, os provedores gratuitos que vai testar e o executor de código.
3. **Confirma**: mostra o plano com o motivo de cada item.
4. **Instala** o que falta, pelo instalador oficial de cada projeto. O assistente do Hermes é pulado, porque esta
   ferramenta faz a configuração.
5. **Faz os logins** nos provedores gratuitos. Cada um é opcional, e as chaves são digitadas no prompt oculto do
   próprio Hermes.
6. **Testa**: manda um "Reply only: OK" curto para cada candidato. Os que dão erro, pedem plano pago ou estouram o tempo
   ficam de fora. O modelo local é conferido para rodar **100% na GPU**.
7. **Configura** o Hermes e o oh-my-hermes só com os modelos aprovados. O config passa por backup antes e é validado
   com `hermes config check`; se a validação falhar, o backup volta automaticamente.
8. **Relata**: mostra um resumo e salva o `freeagent-report.md` na pasta do Hermes.

## Modelo local (roda na sua GPU)

| VRAM livre | Modelo | Download | Contexto alvo |
|---|---|---|---|
| menos de 4 GB, ou sem GPU | nenhum (só na CPU ficaria lento) | — | — |
| 4–6 GB | `bonsai-2:4b` | 1,6 GB | 32k |
| 6–10 GB | `bonsai-2:9b` | 3,2 GB | 64k |
| 10–16 GB | `bonsai-2:9b` | 3,2 GB | 128k |
| 16 GB ou mais | `bonsai-2:27b` | 8,3 GB | 64k |

Se o modelo não couber inteiro na GPU, o contexto cai pela metade (até 16k); se ainda não couber, um modelo menor é
testado. O modelo local cuida das tarefas leves (títulos de sessão, busca, extração de páginas web). Ele não é o
principal, porque sessões longas de programação precisam de muito mais contexto do que um modelo local pequeno comporta.

## Provedores gratuitos (modelo principal, nesta ordem)

| Provedor | O que você precisa | Modelo |
|---|---|---|
| NVIDIA build | uma chave grátis em [build.nvidia.com](https://build.nvidia.com/) | `nemotron-3-ultra` |
| Ollama Cloud | uma conta grátis (`ollama signin`) | `nemotron-3-ultra:cloud`, `nemotron-3-super:cloud`, `gemma4:31b-cloud` |
| Google AI Studio | uma chave grátis em [aistudio.google.com](https://aistudio.google.com/apikey) | `gemini-3.6-flash`, `gemini-3.5-flash-lite` |
| Codex | só se o Codex CLI já estiver logado nesta máquina | os modelos que o seu plano aceita |

O primeiro aprovado vira o modelo principal e os outros viram reservas automáticas. Se nenhum passar, o modelo local
vira o principal e o relatório avisa. Provedores cobrados por token nunca são configurados.

## Opções

```
--dry-run      detecta e mostra o plano, sem mudar nada
--yes          pula a confirmação (os logins no navegador continuam perguntando)
--lang pt|en   força o idioma (padrão: o idioma do sistema)
--skip-local   sem modelo local
--skip-cloud   sem provedores na nuvem
--rollback     restaura o config do último backup
--catalog X    catálogo de modelos: uma URL https, um arquivo ou `bundled`
```

A lista de modelos grátis muda com frequência, então cada execução baixa primeiro o catálogo mais recente deste
repositório. Se falhar (sem internet, arquivo inválido), usa o catálogo que veio com a sua versão e o relatório avisa.

No Windows, as opções vão por uma variável de ambiente:

```powershell
$env:FREEAGENT_ARGS = "--dry-run"; irm https://raw.githubusercontent.com/Jaimedsf/free-agent-setup/main/install.ps1 | iex
```

No Linux, depois de `bash -s --`:

```bash
curl -fsSL https://raw.githubusercontent.com/Jaimedsf/free-agent-setup/main/install.sh | bash -s -- --dry-run
```

## Uso

Abra o Hermes com `hermes`. Troque de modelo quando quiser, sem perder a conversa:

```
/model nemotron         # NVIDIA build
/model nemotron-ollama  # o mesmo modelo pelo Ollama Cloud
/model local            # o modelo na sua GPU
```

Os atalhos criados na sua máquina estão listados no `freeagent-report.md`.

## Desfazer

Rode o instalador com `--rollback`. Os backups ficam em `<pasta do Hermes>/freeagent-backups/`.

## Privacidade

- As chaves de API vão direto para o prompt do Hermes; esta ferramenta nunca as lê, guarda ou registra.
- O relatório e a saída mascaram qualquer coisa parecida com chave ou token.
- Sem telemetria. Nada da sua máquina sai dela, além das requisições de teste aos provedores que você ativar.

## Limitações

- Planos gratuitos mudam e têm limites (requisições por minuto, cota mensal, uma requisição por vez no Ollama Free).
  O teste decide o que é usado hoje; rode o instalador de novo para conferir outra vez.
- O modelo local tem uma janela de contexto pequena em comparação com os modelos de nuvem.
- O macOS ainda não é suportado.

## Desenvolvimento

```bash
uv run pytest -q
uv run ruff check
uv run python scripts/privacy_scan.py
```

Licença: MIT.
