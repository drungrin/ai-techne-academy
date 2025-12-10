# Prompt para Continuar o Projeto AI Techne Academy

Use este prompt quando for retomar o trabalho em uma nova sessão.

---

## 📋 Prompt de Continuação (Copiar e Colar)

```
# CONTEXTO: Projeto AI Techne Academy - Continuação

Estou retomando o desenvolvimento do projeto AI Techne Academy - um sistema de processamento de vídeos que gera automaticamente documentos de Treinamento e Troubleshooting usando AWS Transcribe e Bedrock (Claude Sonnet 4).

## MODO DE EXECUÇÃO: STATEFUL & INCREMENTAL

Este é um projeto de longo prazo que será desenvolvido em múltiplas sessões. Você deve trabalhar de forma incremental, uma tarefa por vez.

### PASSO 1: CARREGAR O ESTADO ATUAL

Por favor, leia os seguintes arquivos para entender o contexto:

1. **PROJECT_STATUS.md** - Status geral e progresso
2. **implementation_log.md** - Histórico de sessões anteriores
3. **IMPLEMENTATION_PLAN.md** - Plano geral de 6 semanas

### PASSO 2: DETERMINAR PRÓXIMA AÇÃO

Com base nos arquivos acima, me informe:
- ✅ Qual é a fase atual?
- 📍 Qual tarefa específica devemos trabalhar agora?
- 🚧 Existem bloqueios ou dependências?
- 📊 Qual é o progresso geral?

### PASSO 3: EXECUTAR TRABALHO INCREMENTAL

**Regras Importantes:**
- Trabalhe em APENAS UMA tarefa por vez
- Teste cada componente antes de avançar
- Documente decisões importantes
- Faça commits frequentes
- NÃO tente fazer tudo de uma vez

### PASSO 4: ATUALIZAR ESTADO

Ao finalizar, atualize:
1. **PROJECT_STATUS.md** - Progresso da fase/tarefa
2. **implementation_log.md** - Nova entrada com o que foi feito
3. Indique claramente qual é o próximo passo

## INFORMAÇÕES DO PROJETO

**Nome**: AI Techne Academy
**Objetivo**: Processar vídeos (até 3h) e gerar documentos de treinamento via LLM
**Modelo LLM**: anthropic.claude-sonnet-4-5-20250929-v1:0 (Claude Sonnet 4)
**Arquitetura**: Step Functions + ECS Fargate + AWS Bedrock
**Runtime**: Python 3.12
**Custo Estimado**: $1.45 por vídeo de 3h

## PRÓXIMOS PASSOS (Conforme Última Sessão)

1. Criar repositório GitHub
2. Setup de ambiente AWS
3. Configurar desenvolvimento local
4. Iniciar Fase 1: Setup Inicial

---

Aguardo sua análise do estado atual e recomendações sobre qual tarefa trabalhar agora.
```

---

## 🎯 Variações do Prompt

### Para Começar uma Nova Fase

```
Olá! Acabamos de completar a Fase [X] do projeto AI Techne Academy.

Por favor:
1. Leia PROJECT_STATUS.md para confirmar o que foi concluído
2. Revise IMPLEMENTATION_PLAN.md para a próxima fase
3. Atualize PROJECT_STATUS.md marcando a fase anterior como completa
4. Liste as tarefas da nova fase que vamos iniciar
5. Sugira por qual tarefa começar

Aguardo suas orientações.
```

### Quando Houver um Bloqueio

```
Encontrei um bloqueio no projeto AI Techne Academy.

**Bloqueio**: [Descrever o problema]
**Tarefa Atual**: [Qual tarefa estava sendo executada]
**Tentativas**: [O que já foi tentado]

Por favor:
1. Leia PROJECT_STATUS.md para contexto
2. Analise o bloqueio
3. Sugira possíveis soluções ou alternativas
4. Atualize PROJECT_STATUS.md adicionando o bloqueio
5. Indique se devemos pausar esta tarefa e trabalhar em outra

Aguardo suas orientações.
```

### Para Fazer Code Review

```
Preciso de code review no projeto AI Techne Academy.

**Arquivo(s)**: [Listar arquivos]
**Contexto**: [Qual tarefa foi implementada]

Por favor:
1. Revise o código seguindo as melhores práticas
2. Verifique conformidade com a especificação (SPECIFICATION.md)
3. Sugira melhorias
4. Identifique possíveis bugs
5. Valide se os testes estão adequados

Após o review, vou ajustar o código conforme suas sugestões.
```

### Para Debugging

