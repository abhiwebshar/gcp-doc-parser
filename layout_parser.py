"""
Document AI Layout Parser - Multi-format to Markdown
Supports: PDF, DOCX, PPTX, XLSX, XLSM, HTML

This uses Document AI Layout Parser (Gemini-powered) which supports more formats
than the RAG Engine LLM Parser.

Usage:
    # First, create a Layout Parser processor in Document AI console
    # Then run:
    python layout_parser.py                     # Full pipeline
    python layout_parser.py --setup             # Create processor (one-time)
    python layout_parser.py --list-processors   # List existing processors
"""

from google.cloud import documentai_v1 as documentai
from google.cloud import storage
from google.api_core.client_options import ClientOptions
import argparse
import os
import re
import tempfile
from pypdf import PdfReader, PdfWriter

# ============ CONFIGURE THESE ============
PROJECT_ID = "compliancebotqa"
LOCATION = "us"  # Document AI multi-region: 'us' or 'eu'
BUCKET = "trenta_llmops"

# Layout Parser processor ID (created via REST API)
PROCESSOR_ID = "7dfc4ba025057d4c"

INPUT_GCS_URI = f"gs://{BUCKET}/test_docs/"  # Folder with documents
OUTPUT_PREFIX = "parsed_output/"
# ==========================================


def create_processor(project_id: str, location: str, display_name: str = "layout-parser-md"):
    """Create a Layout Parser processor (one-time setup)"""
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    client = documentai.DocumentProcessorServiceClient(client_options=opts)

    parent = client.common_location_path(project_id, location)

    processor = client.create_processor(
        parent=parent,
        processor=documentai.Processor(
            display_name=display_name,
            type_="LAYOUT_PARSER_PROCESSOR",
        ),
    )

    print(f"✓ Created processor: {processor.name}")
    print(f"  Processor ID: {processor.name.split('/')[-1]}")
    print(f"\nUpdate PROCESSOR_ID in the script with: {processor.name.split('/')[-1]}")
    return processor


def list_processors(project_id: str, location: str):
    """List all Document AI processors"""
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    client = documentai.DocumentProcessorServiceClient(client_options=opts)

    parent = client.common_location_path(project_id, location)
    processors = client.list_processors(parent=parent)

    print(f"\nProcessors in {project_id}/{location}:")
    for proc in processors:
        print(f"  - {proc.display_name}")
        print(f"    ID: {proc.name.split('/')[-1]}")
        print(f"    Type: {proc.type_}")
        print(f"    State: {proc.state.name}")
        print()


def process_document_online(
    project_id: str,
    location: str,
    processor_id: str,
    file_path: str,
    mime_type: str,
) -> dict:
    """Process a single document using REST API (online, up to 20MB)"""
    import subprocess
    import requests
    import base64

    # Get access token from gcloud
    token = subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True
    ).strip()

    # Read and encode file
    with open(file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")

    # API endpoint
    url = f"https://{location}-documentai.googleapis.com/v1/projects/{project_id}/locations/{location}/processors/{processor_id}:process"

    # Make request
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "rawDocument": {
                "content": content,
                "mimeType": mime_type,
            }
        },
        timeout=300,
    )

    if response.status_code != 200:
        raise Exception(f"API error {response.status_code}: {response.text}")

    return response.json()


def process_document_gcs(
    project_id: str,
    location: str,
    processor_id: str,
    gcs_input_uri: str,
    gcs_output_uri: str,
    mime_type: str,
) -> str:
    """Process document from GCS (batch, for large files)"""
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    client = documentai.DocumentProcessorServiceClient(client_options=opts)

    name = client.processor_path(project_id, location, processor_id)

    # Input config
    gcs_document = documentai.GcsDocument(gcs_uri=gcs_input_uri, mime_type=mime_type)
    input_config = documentai.BatchDocumentsInputConfig(
        gcs_documents=documentai.GcsDocuments(documents=[gcs_document])
    )

    # Output config
    output_config = documentai.DocumentOutputConfig(
        gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
            gcs_uri=gcs_output_uri
        )
    )

    # Process
    request = documentai.BatchProcessRequest(
        name=name,
        input_documents=input_config,
        document_output_config=output_config,
    )

    operation = client.batch_process_documents(request)
    print(f"Batch processing started: {operation.operation.name}")
    print("Waiting for completion...")

    operation.result(timeout=300)
    print("✓ Batch processing complete")

    return gcs_output_uri


