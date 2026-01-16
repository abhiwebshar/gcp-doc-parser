# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/claude-code) when working with this repository.

## Project Overview

GCP Document Parser converts documents (PDF, Excel, Word, PowerPoint) to Markdown using Google Cloud's managed services. It provides two approaches:

1. **RAG Engine LLM Parser** (`test_llm_parser.py`) - Uses Vertex AI RAG Engine with Gemini for PDF/image parsing
2. **Document AI Layout Parser** (`layout_parser.py`) - Uses Document AI's Gemini-powered Layout Parser for multi-format support

## Build and Run Commands

```bash
# Setup virtual environment (using uv - faster)
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Or using pip
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Authentication (required before running scripts)
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT

# Option 1: RAG Engine LLM Parser (PDF only)
# First configure PROJECT_ID, BUCKET, INPUT_GCS_URI in test_llm_parser.py
python test_llm_parser.py

# Option 2: Document AI Layout Parser (multi-format)
# First create a processor
python layout_parser.py --setup
python layout_parser.py --list-processors

# Then process documents (update PROCESSOR_ID in script or use --processor-id)
python layout_parser.py --file document.pdf
python layout_parser.py --file spreadsheet.xlsx
python layout_parser.py --file presentation.pptx --processor-id abc123
```

## Architecture

### RAG Engine Approach (Hacky)
```
PDF → RAG Engine → [Gemini LLM Parser] → Chunks → retrieve_query() → Combine → Markdown
```
- Uploads doc to RAG corpus with LLM parsing enabled
- Retrieves all chunks via similarity search
- Combines chunks with deduplication into final markdown
- Only supports PDF + images

### Document AI Approach (Proper)
```
Any Format → Document AI Layout Parser → Structured JSON → Convert → Markdown
```
- Sends document to Layout Parser processor (Gemini v1.4+ under the hood)
- Receives structured JSON with blocks (text, tables, lists)
- Converts to markdown format
- Supports PDF, DOCX, XLSX, PPTX, HTML

## Key Configuration Points

Both scripts require configuration at the top of the file:

```python
# test_llm_parser.py
PROJECT_ID = "your-project"
BUCKET = "your-bucket"
INPUT_GCS_URI = "gs://your-bucket/path/to/document.pdf"

# layout_parser.py
PROJECT_ID = "your-project"
LOCATION = "us"  # or "eu"
BUCKET = "your-bucket"
PROCESSOR_ID = "abc123"  # from --setup or REST API
```

## Required GCP APIs and Permissions

```bash
# For RAG Engine
gcloud services enable aiplatform.googleapis.com

# For Document AI
gcloud services enable documentai.googleapis.com

# Grant RAG service account bucket access (Option 1 only)
PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format="value(projectNumber)")
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-vertex-rag.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

## Important Implementation Details

- **PDF page limit**: Document AI online processing has 30-page limit. `layout_parser.py` auto-splits larger PDFs using pypdf into 25-page chunks.
- **REST API usage**: `layout_parser.py` uses REST API directly (via `gcloud auth print-access-token`) rather than Python SDK due to credential caching issues with the SDK.
- **Chunk deduplication**: `test_llm_parser.py` includes logic to remove overlapping content when combining RAG chunks back into a single document.
- **IAM propagation**: After granting IAM roles, wait 2-5 minutes for permissions to propagate before retrying.

## File Format Support

| Format | RAG Engine | Document AI |
|--------|------------|-------------|
| PDF    | ✅         | ✅          |
| Excel  | ❌         | ✅          |
| Word   | ❌         | ✅          |
| PowerPoint | ❌     | ✅          |
| Images | ✅         | ✅          |
| HTML   | ❌         | ✅          |
