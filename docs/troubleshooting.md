# Troubleshooting · Problemas comuns

## oh-my-hermes is configured, but Hermes does not see it · O OMH não aparece no Hermes

**EN.** On native Windows, Hermes lives in `%LOCALAPPDATA%\hermes`, not `~/.hermes`. If oh-my-hermes was set up before
that folder was known, it registered itself in the wrong place. Run the installer again: it sets `HERMES_HOME` first
and then re-runs `omh setup`. Check with `/plugins` inside Hermes.

**PT.** No Windows nativo, o Hermes fica em `%LOCALAPPDATA%\hermes`, e não em `~/.hermes`. Se o oh-my-hermes foi
configurado antes de essa pasta ser conhecida, ele se registrou no lugar errado. Rode o instalador de novo: ele define
`HERMES_HOME` primeiro e roda o `omh setup` outra vez. Confira com `/plugins` dentro do Hermes.

## "hermes config check" fails · O config check falha

**EN.** The installer restores your previous config automatically. If the config was already broken before (for
example, a duplicated key), the installer stops without writing and lists the duplicated keys. Fix them with
`hermes config edit` and run again.

**PT.** O instalador restaura o config anterior sozinho. Se o config já estava quebrado antes (uma chave duplicada,
por exemplo), o instalador para sem gravar nada e lista as chaves duplicadas. Corrija com `hermes config edit` e rode
de novo.

## The local model spills to the CPU · O modelo local transborda para a CPU

**EN.** Other programs (games, browsers with hardware acceleration) use VRAM too. Close them and run the installer
again, or keep the smaller context it picked. `ollama ps` shows the GPU/CPU split.

**PT.** Outros programas (jogos, navegadores com aceleração de hardware) também usam VRAM. Feche-os e rode o
instalador de novo, ou fique com o contexto menor que ele escolheu. O `ollama ps` mostra a divisão entre GPU e CPU.

## A model is rejected with http_402 · Um modelo é recusado com http_402

**EN.** That model is not part of your free plan. Nothing to fix: it is simply left out.

**PT.** Esse modelo não faz parte do seu plano gratuito. Não há o que corrigir: ele só fica de fora.

## A model is rejected with served_by_other · Um modelo é recusado com served_by_other

**EN.** Hermes answered, but through a fallback model, which means the alias did not reach the provider (missing
login, or the provider was down). Check `hermes auth status <provider>` and run again.

**PT.** O Hermes respondeu, mas por um modelo de reserva, ou seja, o atalho não chegou ao provedor (login faltando, ou
o provedor estava fora do ar). Confira com `hermes auth status <provedor>` e rode de novo.

## Ollama is not running · O Ollama não está rodando

**EN.** Start it (`ollama serve` on Linux, or open the Ollama app on Windows) and run again. The installer waits up to
30 seconds for it.

**PT.** Inicie o Ollama (`ollama serve` no Linux, ou abra o app do Ollama no Windows) e rode de novo. O instalador
espera até 30 segundos por ele.
