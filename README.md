# GCP Document Parser

Convert documents (PDF, Excel, Word, PowerPoint) to Markdown using Google Cloud's managed services.

## The Problem

You have documents. You need structured text (Markdown) for RAG pipelines, search indexing, or LLM context. Sounds simple, but it's not.

## Evolution of Document Parsing

### Era 1: Traditional OCR & Rule-Based Parsers
- **Tools:** Tesseract, Apache Tika, PyPDF
- **How it works:** OCR + heuristics to extract text
- **Problem:** No semantic understanding. Tables become jumbled text. Headers lose hierarchy. Complex layouts break completely.

### Era 2: Document AI (ML-Based)
- **Tools:** Google Document AI, Azure Document Intelligence, AWS Textract
- **How it works:** ML models trained on document layouts
- **Better:** Understands tables, forms, structure
- **Problem:** Pre-trained on specific document types. Custom documents need fine-tuning. Still struggles with nuanced formatting.

### Era 3: LLM-Powered Parsing
- **Tools:** LlamaParse, Reducto, direct Gemini/GPT-4V
- **How it works:** Send document image/PDF to LLM, ask it to output Markdown
- **Best quality:** LLMs understand context, can follow complex layouts, handle edge cases
- **Problem:** DIY is painful (see below)

## Pain Points of DIY LLM Parsing

If you just call Gemini/GPT-4 directly for document parsing:

| Pain Point | Description |
|------------|-------------|
| **Format conversion** | Must convert DOCX/XLSX/PPTX → PDF → images. Each step loses fidelity. |
| **Rate limits** | LLM APIs have strict rate limits. Parsing 1000 docs? Good luck. |
| **Shared quota** | Document parsing eats the same rate limits as your production LLM calls. |
| **Retries** | API failures happen. You need exponential backoff, dead letter queues. |
| **Cost tracking** | Hard to separate parsing costs from other LLM usage. |
| **Chunking large docs** | 100-page PDF won't fit in context. Need to split, process, reassemble. |

## The Managed Service Philosophy

Think **CloudSQL vs self-hosted Postgres**:

| DIY (Self-hosted) | Managed Service |
|-------------------|-----------------|
| Full control | Less control |
| Handle backups yourself | Automatic backups |
| Manage scaling | Auto-scaling |
| Debug failures at 3am | SLA-backed reliability |
| Your engineers' time | Their engineers' time |

**For document parsing, you want a managed service** that handles:
- Rate limiting & retries
- Format conversion
- Scaling
- Separate billing from your main LLM usage

## Solutions in This Repo

### Option 1: RAG Engine LLM Parser (Hacky but Works)

**The insight:** Vertex AI RAG Engine has an LLM Parser that uses Gemini to parse documents *before* chunking. We can:
1. Upload docs → RAG Engine parses them with Gemini
2. Retrieve the parsed chunks
3. Combine chunks back into full Markdown

**Pros:**
- Managed Gemini parsing (retries, rate limits handled)
- Uses GCP credits
- Custom prompts supported

**Cons:**
- Designed for RAG, not document export
- Must work around chunking (retrieve all, deduplicate, combine)
- Only supports PDF + images

**Use:** `test_llm_parser.py`

### Option 2: Document AI Layout Parser (Proper Solution)

**The insight:** Document AI's Layout Parser now uses Gemini (v1.4+) under the hood. It's the "proper" managed service for document parsing.

**Pros:**
- Supports Excel, Word, PowerPoint, HTML, PDF
- Truly managed (not a hack)
- Batch processing for large volumes
- Auto-splits large PDFs

**Cons:**
- No custom prompts (fixed parsing behavior)
- Requires processor setup

**Use:** `layout_parser.py`

## Quick Start

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/gcp-doc-parser.git
cd gcp-doc-parser

# Setup
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Configure (edit PROJECT_ID, BUCKET in scripts)

# Option 1: RAG Engine (PDF only, custom prompts)
python test_llm_parser.py --file document.pdf

# Option 2: Document AI (Excel/Word/PPT support)
python layout_parser.py --file spreadsheet.xlsx
```

## Comparison

| Feature | LLM Parser (RAG Engine) | Layout Parser (Document AI) |
|---------|-------------------------|----------------------------|
| PDF | ✅ | ✅ |
| Excel | ❌ | ✅ |
| Word | ❌ | ✅ |
| PowerPoint | ❌ | ✅ |
| Images | ✅ | ✅ |
| Custom prompts | ✅ | ❌ |
| Truly managed | ⚠️ Hacky | ✅ |
| Large PDFs | Via chunking | Auto-split or batch |

## Architecture

### Option 1: RAG Engine (Hacky)

```
PDF → RAG Engine → [Gemini LLM Parser] → Chunks → retrieve_query() → Combine → Markdown
                         ↑
                   (parsing happens here,
                    before chunking)
```

### Option 2: Document AI (Proper)

```
Any Format → Document AI Layout Parser → Structured JSON → Convert → Markdown
                      ↑
                (Gemini-powered v1.4+)
```

## Cost

Both use GCP credits. Rough estimate for Gemini 2.0 Flash-Lite:

```
1,000 PDFs × 50 pages × 700 tokens ≈ $3.75
```

## Future Work / TODOs

- [ ] **Temporal/Airflow orchestration** - Build a proper parsing service with:
  - Job queuing
  - Retry policies
  - Progress tracking
  - Webhook notifications

  *Trade-off: Significant engineering effort + ongoing maintenance vs. using external managed service like LlamaParse*

- [ ] **Batch processing** - Process folders of documents in parallel
- [ ] **Format detection** - Auto-detect and route to appropriate parser
- [ ] **Quality scoring** - Compare parsed output against source

## When to Use What

| Scenario | Recommendation |
|----------|----------------|
| PDF with complex tables, need custom output | LLM Parser (Option 1) |
| Excel/Word/PowerPoint files | Layout Parser (Option 2) |
| High volume, need reliability | Layout Parser + Batch mode |
| Prototype/exploration | Either works |
| Production service | Consider LlamaParse/Reducto OR build with Temporal |

## References

- [Vertex AI RAG Engine LLM Parser](https://cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/llm-parser)
- [Document AI Layout Parser](https://cloud.google.com/document-ai/docs/layout-parse-chunk)
- [LlamaParse](https://docs.llamaindex.ai/en/stable/llama_cloud/llama_parse/)
- [Reducto](https://reducto.ai/)

## License

MIT - Use freely, no warranty.