def document_to_markdown(response: dict) -> str:
    """Convert Document AI JSON response to Markdown"""
    md_parts = []

    document = response.get("document", {})
    layout = document.get("documentLayout", {})
    blocks = layout.get("blocks", [])

    def process_block(block, depth=0):
        """Recursively process a block and its children"""
        parts = []

        if "textBlock" in block:
            text_block = block["textBlock"]
            text = text_block.get("text", "")
            block_type = text_block.get("type", "paragraph")

            # Format based on type
            if block_type == "heading-1":
                parts.append(f"# {text}")
            elif block_type == "heading-2":
                parts.append(f"## {text}")
            elif block_type == "heading-3":
                parts.append(f"### {text}")
            elif block_type == "paragraph":
                parts.append(text)
            else:
                parts.append(text)

            # Process nested blocks
            for child in text_block.get("blocks", []):
                child_md = process_block(child, depth + 1)
                if child_md:
                    parts.append(child_md)

        elif "tableBlock" in block:
            table = block["tableBlock"]
            table_md = []

            # Header rows
            for row in table.get("headerRows", []):
                cells = []
                for cell in row.get("cells", []):
                    cell_text = ""
                    for cb in cell.get("blocks", []):
                        if "textBlock" in cb:
                            cell_text += cb["textBlock"].get("text", "")
                    cells.append(cell_text)
                table_md.append("| " + " | ".join(cells) + " |")

            # Separator
            if table.get("headerRows"):
                num_cols = len(table["headerRows"][0].get("cells", []))
                table_md.append("| " + " | ".join(["---"] * num_cols) + " |")

            # Body rows
            for row in table.get("bodyRows", []):
                cells = []
                for cell in row.get("cells", []):
                    cell_text = ""
                    for cb in cell.get("blocks", []):
                        if "textBlock" in cb:
                            cell_text += cb["textBlock"].get("text", "")
                    cells.append(cell_text)
                table_md.append("| " + " | ".join(cells) + " |")

            parts.append("\n".join(table_md))

        elif "listBlock" in block:
            list_block = block["listBlock"]
            list_type = list_block.get("type", "unordered")
            items = []

            for i, entry in enumerate(list_block.get("listEntries", [])):
                item_text = ""
                for eb in entry.get("blocks", []):
                    if "textBlock" in eb:
                        item_text += eb["textBlock"].get("text", "")
                if list_type == "ordered":
                    items.append(f"{i+1}. {item_text}")
                else:
                    items.append(f"- {item_text}")

            parts.append("\n".join(items))

        return "\n\n".join(parts)

    # Process all top-level blocks
    for block in blocks:
        block_md = process_block(block)
        if block_md:
            md_parts.append(block_md)

    # Fall back to raw text if no structured content
    if not md_parts:
        text = document.get("text", "")
        if text:
            md_parts = [text]

    return "\n\n".join(md_parts)


def get_text_from_layout(layout, full_text: str) -> str:
    """Extract text from a layout element"""
    if not layout.text_anchor.text_segments:
        return ""

    text_parts = []
    for segment in layout.text_anchor.text_segments:
        start = int(segment.start_index) if segment.start_index else 0
        end = int(segment.end_index)
        text_parts.append(full_text[start:end])

    return "".join(text_parts)


def table_to_markdown(table, full_text: str) -> str:
    """Convert Document AI table to Markdown table"""
    rows = []

    # Header row
    if table.header_rows:
        for header_row in table.header_rows:
            cells = []
            for cell in header_row.cells:
                cell_text = get_text_from_layout(cell.layout, full_text).strip()
                cell_text = cell_text.replace("\n", " ")
                cells.append(cell_text)
            rows.append("| " + " | ".join(cells) + " |")

        # Separator
        rows.append("| " + " | ".join(["---"] * len(table.header_rows[0].cells)) + " |")

    # Body rows
    for body_row in table.body_rows:
        cells = []
        for cell in body_row.cells:
            cell_text = get_text_from_layout(cell.layout, full_text).strip()
            cell_text = cell_text.replace("\n", " ")
            cells.append(cell_text)
        rows.append("| " + " | ".join(cells) + " |")

    return "\n".join(rows)


