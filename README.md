# Vertex AI RAG Engine LLM Parser - Document to Markdown Conversion

## Goal

Convert PDF documents to high-fidelity Markdown files using GCP's native Vertex AI services - similar to LlamaParse but within GCP ecosystem.

## Overview

This project uses **Vertex AI RAG Engine with LLM Parser** to:
1. Parse PDFs using Gemini models (intelligent understanding of tables, structure, formatting)
2. Retrieve the parsed content
3. Output as Markdown files to GCS

### Key Insight

The RAG Engine's LLM Parser uses Gemini to parse documents **before** chunking. We leverage this parsing capability, retrieve all chunks, and combine them back into full Markdown documents.

## Why This Approach

| Approach | Pros | Cons |
|----------|------|------|
| **LlamaParse** | High fidelity, many formats | External service, separate billing |
| **Gemini Direct** | Full control, full documents | Must handle retries, rate limits yourself |
| **Vertex AI RAG Engine LLM Parser** | Managed service, handles retries/rate limits, same GCP billing | Outputs chunks (combined back to full doc) |
| **Vertex AI Batch Prediction** | Full documents, managed | More setup, async only |

We chose **Vertex AI RAG Engine** because:
- All infrastructure already on GCP
- Same billing account (uses existing GCP credits)
- Managed service handles rate limits and retries
- Uses Gemini models under the hood
- Can retrieve and combine chunks to reconstruct full documents

### Limitation: Chunking

RAG Engine chunks the parsed content. We work around this by:
1. Using large chunk sizes (4096 tokens) to minimize fragmentation
2. Retrieving all chunks via `retrieval_query`
3. **Deduplicating** overlapping content (line-based dedup)
4. Combining chunks into a single clean Markdown file

The script automatically:
- Removes duplicate lines caused by chunk overlap
- Strips markdown code fences (`\`\`\`markdown`) that the LLM parser sometimes adds
- Produces a clean, deduplicated markdown file

## Quick Start (TL;DR)

```bash
# 1. Clone and setup
cd gcp_llm_parser
uv venv && source .venv/bin/activate
uv pip install google-cloud-aiplatform google-cloud-storage

# 2. Grant RAG service account access (one-time)
gcloud storage buckets add-iam-policy-binding gs://YOUR_BUCKET \
  --member="serviceAccount:service-PROJECT_NUMBER@gcp-sa-vertex-rag.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# 3. Upload PDF and run
gsutil cp document.pdf gs://YOUR_BUCKET/test_docs/
python test_llm_parser.py

# Output: parsed_output.md (local) + gs://YOUR_BUCKET/parsed_output/document.md
```

## Prerequisites

- GCP Project with Vertex AI API enabled
- GCS bucket for input/output
- Python 3.10+
- `gcloud` CLI configured

## Setup

### 1. Grant RAG Service Account Access to GCS

The Vertex AI RAG service account needs read/write access to your GCS bucket:

```bash
# Find your project number
gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"

# Grant access (replace PROJECT_NUMBER and BUCKET_NAME)
gcloud storage buckets add-iam-policy-binding gs://YOUR_BUCKET \
  --member="serviceAccount:service-PROJECT_NUMBER@gcp-sa-vertex-rag.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

For our project:
```bash
gcloud storage buckets add-iam-policy-binding gs://trenta_llmops \
  --member="serviceAccount:service-798248085248@gcp-sa-vertex-rag.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

### 2. Install Dependencies

```bash
# Using uv (recommended)
uv venv
source .venv/bin/activate
uv pip install google-cloud-aiplatform google-cloud-storage

# Or using pip
pip install google-cloud-aiplatform google-cloud-storage
```

### 3. Configure the Script

Edit `test_llm_parser.py` and set:

```python
PROJECT_ID = "compliancebotqa"      # Your GCP project
LOCATION = "us-central1"             # Region
BUCKET = "trenta_llmops"             # Your GCS bucket
INPUT_GCS_URI = f"gs://{BUCKET}/test_docs/your_file.pdf"
```

## Usage

### Upload a Document

