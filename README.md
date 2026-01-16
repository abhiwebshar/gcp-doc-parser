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
git clone https://github.com/abhiwebshar/gcp-doc-parser.git
cd gcp-doc-parser

# Setup (choose one)
# Option A: Using uv (faster)
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Option B: Using pip
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Then follow "How to Reproduce" section below
```

## How to Reproduce (Step-by-Step)

### Prerequisites

1. GCP Project with billing enabled
2. `gcloud` CLI installed and authenticated
3. Python 3.10+
4. A test document (PDF, Excel, Word, or PowerPoint)

### Authentication Setup (ADC)

The scripts use [Application Default Credentials (ADC)](https://cloud.google.com/docs/authentication/application-default-credentials). Set up once:

```bash
# Login with your Google account
gcloud auth login

# Set up ADC for local development
gcloud auth application-default login

# Set your default project
gcloud config set project YOUR_PROJECT

# Verify
gcloud auth list
gcloud config get-value project
```

**Environment variables** (optional, scripts auto-detect from gcloud):

```bash
# Only needed if not using gcloud config
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"  # If using service account
```

**For production/CI**, use a service account:

```bash
# Create service account
gcloud iam service-accounts create doc-parser \
  --display-name="Document Parser Service Account"

# Grant roles
gcloud projects add-iam-policy-binding YOUR_PROJECT \
  --member="serviceAccount:doc-parser@YOUR_PROJECT.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding YOUR_PROJECT \
  --member="serviceAccount:doc-parser@YOUR_PROJECT.iam.gserviceaccount.com" \
  --role="roles/documentai.editor"

gcloud projects add-iam-policy-binding YOUR_PROJECT \
  --member="serviceAccount:doc-parser@YOUR_PROJECT.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Download key (for CI/CD)
gcloud iam service-accounts keys create key.json \
  --iam-account=doc-parser@YOUR_PROJECT.iam.gserviceaccount.com

# Use in CI
export GOOGLE_APPLICATION_CREDENTIALS="./key.json"
```

### Option 1: RAG Engine LLM Parser (PDF → Markdown)

```bash
# 1. Enable Vertex AI API
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT

# 2. Create a GCS bucket (or use existing)
gsutil mb -p YOUR_PROJECT gs://YOUR_BUCKET

# 3. Grant RAG service account access
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT --format="value(projectNumber)")
gcloud storage buckets add-iam-policy-binding gs://YOUR_BUCKET \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-vertex-rag.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# 4. Upload your test PDF
gsutil cp your_document.pdf gs://YOUR_BUCKET/test_docs/

# 5. Configure the script
# Edit test_llm_parser.py:
#   PROJECT_ID = "YOUR_PROJECT"
#   BUCKET = "YOUR_BUCKET"
#   INPUT_GCS_URI = "gs://YOUR_BUCKET/test_docs/your_document.pdf"

# 6. Run
python test_llm_parser.py

# Output: parsed_output.md (local) + gs://YOUR_BUCKET/parsed_output/your_document.md
```

### Option 2: Document AI Layout Parser (Excel/Word/PPT → Markdown)

```bash
# 1. Enable Document AI API
gcloud services enable documentai.googleapis.com --project=YOUR_PROJECT

# 2. Grant yourself Document AI admin role
gcloud projects add-iam-policy-binding YOUR_PROJECT \
  --member="user:$(gcloud config get-value account)" \
  --role="roles/documentai.admin" \
  --condition=None

# 3. Create a Layout Parser processor (via REST API)
# NOTE: IAM permissions can take 2-5 minutes to propagate. If you get permission errors, wait and retry.
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://us-documentai.googleapis.com/v1/projects/YOUR_PROJECT/locations/us/processors" \
  -d '{
    "displayName": "layout-parser",
    "type": "LAYOUT_PARSER_PROCESSOR"
  }'

# Response looks like:
# {
#   "name": "projects/123456789/locations/us/processors/abc123def456",
#   "type": "LAYOUT_PARSER_PROCESSOR",
#   ...
# }
# The processor ID is the last part: "abc123def456"

# 4. Configure the script
# Edit layout_parser.py:
#   PROJECT_ID = "YOUR_PROJECT"
#   PROCESSOR_ID = "abc123def456"  # From step 3

# 5. Run with your document
python layout_parser.py --file your_spreadsheet.xlsx
# Or for PDF:
python layout_parser.py --file your_document.pdf

# Output: your_spreadsheet.md (local)
```

### Testing with Sample Documents

Use any document you have. Good test cases:
- **PDF with tables** - Tests table extraction
- **Multi-page PDF** - Tests chunking/splitting (>30 pages triggers auto-split)
- **Excel spreadsheet** - Tests XLSX support (Layout Parser only)
- **Word document** - Tests DOCX support (Layout Parser only)

### Verify Output

```bash
# Check the generated markdown
cat parsed_output.md | head -100

# Look for:
# - Proper headings (#, ##, ###)
# - Tables in markdown format (| col1 | col2 |)
# - Lists preserved (-, *, 1.)
# - No garbled text or broken structure
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

## Troubleshooting

### "Permission denied" errors

**IAM propagation delay:** After granting roles, wait 2-5 minutes for permissions to propagate. Then retry.

**Wrong project:** Verify you're using the correct project:
```bash
gcloud config get-value project
```

**ADC not set up:** Run:
```bash
gcloud auth application-default login
```

### "API not enabled" errors

Enable the required APIs:
```bash
# For RAG Engine
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT

# For Document AI
gcloud services enable documentai.googleapis.com --project=YOUR_PROJECT
```

### "0 files imported" (RAG Engine)

The RAG service account needs access to your GCS bucket:
```bash
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT --format="value(projectNumber)")
gcloud storage buckets add-iam-policy-binding gs://YOUR_BUCKET \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-vertex-rag.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

### "Document pages exceed limit" (Document AI)

Online processing limit is 30 pages. The script auto-splits PDFs >30 pages, but if you see this error:
- Ensure you're using `layout_parser.py` (has auto-split)
- For very large docs, use batch processing

### "Unsupported MIME type"

Check file format support:
- **LLM Parser:** PDF, PNG, JPEG, WebP, HEIC, HEIF only
- **Layout Parser:** PDF, DOCX, XLSX, PPTX, HTML

### Still stuck?

1. Check [Vertex AI docs](https://cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/llm-parser)
2. Check [Document AI docs](https://cloud.google.com/document-ai/docs/layout-parse-chunk)
3. Open an issue on this repo

## References

- [Vertex AI RAG Engine LLM Parser](https://cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/llm-parser)
- [Document AI Layout Parser](https://cloud.google.com/document-ai/docs/layout-parse-chunk)
- [LlamaParse](https://docs.llamaindex.ai/en/stable/llama_cloud/llama_parse/)
- [Reducto](https://reducto.ai/)

## License

MIT - Use freely, no warranty.
