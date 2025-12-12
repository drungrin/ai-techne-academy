"""
Document Generator with 6-Stage Pipeline

This module orchestrates the complete document generation pipeline using
AWS Bedrock (Claude Sonnet 3.5/4.5) to transform video transcriptions into
structured technical training and troubleshooting documents.

Pipeline Stages:
1. Transcription Cleaning and Analysis
2. Technical Content Extraction (JSON)
3. Solution Mapping (JSON)
4. Document Structuring (Outline)
5. Content Writing (Full Markdown)
6. Output Generation (Markdown + DOCX)

Author: AI Techne Academy
Version: 1.2.0 (Optimized for High-Context Models)
"""

import io
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from docx import Document

from llm_client import BedrockLLMClient, TokenUsage, create_xml_prompt
from transcription_parser import TranscriptionParser, TranscriptionChunk

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result from a pipeline stage."""

    stage_id: int
    stage_name: str
    output: Any
    tokens_used: TokenUsage
    duration_seconds: float
    status: str  # 'success' or 'failed'
    error: Optional[str] = None


@dataclass
class DocumentGenerationResult:
    """Final result of document generation."""

    markdown_content: str
    markdown_s3_uri: str
    docx_s3_uri: str
    total_tokens: TokenUsage
    total_cost_usd: float
    duration_seconds: float
    stages: List[StageResult]
    chunks_processed: int


class DocumentGenerator:
    """
    Document generator using 6-stage pipeline with dynamic token allocation.
    """

    def __init__(
        self,
        llm_client: BedrockLLMClient,
        parser: TranscriptionParser,
        s3_client: Any,
        max_output_tokens: int = 64000  # Default for Sonnet 4.5/High-Context models
    ):
        """
        Initialize document generator with dynamic token limits.

        Args:
            llm_client: Bedrock LLM client
            parser: Transcription parser
            s3_client: boto3 S3 client
            max_output_tokens: Maximum output tokens supported by model
        """
        self.llm = llm_client
        self.parser = parser
        self.s3 = s3_client

        # Dynamic Token Allocation Strategy
        # Stage 2: 25% - Sufficient buffer for raw data extraction without truncation
        self.stage_2_max_tokens = int(max_output_tokens * 0.25)

        # Stage 3: 50% - Critical buffer for deep hierarchical JSON (Problem -> Cause -> Solution)
        self.stage_3_max_tokens = int(max_output_tokens * 0.50)

        # Stage 4: 25% - Generous for outlines, but requires strict prompting to avoid full writing
        self.stage_4_max_tokens = int(max_output_tokens * 0.25)

        # Stage 5: 100% - Use full capacity for comprehensive technical documentation
        self.stage_5_max_tokens = max_output_tokens

        logger.info(
            f"DocumentGenerator initialized with max_output_tokens={max_output_tokens}. "
            f"Limits -> S2:{self.stage_2_max_tokens}, S3:{self.stage_3_max_tokens}, "
            f"S4:{self.stage_4_max_tokens}, S5:{self.stage_5_max_tokens}"
        )

    def generate_document(
        self,
        execution_id: str,
        transcription_s3_uri: str,
        output_bucket: str
    ) -> DocumentGenerationResult:
        """
        Execute complete 6-stage pipeline.
        """
        start_time = datetime.now()
        logger.info(f"Starting document generation for execution {execution_id}")

        # Set logging folder for LLM client
        self.llm.set_logging_folder(f"/tmp/ai-techne/academy/{execution_id}")

        try:
            # Load and parse transcription
            transcription_data = self._load_transcription(transcription_s3_uri)
            parsed = self.parser.parse_transcribe_json(transcription_data)

            # Chunk if necessary
            chunks = self.parser.chunk_transcription(parsed)
            logger.info(f"Processing {len(chunks)} chunk(s)")

            # Process chunks through pipeline
            stage_results = []

            # For multi-chunk, process each chunk separately then merge
            if len(chunks) == 1:
                chunk_results = self._process_single_chunk(chunks[0])
                stage_results = chunk_results
            else:
                chunk_results = self._process_multiple_chunks(chunks)
                stage_results = chunk_results

            # Extract final markdown from last stage
            final_stage = stage_results[-1]
            markdown_content = final_stage.output

            # Check if final stage failed
            if markdown_content is None or final_stage.status == 'failed':
                error_msg = final_stage.error or "Final stage produced no output"
                logger.error(f"Cannot generate output: {error_msg}")
                raise Exception(f"Document generation failed: {error_msg}")

            # Stage 6: Generate outputs
            stage_6_start = datetime.now()
            markdown_uri, docx_uri = self._stage_6_generate_outputs(
                execution_id=execution_id,
                markdown_content=markdown_content,
                output_bucket=output_bucket
            )
            stage_6_duration = (datetime.now() - stage_6_start).total_seconds()

            stage_results.append(StageResult(
                stage_id=6,
                stage_name="Output Generation",
                output={'markdown_uri': markdown_uri, 'docx_uri': docx_uri},
                tokens_used=TokenUsage(0, 0),
                duration_seconds=stage_6_duration,
                status='success'
            ))

            # Calculate totals
            total_tokens = TokenUsage(
                input_tokens=sum(s.tokens_used.input_tokens for s in stage_results),
                output_tokens=sum(s.tokens_used.output_tokens for s in stage_results)
            )
            total_duration = (datetime.now() - start_time).total_seconds()

            result = DocumentGenerationResult(
                markdown_content=markdown_content,
                markdown_s3_uri=markdown_uri,
                docx_s3_uri=docx_uri,
                total_tokens=total_tokens,
                total_cost_usd=total_tokens.calculate_cost(),
                duration_seconds=total_duration,
                stages=stage_results,
                chunks_processed=len(chunks)
            )

            logger.info(
                f"Document generation complete: {total_duration:.2f}s, "
                f"${result.total_cost_usd:.4f}, {len(markdown_content)} chars"
            )

            return result

        except Exception as e:
            logger.error(f"Document generation failed: {str(e)}")
            raise

    def _process_single_chunk(
        self,
        chunk: TranscriptionChunk
    ) -> List[StageResult]:
        """Process single chunk through all stages."""
        results = []

        # Stage 1: Clean transcription
        stage_1_result = self._stage_1_clean_transcription(chunk)
        results.append(stage_1_result)

        # Stage 2: Extract technical content
        stage_2_result = self._stage_2_extract_technical_content(
            stage_1_result.output
        )
        results.append(stage_2_result)

        # Stage 3: Map solutions
        stage_3_result = self._stage_3_map_solutions(
            stage_2_result.output
        )
        results.append(stage_3_result)

        # Stage 4: Structure document
        stage_4_result = self._stage_4_structure_document(
            stage_3_result.output
        )
        results.append(stage_4_result)

        # Stage 5: Write content
        stage_5_result = self._stage_5_write_content(
            stage_4_result.output
        )
        results.append(stage_5_result)

        return results

    def _process_multiple_chunks(
        self,
        chunks: List[TranscriptionChunk]
    ) -> List[StageResult]:
        """Process multiple chunks and merge results."""
        logger.info(f"Processing {len(chunks)} chunks with merge strategy")

        chunk_outlines = []

        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)}")

            # Stages 1-4 for each chunk
            stage_1 = self._stage_1_clean_transcription(chunk)
            stage_2 = self._stage_2_extract_technical_content(stage_1.output)
            stage_3 = self._stage_3_map_solutions(stage_2.output)
            stage_4 = self._stage_4_structure_document(stage_3.output)

            chunk_outlines.append(stage_4.output)

        # Merge outlines
        logger.info("Merging chunk outlines")
        merged_outline = self._merge_outlines(chunk_outlines)

        # Stage 5 with merged outline
        stage_5_result = self._stage_5_write_content(merged_outline)

        return [stage_5_result]

    def _stage_1_clean_transcription(
        self,
        chunk: TranscriptionChunk
    ) -> StageResult:
        """Stage 1: Clean and prepare transcription."""
        logger.info(f"Stage 1: Cleaning transcription (chunk {chunk.chunk_id})")
        start_time = datetime.now()

        try:
            formatted_text = self.parser.format_with_timestamps(
                chunk.segments,
                include_speakers=True
            )
            cleaned_text = formatted_text

            duration = (datetime.now() - start_time).total_seconds()

            return StageResult(
                stage_id=1,
                stage_name="Transcription Cleaning",
                output=cleaned_text,
                tokens_used=TokenUsage(0, 0),
                duration_seconds=duration,
                status='success'
            )

        except Exception as e:
            logger.error(f"Stage 1 failed: {str(e)}")
            return StageResult(
                stage_id=1,
                stage_name="Transcription Cleaning",
                output=None,
                tokens_used=TokenUsage(0, 0),
                duration_seconds=0,
                status='failed',
                error=str(e)
            )

    def _stage_2_extract_technical_content(
        self,
        cleaned_transcription: str
    ) -> StageResult:
        """
        Stage 2: Extract technical content using LLM.
        """
        logger.info("Stage 2: Extracting technical content")
        start_time = datetime.now()
        self.llm.set_stage_context("stage-2")

        prompt = create_xml_prompt(
            task="Você é um Analista Técnico de QA. Analise a transcrição e extraia fatos técnicos comprovados.",
            instructions="""Ignore diálogos sociais. Concentre-se exclusivamente no conteúdo técnico.

