"""
Test script: Vertex AI RAG Engine LLM Parser
Workflow: Upload doc -> LLM parse -> View/Extract parsed content -> Save as markdown

Usage:
    python test_llm_parser.py                    # Run full pipeline
    python test_llm_parser.py --inspect-only     # Just view parsed chunks from existing corpus
"""

from vertexai import rag
import vertexai
from google.cloud import storage
import time
import argparse

# ============ CONFIGURE THESE ============
PROJECT_ID = "compliancebotqa"
LOCATION = "us-central1"
BUCKET = "trenta_llmops"

INPUT_GCS_URI = f"gs://{BUCKET}/test_docs/ACME_Corp_PCI_ROC_EXTRACTED.pdf"
OUTPUT_PREFIX = "parsed_output/"

# LLM Parser config
MODEL_ID = "gemini-2.0-flash"
CUSTOM_PROMPT = """Convert this document to well-structured markdown.
Preserve all:
- Headings and hierarchy
- Tables (use markdown table format)
- Lists and bullet points
- Code blocks
- Important formatting

Output clean, readable markdown only."""

# ==========================================


def create_corpus(display_name: str) -> rag.RagCorpus:
    """Create a new RAG corpus"""
    corpus = rag.create_corpus(display_name=display_name)
    print(f"✓ Created corpus: {corpus.name}")
    return corpus


def import_with_llm_parser(corpus_name: str, gcs_uris: list[str]) -> None:
    """Import files with LLM parser enabled"""

    model_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/{MODEL_ID}"

    llm_parser_config = rag.LlmParserConfig(
        model_name=model_name,
        max_parsing_requests_per_min=60,
        custom_parsing_prompt=CUSTOM_PROMPT,
    )

    # Use maximum chunk size to minimize fragmentation
    # For document-to-markdown (not RAG retrieval), bigger = better
    # Embedding limit is 2048 tokens, but we don't care about embeddings here
    transformation_config = rag.TransformationConfig(
        chunking_config=rag.ChunkingConfig(
            chunk_size=4096,  # Try max - may be capped internally
            chunk_overlap=100,  # Minimal overlap since we combine anyway
        ),
    )

    print(f"Importing {len(gcs_uris)} files with LLM parser...")

    response = rag.import_files(
        corpus_name,
        gcs_uris,
        llm_parser=llm_parser_config,
        transformation_config=transformation_config,
    )
    print(f"✓ Import complete: {response.imported_rag_files_count} files imported")
    return response


def retrieve_and_display_chunks(corpus_name: str, query: str = " ") -> list[dict]:
    """
    Retrieve parsed chunks from corpus and display them.
    Uses a generic query to get chunks - adjust top_k for more results.
    """
    print(f"\n{'='*60}")
    print("RETRIEVING PARSED CHUNKS")
    print(f"{'='*60}\n")

    # Use RagRetrievalConfig for proper configuration
    rag_retrieval_config = rag.RagRetrievalConfig(
        top_k=50,  # Get up to 50 chunks
        filter=rag.Filter(vector_distance_threshold=10.0),  # High threshold = include more
    )

    response = rag.retrieval_query(
        rag_resources=[rag.RagResource(rag_corpus=corpus_name)],
        text=query,
        rag_retrieval_config=rag_retrieval_config,
    )

    chunks = []
    for i, context in enumerate(response.contexts.contexts):
        chunk_data = {
            "index": i + 1,
            "source": getattr(context, 'source_uri', 'unknown'),
            "text": context.text,
            "distance": getattr(context, 'distance', None),
        }
        chunks.append(chunk_data)

        # Display each chunk
        print(f"--- Chunk {i+1} ---")
        print(f"Source: {chunk_data['source']}")
        if chunk_data['distance']:
            print(f"Distance: {chunk_data['distance']:.4f}")
        print(f"Content:\n{context.text[:500]}{'...' if len(context.text) > 500 else ''}")
        print()

    print(f"{'='*60}")
    print(f"Total chunks retrieved: {len(chunks)}")
    print(f"{'='*60}\n")

    return chunks


def list_rag_files(corpus_name: str):
    """List all files in the corpus"""
    files = list(rag.list_files(corpus_name))
    print(f"\nFiles in corpus ({len(files)}):")
    for f in files:
        print(f"  - {f.display_name}")
        print(f"    Resource: {f.name}")
    return files


def list_corpora():
    """List all existing corpora"""
    corpora = list(rag.list_corpora())
    print(f"\nExisting corpora ({len(corpora)}):")
    for c in corpora:
        print(f"  - {c.display_name}: {c.name}")
    return corpora


