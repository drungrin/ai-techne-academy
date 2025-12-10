# Gerenciamento de Contexto e Checkpoints - AI Techne Academy

Este documento explica como gerenciar o contexto durante a implementação deste projeto, que levará múltiplas sessões ao longo de dias ou semanas.

## 🎯 Problema

Projetos grandes como este precisam de múltiplas sessões de trabalho. É crucial:
1. Saber exatamente onde você parou
2. Manter o histórico de decisões
3. Não perder trabalho entre sessões
4. Ter clareza sobre o que falta fazer

## 📁 Sistema de Arquivos de Controle

### Arquivos de Estado

#### 1. `implementation_checkpoint.json` - O "Save Game"
Armazena o estado atual da implementação:

```json
{
  "current_phase": 1,
  "current_task": "1.1",
  "last_updated": "2024-12-10T17:00:00Z",
  "status": "IN_PROGRESS",
  "completed_tasks": [
    "planning",
    "architecture_design"
  ],
  "next_tasks": [
    "1.1: Setup de Repositório e Ambiente",
    "1.2: Infraestrutura AWS Base"
  ],
  "blockers": [],
  "notes": "Especificação completa finalizada. Pronto para iniciar implementação."
}
```

#### 2. `implementation_log.md` - O "Diário de Bordo"
Histórico cronológico de todas as atividades:

```markdown
# Log de Implementação - AI Techne Academy

## 2024-12-10

### ✅ Completado
- [x] Especificação técnica completa (SPECIFICATION.md)
- [x] README com guia de uso
- [x] Exemplos práticos (EXAMPLES.md)
- [x] Plano de implementação de 6 semanas
- [x] Correção do modelo Bedrock para Claude Sonnet 4
- [x] Atualização do nome do projeto para ai-techne-academy

### 📝 Decisões Técnicas
- Modelo LLM: anthropic.claude-sonnet-4-5-20250929-v1:0
- Arquitetura: Step Functions + ECS Fargate + Bedrock
- Custo estimado: $1.45 por vídeo de 3h

### 🚀 Próximos Passos
1. Criar repositório GitHub
2. Setup de ambiente AWS
3. Iniciar Fase 1: Setup Inicial
```

#### 3. `decisions_log.md` - Registro de Decisões Arquiteturais (ADR)
Documenta todas as decisões importantes e seus motivos:

```markdown
# Architectural Decision Records (ADR)

## ADR-001: Escolha do Modelo LLM

**Data**: 2024-12-10  
**Status**: Aceito  
**Contexto**: Precisamos escolher o modelo LLM para geração de documentos.  
**Decisão**: Usar Claude Sonnet 4 (anthropic.claude-sonnet-4-5-20250929-v1:0)  
**Consequências**:
- Suporta 200k tokens de contexto (ideal para vídeos de 3h)
- Custo estimado de $0.90 por execução
- Melhor qualidade de saída vs modelos menores
```

## 🔄 Fluxo de Trabalho entre Sessões

### Ao INICIAR uma Nova Sessão

```markdown
Olá! Estou continuando o desenvolvimento do projeto AI Techne Academy.

Por favor:
1. Leia `implementation_checkpoint.json` para ver onde paramos
2. Leia `implementation_log.md` para contexto das últimas sessões
3. Verifique a lista de tarefas pendentes
4. Continue de onde paramos na Fase [X], Tarefa [Y]

**Última sessão**: [data]
**Última tarefa**: [tarefa]
**Status**: [status]
```

### Ao FINALIZAR uma Sessão

```markdown
Antes de finalizar, por favor:
1. Atualize `implementation_checkpoint.json` com o estado atual
2. Adicione entrada em `implementation_log.md` com o que foi feito
3. Liste claramente os próximos passos
4. Documente qualquer decisão técnica importante em `decisions_log.md`
5. Commite e push todas as mudanças
```

## 📋 Template de Prompt para Continuação

### Prompt Padrão para Retomar Trabalho

```
# CONTEXTO: Projeto AI Techne Academy - Continuação

Estou retomando o desenvolvimento do projeto AI Techne Academy (sistema de processamento de vídeos com geração de documentos usando LLM).

## MODO DE EXECUÇÃO: STATEFUL & INCREMENTAL

Este é um projeto que será desenvolvido em múltiplas sessões. Você deve:

### PASSO 1: CARREGAR O ESTADO ATUAL
1. Leia `implementation_checkpoint.json` para ver o estado atual
2. Leia `implementation_log.md` para entender o histórico
3. Revise `IMPLEMENTATION_PLAN.md` para ver o plano geral

### PASSO 2: DETERMINAR AÇÃO
- **Se checkpoint.status == "IN_PROGRESS"**: Continue da tarefa atual
- **Se checkpoint.status == "BLOCKED"**: Resolva o blocker primeiro
- **Se checkpoint.status == "COMPLETED"**: Avance para próxima fase

### PASSO 3: EXECUTAR TRABALHO
- Implemente APENAS a tarefa atual do checkpoint
- Não tente fazer tudo de uma vez
- Teste cada componente antes de prosseguir
- Documente decisões importantes

### PASSO 4: ATUALIZAR ESTADO
- Atualize `implementation_checkpoint.json` ao completar a tarefa
- Adicione entrada em `implementation_log.md`
- Commite as mudanças
- Indique claramente o próximo passo

## INFORMAÇÕES DO CHECKPOINT ATUAL
Por favor, leia os arquivos de controle e me informe:
- Qual é a fase atual?
- Qual tarefa está em andamento?
- Quais são os próximos passos?
- Existem bloqueios?

Aguardo suas orientações para prosseguir.
```