```bash
gsutil cp your_document.pdf gs://trenta_llmops/test_docs/
```

### Run Full Pipeline

```bash
python test_llm_parser.py
```

This will:
1. Create a new RAG corpus
2. Import the document with LLM parsing
3. Display parsed chunks in terminal
4. Save combined markdown locally (`parsed_output.md`)
5. Save to GCS (`gs://trenta_llmops/parsed_output/`)

### List Existing Corpora

```bash
python test_llm_parser.py --list-corpora
```

### Inspect Existing Corpus

```bash
python test_llm_parser.py --inspect-only --corpus 'projects/798248085248/locations/us-central1/ragCorpora/CORPUS_ID'
```

### Custom Query for Retrieval

```bash
python test_llm_parser.py --inspect-only --corpus 'CORPUS_NAME' --query 'security requirements'
```

## Configuration Options

### LLM Parser Settings

In `test_llm_parser.py`:

```python
MODEL_ID = "gemini-2.0-flash"  # Or gemini-2.5-pro, gemini-2.5-flash

CUSTOM_PROMPT = """Convert this document to well-structured markdown.
Preserve all:
- Headings and hierarchy
- Tables (use markdown table format)
- Lists and bullet points
- Code blocks
- Important formatting

Output clean, readable markdown only."""
```

### Chunking Settings

```python
transformation_config = rag.TransformationConfig(
    chunking_config=rag.ChunkingConfig(
        chunk_size=4096,   # Max practical size (embedding limit ~2048, but we don't need embeddings)
        chunk_overlap=100, # Minimal overlap since we combine chunks anyway
    ),
)
```

**Note:** For document-to-markdown conversion (not RAG retrieval), use the **largest chunk size** to minimize fragmentation. The embedding model limit is 2048 tokens, but since we're just extracting text, larger may work.

### Retrieval Settings

```python
rag_retrieval_config = rag.RagRetrievalConfig(
    top_k=50,  # Number of chunks to retrieve
    filter=rag.Filter(vector_distance_threshold=10.0),  # Higher = more inclusive
)
```

## Supported File Types

- `application/pdf`
- `image/png`
- `image/jpeg`
- `image/webp`
- `image/heic`
- `image/heif`

**Note:** For DOCX/PPTX, convert to PDF first.

## Supported Models

- Gemini 2.0 Flash
- Gemini 2.5 Flash / Flash-Lite
- Gemini 2.5 Pro
- Gemini 3 Flash / Pro (preview)

## Test Results

### Test Document
- **File:** `ACME_Corp_PCI_ROC_EXTRACTED.pdf` (5.9 MB PCI DSS compliance report)
- **Result:** 31 chunks successfully parsed

### What LLM Parser Captured
- ✅ Complex multi-column tables with proper markdown formatting
- ✅ Heading hierarchy preserved
- ✅ Checkbox symbols (☐, ☑, ☒)
- ✅ Bullet points and nested lists
- ✅ Page references
- ✅ Document structure and sections

### Sample Output

```markdown
# PCI Security Standards Council

## Summary of Assessment Findings (check one)

| PCI DSS Requirements and Testing Procedures | Reporting Instruction | Reporting Details | In Place | N/A |
|---------------------------------------------|----------------------|-------------------|----------|-----|
| 1.2.2 Secure and synchronize router config  | Describe how...      | N/A - Since...    | ☐        | ☑   |
```

## Cost Estimation

Formula:
```
cost = num_files * pages_per_file * (input_tokens * input_price + output_tokens * output_price)
```

Example (Gemini 2.0 Flash-Lite @ $0.075/1M input, $0.30/1M output):
```
1,000 PDFs × 50 pages × (600 input + 100 output tokens) ≈ $3.75
```

## Architecture

### Pipeline (Behind the Scenes)

