"""
Loop through ResearchNote objects with status == 2.

• If report_type is missing, upload the PDF → categorize via OpenAI → save report_type
• Always run a summarization prompt based on report_type
• Save the JSON response in report_summary
• On success: status = 3 and file_summary_time = now()
"""
import json
from django.utils.timezone import now
from utils.file_utils import get_or_upload_file_to_openai
from research_summaries.openai_utils import get_openai_client
from research_summaries.models import ResearchNote
from research_summaries.OpenAI_toolbox.prompts import (
    CATEGORIZATION_INSTRUCTIONS,
    SUMMARY_INSTRUCTIONS,
    DEFAULT_SUMMARY_PROMPT,
)
from research_summaries.OpenAI_toolbox.structured_outputs import SCHEMAS

MODEL_ONE = 'gpt-4.1-mini-2025-04-14'
MODEL = 'gpt-5-mini-2025-08-07'

TICKER_OVERRIDES = {
    "2330": "TSMC",
    "2330 TT": "TSMC",
    "2330.TW": "TSMC",
    "9988": "BABA",
    "9988.HK": "BABA",
    "ABI": "BUD", # A‑B InBev ADR code often appears as ABBI
    "RR/LN": "RR",
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
        # temperature=0.001,
    )

    return json.loads(response.output_text).get('report_type')


def categorize_document_v2(client, model: str, file_id: str, company_count: int, companies: str, title: str) -> tuple:
    """
    Categorize a document and assign vector group ID based on its content.
    Returns a tuple of (report_type, vector_group_id)
    """
    # Determine which categorization instructions to use
    if company_count <= 0:
        cat_key = "no-company"
        report_options = ["Initiation Report", "Company Update", "Quarter Preview", "Quarter Review", "Industry Note",
                          "Macro/Strategy Report", "Invalid"]
        prompt = f"There seems to be no company mentioned in the report but the title is '{title}'"

    elif company_count == 1:
        cat_key = "single-company"
        report_options = ["Initiation Report", "Company Update", "Quarter Preview", "Quarter Review", "Industry Note",
                          "Macro/Strategy Report", "Invalid"]
        prompt = f"The report should be about {companies} and the title is '{title}'"

    else:
        cat_key = "multi-company"
        report_options = ["Initiation Report", "Company Update", "Quarter Preview", "Quarter Review", "Industry Note",
                          "Macro/Strategy Report", "Invalid"]
        prompt = f"There are multiple companies in the report which include {companies} and the title is '{title}'"

    cat_instruction = CATEGORIZATION_INSTRUCTIONS[cat_key]

    enum_options = [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116]

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
                        "vector_group_id": {"type": "number", "enum": enum_options}
                    },
                    "required": ["report_type", "vector_group_id"],
                    "additionalProperties": False,
                },
            },
        },
        # temperature=0.001,
    )

    result = json.loads(response.output_text)
    return result.get('report_type'), result.get('vector_group_id')


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
        # temperature=0.1,
    )

    return json.loads(response.output_text)


