"""
Advanced Document Summarizer for Research Notes

Loop through ResearchNote objects with status == 3 (Summarized) AND is_advanced_summary=True.

• If report_type is missing, upload the PDF → categorize via OpenAI → save report_type
• Always run a summarization prompt based on report_type using GPT o3-mini
• Save the JSON response in report_summary
• On success: status = 4 (Advanced Summarized) and file_summary_time = now()
"""
import json
from django.utils.timezone import now
from utils.file_utils import get_or_upload_file_to_openai
from research_summaries.openai_utils import get_openai_client
from research_summaries.models import ResearchNote
from research_summaries.OpenAI_toolbox.prompts import (
    CATEGORIZATION_INSTRUCTIONS,
    ADVANCED_SUMMARY_INSTRUCTIONS,
    DEFAULT_SUMMARY_PROMPT,
)
from research_summaries.OpenAI_toolbox.structured_outputs import ADVANCED_SCHEMAS

# Use GPT o3-mini for advanced summarization
MODEL = 'o3-mini-2025-01-31'

TICKER_OVERRIDES = {
    "2330": "TSMC",
    "2330 TT": "TSMC",
    "2330.TW": "TSMC",
    "ABI": "BUD", # A‑B InBev ADR code often appears as ABBI
}


# ── Utility Functions -------------------------------------------------------
def clean_ticker(raw: str | None) -> str | None:
    if not raw:
        return None
    ticker = raw.strip().upper()

    for alt_name, real_name in TICKER_OVERRIDES.items():
        if alt_name in ticker:
            return real_name

    if " " in ticker:
        ticker = ticker.split(" ", 1)[0]

    for sep in (".", "-", ","):
        if sep in ticker:
            ticker = ticker.split(sep, 1)[0]
    return ticker or None


def categorize_document(client, model: str, file_id: str, company_count: int, companies: str, title: str) -> str:
    if company_count == 0:
        cat_key = "no-company"
        report_options = ["Industry Note", "Macro/Strategy Report", "Invalid"]
        prompt = f"There are no companies in the report and the title is '{title}'"

    elif company_count == 1:
        cat_key = "single-company"
        report_options = ["Initiation Report", "Company Update", "Quarter Preview", "Quarter Review", "Invalid"]
        prompt = f"The report should be about {companies} and the title is '{title}'"

    else:
        cat_key = "multi-company"
        report_options = ["Initiation Report", "Company Update", "Quarter Preview", "Quarter Review", "Industry Note",
                          "Macro/Strategy Report", "Invalid"]
        prompt = f"There are multiple companies in the report which include {companies} and the title is '{title}'"

    cat_instruction = CATEGORIZATION_INSTRUCTIONS[cat_key]

    response = client.responses.create(
        model=model,
        instructions=cat_instruction,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "file_id": file_id,
                    },
                    {
                        "type": "input_text",
                        "text": prompt,
                    },
                ]
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "report_categorization",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "report_type": {"type": "string", "enum": report_options},
                    },
                    "required": ["report_type"],
                    "additionalProperties": False,
                },
            },
        },
    )

    return json.loads(response.output_text).get('report_type')


def summarize_document(client, model: str, file_id: str, instructions: str, schema) -> dict:
    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "file_id": file_id,
                    },
                    {
                        "type": "input_text",
                        "text": "...",
                    },
                ]
            }
        ],
        text=schema,
    )

    return json.loads(response.output_text)