<CRITICAL_RULES>
1. GROUNDING: Se um comando (ex: SQL, Bash) não for soletrado ou lido explicitamente, NÃO O INVENTE.
2. GUI vs CLI: Se o usuário diz "cliquei aqui", classifique como "Ação de Interface Gráfica", não invente um comando de terminal equivalente.
</CRITICAL_RULES>
            
Gere um objeto JSON contendo as seguintes chaves (keys):

1. "diagnostics": Lista de objetos (error_code, root_cause).
2. "solutions": Lista de strings descrevendo passos técnicos. *Nota: Se for uma ação visual, descreva a ação (ex: "Clicar no botão processar"), não invente código.*
3. "risks": Avisos sobre concorrência/segurança.
4. "configurations": Convenções de nomenclatura e configs.
""",
            output_format="Responda APENAS com o JSON válido.",
            input_data=cleaned_transcription,
            input_tag="transcription"
        )

        try:
            # Set max_tokens to 25%
            original_max = self.llm.max_tokens
            self.llm.model.model_kwargs["max_tokens"] = self.stage_2_max_tokens

            response, usage = self.llm.invoke_with_json_output(prompt)

            self.llm.model.model_kwargs["max_tokens"] = original_max
            duration = (datetime.now() - start_time).total_seconds()

            logger.info(f"Stage 2 complete: {usage.total_tokens} tokens")
            return StageResult(
                stage_id=2,
                stage_name="Technical Content Extraction",
                output=response,
                tokens_used=usage,
                duration_seconds=duration,
                status='success'
            )

        except Exception as e:
            logger.error(f"Stage 2 failed: {str(e)}")
            duration = (datetime.now() - start_time).total_seconds()
            return StageResult(
                stage_id=2,
                stage_name="Technical Content Extraction",
                output=None,
                tokens_used=TokenUsage(0, 0),
                duration_seconds=duration,
                status='failed',
                error=str(e)
            )

    def _stage_3_map_solutions(
        self,
        technical_content: Dict[str, Any]
    ) -> StageResult:
        """
        Stage 3: Map problems to solutions.
        Adjusted to output explicit JSON keys.
        """
        logger.info("Stage 3: Mapping solutions")
        start_time = datetime.now()
        self.llm.set_stage_context("stage-3")

        prompt = create_xml_prompt(
            task="Você é um Engenheiro de Software Sênior. Crie um mapeamento hierárquico entre problemas e soluções.",
            instructions="""Com base no conteúdo técnico, gere um JSON com as seguintes chaves:

1. "problem_solution_map": Lista de objetos contendo:
   - "problem": Código/mensagem do erro
   - "root_cause": Causa raiz técnica
   - "solution_steps": Lista de passos executados
   - "commands": Lista de comandos usados
   - "outcome": Resultado obtido

2. "preventive_measures": Lista de strings sobre como evitar o problema no futuro.

3. "debugging_steps": Lista de strings sobre como diagnosticar/investigar o problema.
""",
            output_format="Responda APENAS com o JSON válido. Não use Markdown ou tags XML na resposta.",
            input_data=json.dumps(technical_content, indent=2),
            input_tag="technical_content"
        )

        try:
            # Set max_tokens to 50% (High capacity for complex structure)
            original_max = self.llm.max_tokens
            self.llm.model.model_kwargs["max_tokens"] = self.stage_3_max_tokens

            response, usage = self.llm.invoke_with_json_output(prompt)

            self.llm.model.model_kwargs["max_tokens"] = original_max
            duration = (datetime.now() - start_time).total_seconds()

            logger.info(f"Stage 3 complete: {usage.total_tokens} tokens")
            return StageResult(
                stage_id=3,
                stage_name="Solution Mapping",
                output=response,
                tokens_used=usage,
                duration_seconds=duration,
                status='success'
            )

        except Exception as e:
            logger.error(f"Stage 3 failed: {str(e)}")
            duration = (datetime.now() - start_time).total_seconds()
            return StageResult(
                stage_id=3,
                stage_name="Solution Mapping",
                output=None,
                tokens_used=TokenUsage(0, 0),
                duration_seconds=duration,
                status='failed',
                error=str(e)
            )

    def _stage_4_structure_document(
        self,
        solution_map: Dict[str, Any]
    ) -> StageResult:
        """
        Stage 4: Create document structure (outline).
        Added CRITICAL CONSTRAINT to prevent premature content writing.
        """
        logger.info("Stage 4: Structuring document")
        start_time = datetime.now()
        self.llm.set_stage_context("stage-4")

        prompt = create_xml_prompt(
            task="Você é um Designer Instrucional Técnico. Crie a estrutura para um Guia de Treinamento e Troubleshooting.",
            instructions="""Organize os tópicos considerando:
            