```
Estou com um erro no projeto AI Techne Academy.

**Erro**: [Descrição do erro]
**Contexto**: [O que estava tentando fazer]
**Logs**: [Colar logs relevantes]

Por favor:
1. Analise o erro
2. Identifique a causa raiz
3. Sugira solução
4. Indique se precisa de mais informações

Aguardo suas orientações.
```

---

## 📚 Documentos de Referência

### Para Consulta Rápida
- **Arquitetura**: Ver SPECIFICATION.md seção 2
- **Custos**: Ver SPECIFICATION.md seção 8
- **Exemplos de Código**: Ver EXAMPLES.md
- **Troubleshooting**: Ver README.md seção "Troubleshooting"

### Para Decisões Técnicas
- **Escolhas Arquiteturais**: Ver implementation_log.md
- **Padrões de Código**: Ver EXAMPLES.md
- **Infraestrutura AWS**: Ver SPECIFICATION.md seção 5

---

## ⚡ Atalhos Úteis

### Verificar Status Rapidamente
```
Por favor, leia PROJECT_STATUS.md e me dê um resumo de:
1. Progresso geral (%)
2. Fase atual e tarefa em andamento
3. Bloqueios (se houver)
4. Próximos 3 passos

Formato: bullets points, máximo 10 linhas.
```

### Listar Próximas N Tarefas
```
Com base em IMPLEMENTATION_PLAN.md e PROJECT_STATUS.md, liste as próximas 5 tarefas a serem executadas, em ordem de prioridade, com estimativa de tempo para cada uma.
```

### Atualizar Documentação
```
Por favor, atualize a documentação do projeto AI Techne Academy:
1. PROJECT_STATUS.md - Marcar [tarefa X] como completa
2. implementation_log.md - Adicionar entrada para hoje com [resumo]
3. Indicar próximo passo

[Fornecer detalhes do que foi completado]
```

---

## 🔧 Manutenção dos Arquivos de Controle

### Atualização Diária (Durante Desenvolvimento Ativo)
```
Fim do dia - atualizar:
1. PROJECT_STATUS.md
   - Progresso das tarefas
   - Métricas (linhas de código, testes)
2. implementation_log.md
   - Nova entrada com data de hoje
   - O que foi feito
   - Próximos passos
```

### Atualização Semanal
```
Fim da semana - atualizar:
1. PROJECT_STATUS.md
   - Progresso geral
   - Timeline
   - Riscos
2. implementation_log.md
   - Resumo da semana
3. Fazer backup dos arquivos de controle
```

### Ao Mudar de Fase
```
Mudança de fase - atualizar:
1. PROJECT_STATUS.md
   - Marcar fase anterior como completa
   - Iniciar nova fase
   - Atualizar progresso geral
2. implementation_log.md
   - Entrada especial de mudança de fase
   - Retrospectiva da fase concluída
3. Fazer commit com mensagem: "chore: complete phase [X]"
```

---

## 💡 Dicas para Uso Eficiente

### 1. Sempre Comece Lendo o Status
Não assuma onde parou. Sempre leia PROJECT_STATUS.md primeiro.

### 2. Uma Tarefa por Vez
Não tente implementar múltiplas funcionalidades simultaneamente.

### 3. Teste Antes de Avançar
Cada componente deve ser testado antes de prosseguir.

### 4. Documente Decisões
Se tomou uma decisão técnica importante, documente no implementation_log.md.

### 5. Commits Frequentes
Commite a cada pequeno progresso, não apenas no final do dia.

### 6. Use os Exemplos
Consulte EXAMPLES.md para padrões de código e casos de uso.

### 7. Respeite o Plano
Siga IMPLEMENTATION_PLAN.md. Se precisar desviar, documente o motivo.

---

## 🎓 Melhores Práticas

### Início de Sessão
1. Ler PROJECT_STATUS.md
2. Ler última entrada de implementation_log.md
3. Confirmar qual tarefa trabalhar
4. Estimar tempo necessário
5. Começar

### Durante a Sessão
1. Focar em uma tarefa
2. Testar incrementalmente
3. Documentar decisões
4. Fazer commits pequenos
5. Atualizar status se necessário

### Fim de Sessão
1. Completar a tarefa atual (se possível)
2. Fazer commit final
3. Atualizar PROJECT_STATUS.md
4. Adicionar entrada em implementation_log.md
5. Listar claramente próximos passos

---

**Este arquivo deve ser sua primeira referência ao retomar o trabalho no projeto.**  
**Escolha o prompt apropriado e comece!** 🚀