# ── MAIN TASK -----------------------------------------------------------------
def summarize_documents_advanced():
    """
    Advanced summarization using GPT o3-mini for documents with status=3 AND is_advanced_summary=True
    """
    notes = ResearchNote.objects.filter(status=3, is_advanced_summary=True)
    if not notes.exists():
        print("✅ No documents awaiting advanced summarization.")
        return

    print(f"🧠 Advanced summarizing {notes.count()} research notes with GPT o3-mini...")

    client = get_openai_client()
    success_count = 0

    for note in notes:

        try:
            # Get or upload file to OpenAI (reuse existing if possible)
            file_id = get_or_upload_file_to_openai(
                s3_key=note.file_directory,
                existing_file_id=note.openai_file_id
            )

            # Save the file_id if it's new
            if not note.openai_file_id:
                note.openai_file_id = file_id
                note.save(update_fields=['openai_file_id'])

            # Categorize if needed (should rarely be needed for status=3)
            if not note.report_type:
                print(f"🔖 Categorizing {note.file_id}...")
                note.report_type = categorize_document(
                    client, MODEL, file_id, note.raw_company_count or 0,
                                            note.raw_companies or "", note.raw_title or ""
                )
                note.save(update_fields=["report_type"])
                print(f"🔖 Categorized {note.file_id} → {note.report_type}")

            if note.report_type == "Invalid":
                print(f"⚠️  Skipping invalid report: {note.file_id}")
                note.status = 10  # Invalid
                note.save(update_fields=["status"])
                continue

            print(f"🧠 Advanced summarizing {note.file_id} with GPT o3-mini...")
            summary_instructions = ADVANCED_SUMMARY_INSTRUCTIONS.get(note.report_type, DEFAULT_SUMMARY_PROMPT)
            summary_schema = ADVANCED_SCHEMAS.get(note.report_type)

            if not summary_schema:
                print(f"⚠️  No schema found for report type: {note.report_type}")
                continue

            summary_json = summarize_document(client, MODEL, file_id, summary_instructions, summary_schema)

            ticker = clean_ticker(summary_json.get("stock_ticker"))
            note.report_summary = summary_json
            note.parsed_ticker = ticker
            note.status = 4  # Advanced Summarized
            note.file_summary_time = now()
            note.save(update_fields=[
                "report_summary", "parsed_ticker",
                "status", "file_summary_time"
            ])
            success_count += 1
            print(f"✅ Advanced summarized {note.file_id}")

        except Exception as e:
            print(f"❌ Error processing {note.file_id}: {e}")
            note.status = 11  # Error status
            note.save(update_fields=["status"])

    print(f"🏁 Advanced summarization task finished. {success_count}/{notes.count()} documents processed successfully.")


def process_single_document_advanced(note):
    """Process a single document for advanced summarization with real-time streaming"""
    client = get_openai_client()
    temp_pdf_path = None
    file_id = None

    try:
        # Get or upload file to OpenAI (reuse existing if possible)
        file_id = get_or_upload_file_to_openai(
            s3_key=note.file_directory,
            existing_file_id=note.openai_file_id
        )

        # Save the file_id if it's new
        if not note.openai_file_id:
            note.openai_file_id = file_id
            note.save(update_fields=['openai_file_id'])

        # Categorize if needed
        if not note.report_type:
            note.report_type = categorize_document(
                client, MODEL, file_id, note.raw_company_count or 0,
                                        note.raw_companies or "", note.raw_title or ""
            )
            note.save(update_fields=["report_type"])

        if note.report_type == "Invalid":
            return False

        # Advanced summarize
        summary_instructions = ADVANCED_SUMMARY_INSTRUCTIONS.get(note.report_type, DEFAULT_SUMMARY_PROMPT)
        summary_schema = ADVANCED_SCHEMAS.get(note.report_type)

        if not summary_schema:
            return False

        summary_json = summarize_document(client, MODEL, file_id, summary_instructions, summary_schema)

        ticker = clean_ticker(summary_json.get("stock_ticker"))
        note.report_summary = summary_json
        note.parsed_ticker = ticker
        note.status = 4  # Advanced Summarized
        note.file_summary_time = now()
        note.save(update_fields=[
            "report_summary", "parsed_ticker",
            "status", "file_summary_time"
        ])

        return True

    except Exception as e:
        note.status = 11  # Error status
        note.save(update_fields=["status"])
        return False