1. Troubleshooting (Erro -> Solução)
2. Procedimentos Práticos (Passo a passo, Debug)
3. Protocolos de Segurança (Ambiente compartilhado)
4. Regras de Negócio (Entendimento do sistema)
5. FAQ

<CRITICAL_CONSTRAINT>
Gere APENAS A ESTRUTURA (Outline) com títulos e bullet points descritivos do que será abordado.
NÃO ESCREVA O CONTEÚDO DOS PARÁGRAFOS AINDA.
NÃO GERE CÓDIGO DE EXEMPLO AINDA.
O objetivo é criar um esqueleto organizado para aprovação.
</CRITICAL_CONSTRAINT>
""",
            output_format="Markdown Outline (Hierarquia de Títulos #, ## e listas -)",
            input_data=json.dumps(solution_map, indent=2),
            input_tag="solution_map"
        )

        try:
            # Set max_tokens to 25%
            original_max = self.llm.max_tokens
            self.llm.model.model_kwargs["max_tokens"] = self.stage_4_max_tokens

            response, usage = self.llm.invoke(prompt)

            self.llm.model.model_kwargs["max_tokens"] = original_max
            duration = (datetime.now() - start_time).total_seconds()

            logger.info(f"Stage 4 complete: {usage.total_tokens} tokens")
            return StageResult(
                stage_id=4,
                stage_name="Document Structuring",
                output=response,
                tokens_used=usage,
                duration_seconds=duration,
                status='success'
            )

        except Exception as e:
            logger.error(f"Stage 4 failed: {str(e)}")
            duration = (datetime.now() - start_time).total_seconds()
            return StageResult(
                stage_id=4,
                stage_name="Document Structuring",
                output=None,
                tokens_used=TokenUsage(0, 0),
                duration_seconds=duration,
                status='failed',
                error=str(e)
            )

    def _stage_5_write_content(
        self,
        document_outline: str
    ) -> StageResult:
        """
        Stage 5: Write complete Markdown document.
        Uses 100% of token capacity and lower temperature for precision.
        """
        logger.info("Stage 5: Writing document content")
        start_time = datetime.now()
        self.llm.set_stage_context("stage-5")

        prompt = create_xml_prompt(
            task="Atue como um Redator Técnico Sênior. Escreva um Documento de Treinamento e Troubleshooting baseando-se ESTRITAMENTE no outline fornecido.",
            instructions="""<guidelines>
- Tom: Profissional e instrucional.
- Clareza: Explique o 'porquê'.
- Formatação: Use Markdown padrão.
</guidelines>

<ANTI_HALLUCINATION_PROTOCOL>
1. **NÃO INVENTE COMANDOS:** Se o outline diz "Executar contagem", e não há um comando explícito (como `bash run.sh`), assuma que é uma ação de interface (botão/menu). Descreva a ação generica (ex: "Execute a rotina de contagem").
2. **INTERFACE VISUAL:** Como você está processando texto de um vídeo, você não vê a tela. Quando o texto sugere uma ação visual (cliques, janelas, menus) que não pode ser descrita com precisão apenas pelo áudio:
   - **OBRIGATÓRIO:** Insira a tag `> 📸 **[INSERIR PRINT AQUI: Descrição da tela ou botão mencionado]**`
   - Não tente adivinhar o nome do menu se ele não foi dito.
3. **INCERTEZA:** Se um passo técnico faltar, escreva: "> ⚠️ **Nota:** Verifique a documentação oficial para o comando exato desta etapa."
</ANTI_HALLUCINATION_PROTOCOL>