```
PDF Document
    │
    ▼
┌─────────────────────────────────────┐
│  1. LLM PARSER (Gemini)             │  ← Parsing happens FIRST
│     - Reads PDF visually            │
│     - Understands tables, structure │
│     - Outputs clean Markdown        │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. CHUNKING (Transformation)       │  ← Applied to parsed Markdown
│     - Splits MD into chunks         │
│     - We use large chunks (4096)    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  3. EMBEDDING                       │  ← We don't care about this
│     - Creates vectors for retrieval │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  4. RAG CORPUS                      │  ← Stored here
│     - Chunks with embeddings        │
└─────────────────────────────────────┘
```

**Key insight:** The LLM Parser runs **before** chunking. So chunks already contain nicely parsed Markdown. We just need to retrieve them and combine.

### Our Workflow

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  GCS Bucket     │────▶│  Vertex AI RAG       │────▶│  GCS Bucket     │
│  (input PDFs)   │     │  Engine + LLM Parser │     │  (output .md)   │
└─────────────────┘     │  (Gemini 2.0 Flash)  │     └─────────────────┘
                        └──────────────────────┘
                                  │
                        retrieval_query()
                                  │
                                  ▼
                        ┌──────────────────────┐
                        │  Combine + Dedup     │
                        │  → Clean Markdown    │
                        └──────────────────────┘
```

## Files

```
gcp_llm_parser/
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── test_llm_parser.py        # Main script
├── parsed_output.md          # Local output (generated)
└── notes.md                  # Research notes
```

## Troubleshooting

### "Permission Denied" on import

Grant the RAG service account access to your bucket:
```bash
gcloud storage buckets add-iam-policy-binding gs://YOUR_BUCKET \
  --member="serviceAccount:service-PROJECT_NUMBER@gcp-sa-vertex-rag.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

### 0 files imported

- Check the service account has read access to source files
- Verify the file exists at the GCS URI
- Check file format is supported (PDF, PNG, JPEG, etc.)

### Empty chunks retrieved

- Increase `top_k` in retrieval config
- Increase `vector_distance_threshold`
- Wait longer for processing (large files take time)

## References

- [Vertex AI RAG Engine LLM Parser Docs](https://cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/llm-parser)
- [RAG Engine API Reference](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/rag-api)
- [RAG Engine Overview](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/rag-overview)
- [Vertex AI Pricing](https://cloud.google.com/vertex-ai/pricing)

## Option 2: Document AI Layout Parser (Excel Support)

For Excel/Word/PowerPoint support, use **Document AI Layout Parser** instead of LLM Parser.

### Supported Formats

| Format | Supported | Size Limit |
|--------|-----------|------------|
| PDF | ✅ | 1 GB / 500 pages |
| DOCX (Word) | ✅ | 20 MB |
| PPTX (PowerPoint) | ✅ | 20 MB |
| **XLSX (Excel)** | ✅ | 5 million cells |
| XLSM (Excel+macros) | ✅ | 5 million cells |
| HTML | ✅ | 20 MB |

### Setup

```bash
# 1. Enable Document AI API
gcloud services enable documentai.googleapis.com --project=compliancebotqa

# 2. Grant Document AI admin role
gcloud projects add-iam-policy-binding compliancebotqa \
  --member="user:$(gcloud config get-value account)" \
  --role="roles/documentai.admin" \
  --condition=None

# 3. Create a Layout Parser processor
python layout_parser.py --setup

# 4. Process files
python layout_parser.py --file spreadsheet.xlsx --processor-id YOUR_PROCESSOR_ID
```

### Comparison: LLM Parser vs Layout Parser

| Feature | LLM Parser | Document AI Layout Parser |
|---------|------------|---------------------------|
| Excel support | ❌ | ✅ |
| Word support | ❌ | ✅ |
| PowerPoint | ❌ | ✅ |
| PDF | ✅ | ✅ |
| Images | ✅ | ✅ |
| Custom prompt | ✅ | ❌ |
| Gemini-powered | ✅ | ✅ (v1.4+) |

**Recommendation:**
- Use **LLM Parser** for PDFs with custom parsing needs
- Use **Layout Parser** for Excel/Word/PowerPoint files

## Next Steps

- [ ] Batch processing for multiple files
- [ ] Webhook notification when processing complete
- [ ] Custom parsing prompts per document type
- [ ] Integration with downstream RAG pipeline