def deduplicate_chunks(chunks: list[dict]) -> str:
    """
    Combine chunks while removing duplicate/overlapping content.
    Uses line-based deduplication to handle chunk overlaps.
    """
    if not chunks:
        return ""

    # Extract text from each chunk and clean up
    all_lines = []
    seen_lines = set()

    for chunk in chunks:
        text = chunk['text'].strip()
        # Remove markdown code fence if present (LLM parser sometimes wraps in ```markdown)
        if text.startswith('```markdown'):
            text = text[len('```markdown'):].strip()
        if text.endswith('```'):
            text = text[:-3].strip()

        # Split into lines and deduplicate
        for line in text.split('\n'):
            # Normalize line for comparison (strip whitespace)
            normalized = line.strip()
            # Skip empty lines for dedup check but keep them for formatting
            if not normalized:
                all_lines.append(line)
                continue
            # Skip if we've seen this line (handles overlap)
            if normalized in seen_lines:
                continue
            seen_lines.add(normalized)
            all_lines.append(line)

    return '\n'.join(all_lines)


def save_chunks_to_gcs(chunks: list[dict], bucket_name: str, blob_name: str):
    """Save combined chunks as markdown to GCS (deduplicated)"""
    combined = deduplicate_chunks(chunks)

    client = storage.Client(project=PROJECT_ID)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(combined, content_type="text/markdown")
    print(f"✓ Saved to gs://{bucket_name}/{blob_name}")


def save_chunks_locally(chunks: list[dict], filename: str):
    """Save deduplicated markdown locally"""
    combined = deduplicate_chunks(chunks)

    with open(filename, 'w') as f:
        f.write(combined)
    print(f"✓ Saved locally to {filename}")


def main():
    parser = argparse.ArgumentParser(description='Test Vertex AI RAG Engine LLM Parser')
    parser.add_argument('--inspect-only', action='store_true',
                        help='Only inspect existing corpus, do not create new one')
    parser.add_argument('--corpus', type=str, help='Existing corpus name to inspect')
    parser.add_argument('--list-corpora', action='store_true', help='List all corpora')
    parser.add_argument('--query', type=str, default=" ",
                        help='Query to use for retrieval (default: broad match)')
    args = parser.parse_args()

    # Initialize Vertex AI
    vertexai.init(project=PROJECT_ID, location=LOCATION)

    if args.list_corpora:
        list_corpora()
        return

    if args.inspect_only:
        if not args.corpus:
            print("Error: --corpus required with --inspect-only")
            print("Use --list-corpora to see available corpora")
            return
        # Just retrieve and display chunks from existing corpus
        list_rag_files(args.corpus)
        chunks = retrieve_and_display_chunks(args.corpus, args.query)
        save_chunks_locally(chunks, "parsed_output.md")
        return

    # Full pipeline: Create -> Import -> Retrieve -> Save
    print(f"\n{'='*60}")
    print("VERTEX AI RAG ENGINE - LLM PARSER TEST")
    print(f"Project: {PROJECT_ID}")
    print(f"Input: {INPUT_GCS_URI}")
    print(f"{'='*60}\n")

    # Step 1: Create corpus
    corpus = create_corpus(display_name=f"llm-parser-test-{int(time.time())}")

    # Step 2: Import file with LLM parser
    import_with_llm_parser(corpus.name, [INPUT_GCS_URI])

    # Wait for processing
    print("\nWaiting for processing to complete...")
    time.sleep(15)

    # Step 3: List files to confirm import
    list_rag_files(corpus.name)

    # Step 4: Retrieve and display parsed chunks
    chunks = retrieve_and_display_chunks(corpus.name, args.query)

    # Step 5: Save locally and to GCS
    save_chunks_locally(chunks, "parsed_output.md")

    output_filename = INPUT_GCS_URI.split("/")[-1].replace(".pdf", ".md")
    save_chunks_to_gcs(chunks, BUCKET, f"{OUTPUT_PREFIX}{output_filename}")

    print(f"\n{'='*60}")
    print("✓ DONE!")
    print(f"  Corpus: {corpus.name}")
    print(f"  Local output: parsed_output.md")
    print(f"  GCS output: gs://{BUCKET}/{OUTPUT_PREFIX}{output_filename}")
    print(f"\nTo inspect later:")
    print(f"  python test_llm_parser.py --inspect-only --corpus '{corpus.name}'")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