def split_pdf(file_path: str, max_pages: int = 25) -> list[str]:
    """Split a PDF into chunks of max_pages each. Returns list of temp file paths."""
    reader = PdfReader(file_path)
    total_pages = len(reader.pages)

    if total_pages <= max_pages:
        return [file_path]  # No split needed

    print(f"Splitting PDF ({total_pages} pages) into chunks of {max_pages}...")
    temp_files = []

    for start in range(0, total_pages, max_pages):
        end = min(start + max_pages, total_pages)
        writer = PdfWriter()

        for page_num in range(start, end):
            writer.add_page(reader.pages[page_num])

        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        writer.write(temp_file)
        temp_file.close()
        temp_files.append(temp_file.name)
        print(f"  Created chunk {len(temp_files)}: pages {start+1}-{end}")

    return temp_files


def process_large_pdf(
    project_id: str,
    location: str,
    processor_id: str,
    file_path: str,
    max_pages: int = 25,
) -> str:
    """Process a large PDF by splitting into chunks and combining results."""
    # Split PDF
    chunks = split_pdf(file_path, max_pages)

    all_markdown = []
    for i, chunk_path in enumerate(chunks):
        print(f"\nProcessing chunk {i+1}/{len(chunks)}...")
        try:
            response = process_document_online(
                project_id, location, processor_id, chunk_path, "application/pdf"
            )
            md = document_to_markdown(response)
            all_markdown.append(f"<!-- Page chunk {i+1} -->\n{md}")
        finally:
            # Clean up temp file (but not original)
            if chunk_path != file_path:
                os.unlink(chunk_path)

    return "\n\n---\n\n".join(all_markdown)


def get_mime_type(file_path: str) -> str:
    """Get MIME type from file extension"""
    ext = os.path.splitext(file_path)[1].lower()
    mime_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsm": "application/vnd.ms-excel.sheet.macroenabled.12",
        ".html": "text/html",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".gif": "image/gif",
    }
    return mime_types.get(ext, "application/octet-stream")


def save_to_gcs(content: str, bucket_name: str, blob_name: str):
    """Save content to GCS"""
    client = storage.Client(project=PROJECT_ID)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(content, content_type="text/markdown")
    print(f"✓ Saved to gs://{bucket_name}/{blob_name}")


def main():
    parser = argparse.ArgumentParser(description="Document AI Layout Parser to Markdown")
    parser.add_argument("--setup", action="store_true", help="Create Layout Parser processor")
    parser.add_argument("--list-processors", action="store_true", help="List processors")
    parser.add_argument("--file", type=str, help="Local file to process")
    parser.add_argument("--processor-id", type=str, help="Processor ID to use")
    args = parser.parse_args()

    if args.setup:
        create_processor(PROJECT_ID, LOCATION)
        return

    if args.list_processors:
        list_processors(PROJECT_ID, LOCATION)
        return

    processor_id = args.processor_id or PROCESSOR_ID
    if not processor_id:
        print("Error: No processor ID. Run --setup first or provide --processor-id")
        return

    if args.file:
        # Process local file
        mime_type = get_mime_type(args.file)
        print(f"Processing: {args.file} ({mime_type})")

        # Check if PDF needs splitting
        if mime_type == "application/pdf":
            reader = PdfReader(args.file)
            num_pages = len(reader.pages)
            print(f"PDF has {num_pages} pages")

            if num_pages > 30:
                print(f"Large PDF detected, will split into chunks...")
                markdown = process_large_pdf(
                    PROJECT_ID, LOCATION, processor_id, args.file, max_pages=25
                )
            else:
                response = process_document_online(
                    PROJECT_ID, LOCATION, processor_id, args.file, mime_type
                )
                markdown = document_to_markdown(response)
        else:
            response = process_document_online(
                PROJECT_ID, LOCATION, processor_id, args.file, mime_type
            )
            markdown = document_to_markdown(response)

        # Save locally
        output_file = os.path.splitext(args.file)[0] + ".md"
        with open(output_file, "w") as f:
            f.write(markdown)
        print(f"\n✓ Saved to {output_file}")

        # Preview
        print(f"\n{'='*60}")
        print("PREVIEW (first 1000 chars):")
        print(f"{'='*60}")
        print(markdown[:1000])
    else:
        print("Usage:")
        print("  python layout_parser.py --setup              # Create processor")
        print("  python layout_parser.py --list-processors    # List processors")
        print("  python layout_parser.py --file doc.xlsx      # Process file")
        print("  python layout_parser.py --file doc.pdf --processor-id abc123")


if __name__ == "__main__":
    main()