<required_structure>
Siga estritamente o outline. Expanda os pontos, mas respeite o PROTOCOLO acima.
Não crie código (CLI/SQL) a menos que ele esteja explícito no input.
</required_structure>""",
            output_format="Gere o documento completo em Markdown AGORA.",
            input_data=document_outline,
            input_tag="document_outline"
        )

        try:
            # Set max_tokens to 100% (64k or model max)
            original_max = self.llm.max_tokens
            self.llm.model.model_kwargs["max_tokens"] = self.stage_5_max_tokens

            # Lower temperature to 0.3 for technical precision
            response, usage = self.llm.invoke(prompt, temperature=0.3)

            self.llm.model.model_kwargs["max_tokens"] = original_max
            duration = (datetime.now() - start_time).total_seconds()

            logger.info(
                f"Stage 5 complete: {usage.total_tokens} tokens, "
                f"{len(response)} chars"
            )

            return StageResult(
                stage_id=5,
                stage_name="Content Writing",
                output=response,
                tokens_used=usage,
                duration_seconds=duration,
                status='success'
            )

        except Exception as e:
            logger.error(f"Stage 5 failed: {str(e)}")
            duration = (datetime.now() - start_time).total_seconds()
            return StageResult(
                stage_id=5,
                stage_name="Content Writing",
                output=None,
                tokens_used=TokenUsage(0, 0),
                duration_seconds=duration,
                status='failed',
                error=str(e)
            )

    def _stage_6_generate_outputs(
        self,
        execution_id: str,
        markdown_content: str,
        output_bucket: str
    ) -> Tuple[str, str]:
        """
        Stage 6: Generate and upload Markdown + DOCX.
        """
        logger.info("Stage 6: Generating output files")

        # Save Markdown
        md_key = f"{execution_id}/document.md"
        md_uri = f"s3://{output_bucket}/{md_key}"

        self.s3.put_object(
            Bucket=output_bucket,
            Key=md_key,
            Body=markdown_content.encode('utf-8'),
            ContentType='text/markdown',
            Metadata={
                'execution_id': execution_id,
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'content_length': str(len(markdown_content))
            }
        )
        logger.info(f"Markdown saved: {md_uri}")

        # Convert to DOCX
        docx_buffer = self._markdown_to_docx(markdown_content)

        # Save DOCX
        docx_key = f"{execution_id}/document.docx"
        docx_uri = f"s3://{output_bucket}/{docx_key}"

        self.s3.put_object(
            Bucket=output_bucket,
            Key=docx_key,
            Body=docx_buffer.getvalue(),
            ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            Metadata={
                'execution_id': execution_id,
                'generated_at': datetime.now(timezone.utc).isoformat()
            }
        )
        logger.info(f"DOCX saved: {docx_uri}")

        return md_uri, docx_uri

    def _markdown_to_docx(self, markdown_content: str) -> io.BytesIO:
        """Convert Markdown to DOCX using python-docx."""
        doc = Document()
        lines = markdown_content.split('\n')
        in_code_block = False
        code_block_lines = []

        for line in lines:
            if line.strip().startswith('```'):
                if in_code_block:
                    code_text = '\n'.join(code_block_lines)
                    p = doc.add_paragraph(code_text)
                    p.style = 'Intense Quote'
                    code_block_lines = []
                    in_code_block = False
                else:
                    in_code_block = True
                continue

            if in_code_block:
                code_block_lines.append(line)
                continue

            if line.startswith('# '):
                doc.add_heading(line[2:], level=1)
            elif line.startswith('## '):
                doc.add_heading(line[3:], level=2)
            elif line.startswith('### '):
                doc.add_heading(line[4:], level=3)
            elif line.strip().startswith('- ') or line.strip().startswith('* '):
                doc.add_paragraph(line.strip()[2:], style='List Bullet')
            elif re.match(r'^\d+\. ', line.strip()):
                text = re.sub(r'^\d+\. ', '', line.strip())
                doc.add_paragraph(text, style='List Number')
            elif line.strip().startswith('>'):
                doc.add_paragraph(line.strip()[1:].strip(), style='Quote')
            elif line.strip():
                p = doc.add_paragraph()
                self._add_formatted_text(p, line)

        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer

    def _add_formatted_text(self, paragraph, text: str):
        """Add text with inline formatting."""
        paragraph.add_run(text)

    def _merge_outlines(self, outlines: List[str]) -> str:
        """Merge multiple outlines into one."""
        merged = "# Merged Outline from Multiple Chunks\n\n"
        for i, outline in enumerate(outlines):
            merged += f"## Part {i+1}\n\n{outline}\n\n"
        return merged

    def _load_transcription(self, s3_uri: str) -> Dict[str, Any]:
        """Load transcription JSON from S3."""
        from transcription_parser import parse_s3_uri, load_transcription_from_s3
        bucket, key = parse_s3_uri(s3_uri)
        return load_transcription_from_s3(self.s3, bucket, key)