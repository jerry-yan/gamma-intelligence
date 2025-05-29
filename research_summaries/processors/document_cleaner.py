"""
Clean PDFs for all ResearchNote objects whose status == 1.

 ↳  Downloads each PDF from S3
 ↳  Removes everything from broker‑specific "disclosure" headings onward
 ↳  Uploads cleaned PDF back to S3, replacing the original
 ↳  Updates note.file_update_time and sets status = 2 on success
"""

import os
import re
import tempfile
import boto3
import fitz  # PyMuPDF
from django.utils.timezone import now
from django.conf import settings
from research_summaries.models import ResearchNote

# ── HEADINGS CONFIG ──────────────────────────────────────────────
DEFAULT_HEADINGS = ("Required Disclosures", "Important Disclosures")

DOMAIN_HEADINGS = {
    "scotiabank.com": ("Appendix A: Important Disclosures", "Important Disclosures"),
    "ubs.com": ("Quantitative Research Review", "Required Disclosures"),
    "bofa.com": ("Analyst Certification", "Disclosures", "Required Disclosures"),
    "stifel.com": ("Important Disclosures and Certifications", "Required Disclosures"),
    "psc.com": ("IMPORTANT RESEARCH DISCLOSURES", "Required Disclosures"),
    "morganstanley.com": ("Disclosure Section", "Risk Reward Reference links"),
    "bernsteinsg.com": ("I. REQUIRED DISCLOSURES", "Required Disclosures"),
    "wellsfargo.com": ("Required Disclosures", "Important Disclosures"),
    "rbccm.com": "Required disclosures",
    "jpmchase.com": ("Analyst Certification", "Companies Discussed in This Report", "Important Disclosures"),
    "jpmorgan.com": ("Analyst Certification", "Companies Discussed in This Report",
                     "Important Disclosures", "Quick Links"),
    "evercoreisi.com": ("Analyst Certification", "Timestamp", "IMPORTANT DISCLOSURES"),
    "gs.com": ("Disclosure Appendix", "Disclosures", "Regulatory disclosures"),
    "jefferies.com": ("Analyst Certification", "Analyst Certification:",
                      "Company Specific Disclosures"),
    "barclays.com": ("Analyst(s) Certification(s):", "Important Disclosures:",
                     "Analyst(s) Certification(s)", "Important Disclosures"),
    "citi.com": ("Appendix A-1", "Analyst Certification", "IMPORTANT DISCLOSURES"),
    "bnpparibas.com": ("ANALYST CERTIFICATION AND IMPORTANT DISCLOSURES", "Analyst Certification"),
    "tdsecurities.com": ("IMPORTANT DISCLOSURES AND INFORMATION", "Analyst Certification",
                         "IMPORTANT DISCLOSURES"),
}


# ── AWS S3 SETUP ─────────────────────────────────────────
def get_s3_client():
    """Initialize S3 client with credentials"""
    return boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )


# ── PDF HELPER UTILITIES ─────────────────────────────────
def determine_cutoff_headings(doc):
    text_content = "\n".join(doc.load_page(i).get_text("text")
                             for i in range(doc.page_count))
    for domain, headings in DOMAIN_HEADINGS.items():
        if f"@{domain}" in text_content:
            return headings if isinstance(headings, tuple) else (headings,)
    return DEFAULT_HEADINGS


def group_words_into_lines(words, y_threshold=2.0):
    if not words:
        return []
    words = sorted(words, key=lambda w: (w[1], w[0]))
    lines, cur, cur_y = [], [], None
    for w in words:
        x0, y0, *_ = w
        if not cur or abs(y0 - cur_y) < y_threshold:
            cur.append(w);
            cur_y = y0
        else:
            lines.append(_mk_line(cur));
            cur = [w];
            cur_y = y0
    if cur: lines.append(_mk_line(cur))
    return lines


def _mk_line(words_on_line):
    words_on_line.sort(key=lambda w: w[0])
    x0s, x1s, y0s, y1s = zip(*[(w[0], w[2], w[1], w[3]) for w in words_on_line])
    return {
        "y_top": min(y0s),
        "y_bottom": max(y1s),
        "x0": min(x0s),
        "x1": max(x1s),
        "text": " ".join(w[4] for w in words_on_line).strip()
    }


