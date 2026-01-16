# Project Notes

## Goal
- Convert documents (PDF, Excel, etc.) to high-fidelity Markdown
- Want **managed service** (like CloudSQL vs self-hosted Postgres)
- Use GCP credits, same billing account

## LlamaParse
- Any format to markdown with high fidelity conversion
- Handles PDFs, Word docs, PowerPoints, etc.
- Preserves tables, figures, charts, and complex layouts
- API-based service by LlamaIndex
- Good for RAG pipelines

## Vertex AI RAG Engine - LLM Parser
- Google's native solution using Gemini models
- Uses LLMs to understand semantic content, extract info, summarize, analyze visuals

### Supported Models
- Gemini 2.0 Flash, 2.5 Pro/Flash/Flash-Lite, 3 Flash/Pro (preview)

### Supported Formats (LLM Parser - high fidelity)
- ✅ PDF
- ✅ Images (PNG, JPEG, WebP, HEIC, HEIF)
- ❌ Excel (.xlsx, .xls) - NOT SUPPORTED
- ❌ CSV - NOT SUPPORTED
- ❌ Word (.docx) - only via default parser (lower quality)
- ❌ PowerPoint (.pptx) - only via default parser (lower quality)

### Limitation
- Excel NOT supported by LLM Parser
- Only PDF + images

---

## Document AI Layout Parser (BETTER OPTION FOR EXCEL)

**This is the managed solution like CloudSQL!**

### Supported Formats (GA)
- ✅ PDF (1 GB / 500 pages)
- ✅ DOCX - Word (20 MB)
- ✅ PPTX - PowerPoint (20 MB)
- ✅ **XLSX - Excel** (5 million cells)
- ✅ XLSM - Excel with macros
- ✅ HTML (20 MB)

### Features
- Gemini-powered (v1.4/v1.5 uses Gemini behind the scenes)
- Extracts text, tables, lists
- Context-aware chunking
- Integrates with RAG Engine

### How to Use with RAG Engine
```python
response = rag.import_files(
    corpus_name=corpus_name,
    paths=paths,
    layout_parser=rag.LayoutParserConfig(
        processor_name="projects/{PROJECT_ID}/locations/us/processors/{processor_id}",
        max_parsing_requests_per_min=120,
    ),
)
```

### Limits
| Mode | Size | Pages | Use Case |
|------|------|-------|----------|
| Online | 20 MB | 30 max | Small docs, real-time |
| Batch | 1 GB | 500 max | Large docs, async |
| Split PDF | Any | Any | Workaround for online limit |

### Processor ID (compliancebotqa)
- `7dfc4ba025057d4c` (Layout Parser)

### Batch Processing (for very large files)
When to use:
- Files > 20 MB
- PDFs > 500 pages (can't split effectively)
- Processing many files at once

How it works:
1. Upload files to GCS input bucket
2. Submit batch job (async)
3. Job processes files in background
4. Results written to GCS output bucket

```python
# Batch processing example
from google.cloud import documentai_v1 as documentai

# Input from GCS
input_config = documentai.BatchDocumentsInputConfig(
    gcs_documents=documentai.GcsDocuments(
        documents=[
            documentai.GcsDocument(
                gcs_uri="gs://bucket/input/large.pdf",
                mime_type="application/pdf"
            )
        ]
    )
)

# Output to GCS
output_config = documentai.DocumentOutputConfig(
    gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
        gcs_uri="gs://bucket/output/"
    )
)

# Submit batch job
operation = client.batch_process_documents(
    name=processor_name,
    input_documents=input_config,
    document_output_config=output_config,
)

# Wait for completion (or poll status)
result = operation.result(timeout=3600)
```

### Current Solution: PDF Splitting
For PDFs 30-500 pages, we split into 25-page chunks:
- Automatic in `layout_parser.py`
- Each chunk processed via online API
- Results combined into single markdown

---

## Comparison: LLM Parser vs Layout Parser

| Feature | LLM Parser | Document AI Layout Parser |
|---------|------------|---------------------------|
| Excel support | ❌ | ✅ |
| Word support | ❌ | ✅ |
| PowerPoint | ❌ | ✅ |
| PDF | ✅ | ✅ |
| Images | ✅ | ✅ |
| Custom prompt | ✅ | ❌ |
| Gemini-powered | ✅ | ✅ (v1.4+) |
| RAG Engine integration | ✅ | ✅ |
| Managed service | ✅ | ✅ |

**Recommendation:** Use **Document AI Layout Parser** for Excel/Word/PPT support

### Capabilities
- Links section titles across slides to related content
- Associates columns/headers in large tables
- Follows flowchart logic to extract action sequences
- Interprets graphs and extracts data points

### Cost Example
- 1,000 PDFs × 50 pages × ~700 tokens = ~$3.75 (Gemini 2.0 Flash-Lite)

### Configuration
- Model name (resource path)
- Custom parsing prompt (optional)
- Max parsing requests per minute (optional)

### Docs
- https://cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/llm-parser