# ── MAIN TASK -----------------------------------------------------------------
def summarize_documents():
    notes = ResearchNote.objects.filter(status=2)
    if not notes.exists():
        print("✅ No documents awaiting summarization.")
        return

    print(f"📝 Summarizing {notes.count()} research notes …")

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

            # Categorize if needed
            # if not note.report_type:
            #     print(f"🔖 Categorizing {note.file_id}...")
            #     note.report_type = categorize_document(
            #         client, MODEL, file_id, note.raw_company_count or 0,
            #                                 note.raw_companies or "", note.raw_title or ""
            #     )
            #     note.save(update_fields=["report_type"])
            #     print(f"🔖 Categorized {note.file_id} → {note.report_type}")

            # Categorize if needed - using the new v2 function
            if not note.report_type:
                print(f"🔖 Categorizing {note.file_id}...")
                report_type, vector_group_id = categorize_document_v2(
                    client, MODEL, file_id, note.raw_company_count or 0,
                                            note.raw_companies or "", note.raw_title or ""
                )
                note.report_type = report_type
                note.vector_group_id = vector_group_id
                note.save(update_fields=["report_type", "vector_group_id"])
                print(f"🔖 Categorized {note.file_id} → {note.report_type} (Vector Group: {note.vector_group_id})")

            if note.report_type == "Invalid":
                print(f"⚠️  Skipping invalid report: {note.file_id}")
                note.status = 10  # Invalid
                note.save(update_fields=["status"])
                continue

            print(f"📝 Summarizing {note.file_id}...")
            summary_instructions = SUMMARY_INSTRUCTIONS.get(note.report_type, DEFAULT_SUMMARY_PROMPT)
            summary_schema = SCHEMAS.get(note.report_type)

            if not summary_schema:
                print(f"⚠️  No schema found for report type: {note.report_type}")
                continue

            summary_json = summarize_document(client, MODEL, file_id, summary_instructions, summary_schema)

            # Check if note.vector_group_id is empty and summary_json contains one
            if not note.vector_group_id and summary_json.get("vector_group_id"):
                note.vector_group_id = summary_json.get("vector_group_id")
                # Remove vector_group_id from summary_json since we're storing it separately
                summary_json.pop("vector_group_id", None)
                print(f"📍 Extracted vector_group_id {note.vector_group_id} from summary")

            ticker = clean_ticker(summary_json.get("stock_ticker"))
            note.report_summary = summary_json
            note.parsed_ticker = ticker
            note.status = 3
            note.file_summary_time = now()
            note.save(update_fields=[
                "report_summary", "parsed_ticker",
                "status", "file_summary_time", "vector_group_id"  # Added vector_group_id to update_fields
            ])

            success_count += 1
            print(f"✅ Summarized {note.file_id}")


        except Exception as e:
            print(f"❌ Error processing {note.file_id}: {e}")

        # finally:
        #     # Clean up OpenAI file
        #     if file_id:
        #         try:
        #             client.files.delete(file_id=file_id)
        #         except Exception as e:
        #             print(f"⚠️  Failed to delete OpenAI file {file_id}: {e}")
        #
        #     # Clean up temporary file
        #     if temp_pdf_path and os.path.exists(temp_pdf_path):
        #         try:
        #             os.unlink(temp_pdf_path)
        #         except Exception as e:
        #             print(f"⚠️  Failed to delete temp file {temp_pdf_path}: {e}")

    print(f"🏁 Summarization task finished. {success_count}/{notes.count()} documents processed successfully.")


def process_single_document(note):
    """Process a single document for real-time streaming"""
    client = get_openai_client()
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
        # if not note.report_type:
        #     note.report_type = categorize_document(
        #         client, MODEL, file_id, note.raw_company_count or 0,
        #                                 note.raw_companies or "", note.raw_title or ""
        #     )
        #     note.save(update_fields=["report_type"])

        # Categorize if needed - using the new v2 function
        if not note.report_type:
            report_type, vector_group_id = categorize_document_v2(
                client, MODEL, file_id, note.raw_company_count or 0,
                                        note.raw_companies or "", note.raw_title or ""
            )
            note.report_type = report_type
            note.vector_group_id = vector_group_id
            note.save(update_fields=["report_type", "vector_group_id"])

        if note.report_type == "Invalid":
            return False

        # Summarize
        summary_instructions = SUMMARY_INSTRUCTIONS.get(note.report_type, DEFAULT_SUMMARY_PROMPT)
        summary_schema = SCHEMAS.get(note.report_type)

        if not summary_schema:
            return False

        summary_json = summarize_document(client, MODEL, file_id, summary_instructions, summary_schema)

        # Check if note.vector_group_id is empty and summary_json contains one
        if not note.vector_group_id and summary_json.get("vector_group_id"):
            note.vector_group_id = summary_json.get("vector_group_id")
            # Remove vector_group_id from summary_json since we're storing it separately
            summary_json.pop("vector_group_id", None)
            print(f"📍 Extracted vector_group_id {note.vector_group_id} from summary")

        ticker = clean_ticker(summary_json.get("stock_ticker"))
        note.report_summary = summary_json
        note.parsed_ticker = ticker
        note.status = 3
        note.file_summary_time = now()
        note.save(update_fields=[
            "report_summary", "parsed_ticker",
            "status", "file_summary_time", "vector_group_id"  # Added vector_group_id to update_fields
        ])

        return True

    except Exception as e:
        note.status = 10  # Error status
        note.save(update_fields=["status"])
        return False