def clean_pdf_from_s3(s3_key: str):
    """
    Download PDF from S3, clean it, then upload back to S3.
    Returns True if cleaned successfully.
    """
    s3_client = get_s3_client()
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME

    # Create temporary files
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_input:
        temp_input_path = temp_input.name

    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_output:
        temp_output_path = temp_output.name

    try:
        # Download from S3
        print(f"📥 Downloading {s3_key} from S3...")
        s3_client.download_file(bucket_name, s3_key, temp_input_path)

        # Clean the PDF
        doc = fitz.open(temp_input_path)
        headings = determine_cutoff_headings(doc)
        pattern = re.compile(
            rf"^\s*(?:[IVXLCDM.\s]*|\b\w+\s+\w+[:.\-]\s*)?({'|'.join(headings)})\s*$",
            re.IGNORECASE)

        cut_found = False
        for page_idx in range(doc.page_count):
            page = doc.load_page(page_idx)
            lines = group_words_into_lines(page.get_text("words"))
            for ln in lines:
                if pattern.match(ln["text"]):
                    cut_found = True
                    cut_page, cut_y = page_idx, ln["y_top"]
                    break
            if cut_found:
                break

        if cut_found:
            print(f"✂️  Found disclosure section on page {cut_page + 1}, cleaning...")
            doc.select(range(cut_page + 1))
            page = doc[-1]
            page.add_redact_annot(fitz.Rect(0, cut_y, page.rect.width, page.rect.height),
                                  fill=(1, 1, 1))
            page.apply_redactions()
        else:
            print("ℹ️  No disclosure section found, keeping original")

        # Save cleaned PDF
        doc.save(temp_output_path, garbage=4)
        doc.close()

        # Upload back to S3
        print(f"📤 Uploading cleaned PDF back to S3...")
        s3_client.upload_file(temp_output_path, bucket_name, s3_key)

        return True

    except Exception as e:
        print(f"❌ Error processing {s3_key}: {e}")
        return False

    finally:
        # Clean up temporary files
        try:
            os.unlink(temp_input_path)
            os.unlink(temp_output_path)
        except FileNotFoundError:
            pass


def clean_documents():
    """Main function to clean all documents with status == 1"""
    notes = ResearchNote.objects.filter(status=1)
    if not notes.exists():
        print("✅ No PDFs awaiting cleaning.")
        return

    print(f"🧹 Cleaning {notes.count()} research PDFs from S3...")
    success_count = 0

    for note in notes:
        try:
            # Extract S3 key from file_directory
            # Assuming file_directory contains the full S3 path
            s3_key = note.file_directory
            if s3_key.startswith('https://'):
                # Extract key from URL if it's a full S3 URL
                s3_key = s3_key.split('amazonaws.com/')[-1]
            elif s3_key.startswith('s3://'):
                # Extract key from s3:// URL
                s3_key = s3_key.split('/', 3)[-1]

            print(f"🔄 Processing {note.file_id}: {s3_key}")

            if clean_pdf_from_s3(s3_key):
                note.status = 2
                note.file_update_time = now()
                note.save(update_fields=["status", "file_update_time"])
                success_count += 1
                print(f"✅ Cleaned & updated {note.file_id}")
            else:
                print(f"❌ Failed to clean {note.file_id}")

        except Exception as e:
            print(f"❌ Error processing {note.file_id}: {e}")

    print(f"🏁 Cleaning task finished. {success_count}/{notes.count()} files processed successfully.")


def process_single_document(note):
    """Process a single document for real-time streaming"""
    try:
        # Extract S3 key from file_directory
        s3_key = note.file_directory
        if s3_key.startswith('https://'):
            s3_key = s3_key.split('amazonaws.com/')[-1]
        elif s3_key.startswith('s3://'):
            s3_key = s3_key.split('/', 3)[-1]

        # Clean the document
        if clean_pdf_from_s3(s3_key):
            note.status = 2
            note.file_update_time = now()
            note.save(update_fields=["status", "file_update_time"])
            return True
        else:
            return False

    except Exception as e:
        return False