## 🎯 Estratégia de Divisão de Trabalho

### Princípio: One Task at a Time

Cada sessão deve focar em **UMA** tarefa específica do plano:

**❌ NÃO FAÇA:**
```
"Vou implementar todas as Lambda functions hoje"
```

**✅ FAÇA:**
```
"Vou implementar a Trigger Function e seus testes unitários"
```

### Tamanho Ideal de Tarefa

Uma tarefa ideal deve:
- Ser completável em 2-4 horas
- Produzir código testável
- Ter critérios claros de conclusão
- Não depender de muitas outras tarefas

### Exemplo de Subdivisão

**Tarefa Original (muito grande):**
> "2.1 Lambda Functions (3 dias)"

**Subdivisão Correta:**
1. Implementar Trigger Function (4h)
2. Testes unitários para Trigger (2h)
3. Implementar Transcribe Starter (4h)
4. Testes unitários para Transcribe Starter (2h)
5. Implementar Finalizer (4h)
6. Testes unitários para Finalizer (2h)
7. Integração e deploy em dev (4h)

## 📊 Dashboard de Progresso

### Criar Arquivo de Status Visual

**`PROJECT_STATUS.md`**
```markdown
# AI Techne Academy - Status do Projeto

Atualizado: 2024-12-10 17:00

## Progresso Geral: 15%

### ✅ Fase 0: Planejamento (100%)
- [x] Especificação técnica
- [x] Arquitetura
- [x] Plano de implementação
- [x] Documentação inicial

### 🔄 Fase 1: Setup Inicial (0%)
- [ ] 1.1 Setup de Repositório
- [ ] 1.2 Infraestrutura AWS Base

### ⏸️ Fase 2: Desenvolvimento Core (0%)
Aguardando conclusão da Fase 1

### ⏸️ Fase 3: Orquestração (0%)
Aguardando conclusão da Fase 2

### ⏸️ Fase 4: Testes (0%)
Aguardando conclusão da Fase 3

### ⏸️ Fase 5: Deploy (0%)
Aguardando conclusão da Fase 4

## Próxima Ação
**Iniciar Tarefa 1.1**: Setup de Repositório e Ambiente
**Responsável**: [Nome]
**Prazo**: [Data]
```

## 🔧 Ferramentas de Apoio

### Script para Atualizar Checkpoint

**`scripts/update-checkpoint.sh`**
```bash
#!/bin/bash

# Update checkpoint with current status
CURRENT_PHASE=$1
CURRENT_TASK=$2
STATUS=$3

cat > implementation_checkpoint.json <<EOF
{
  "current_phase": $CURRENT_PHASE,
  "current_task": "$CURRENT_TASK",
  "last_updated": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "status": "$STATUS",
  "completed_tasks": $(cat implementation_checkpoint.json | jq '.completed_tasks'),
  "next_tasks": $(cat implementation_checkpoint.json | jq '.next_tasks'),
  "blockers": [],
  "notes": "$4"
}
EOF

echo "✅ Checkpoint atualizado: Fase $CURRENT_PHASE, Tarefa $CURRENT_TASK, Status: $STATUS"
```

### Script para Ver Status

**`scripts/show-status.sh`**
```bash
#!/bin/bash

echo "=== AI Techne Academy - Status Atual ==="
echo ""
echo "📊 Checkpoint:"
cat implementation_checkpoint.json | jq '.'
echo ""
echo "📝 Últimas 5 entradas do log:"
tail -n 20 implementation_log.md
echo ""
echo "🚀 Próximos passos:"
cat implementation_checkpoint.json | jq -r '.next_tasks[]'
```

## 📚 Convenções de Commit

Para facilitar o rastreamento:

```
feat(fase-1): implementar setup de repositório
^    ^        ^
|    |        |
|    |        +-- Descrição clara
|    +-- Fase do projeto
+-- Tipo de mudança

Tipos:
- feat: nova funcionalidade
- fix: correção de bug
- docs: apenas documentação
- test: adicionar/modificar testes
- refactor: refatoração de código
- chore: tarefas de manutenção
```

## 🎓 Boas Práticas

### 1. Commits Frequentes
Commite a cada pequeno progresso, não apenas no final do dia.

### 2. Documentação Inline
Ao tomar decisões técnicas, documente no momento.

### 3. Testes Incrementais
Teste cada componente antes de prosseguir.

### 4. Revisão Diária
No fim de cada sessão, revise o que foi feito e planeje o próximo dia.

### 5. Comunicação Clara
Deixe notas claras no checkpoint para seu "eu do futuro".

## 🚨 Sinais de Alerta

Você deve PAUSAR e reavaliar se:
- Uma tarefa está levando >2x o tempo estimado
- Você está fazendo muitas mudanças arquiteturais
- Os testes estão falhando consistentemente
- Você não tem certeza do próximo passo

Nestes casos:
1. Atualize o checkpoint com status "BLOCKED"
2. Documente o problema em `blockers`
3. Peça ajuda ou reavalie a abordagem

## 📞 Suporte

Se precisar retomar o contexto ou está perdido:
1. Leia este documento
2. Revise os arquivos de controle
3. Use o prompt de continuação acima
4. Consulte o IMPLEMENTATION_PLAN.md

---

**Lembre-se**: Devagar e sempre. É melhor fazer uma tarefa bem feita por vez do que tentar fazer tudo e perder o controle.