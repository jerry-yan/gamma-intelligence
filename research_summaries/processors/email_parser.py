from research_summaries.models import ResearchNote
from django.utils.timezone import now
import os, ssl, datetime, email, pandas as pd, io, re
from email.utils import parsedate_to_datetime
from imapclient import IMAPClient
from urllib.parse import urlparse, parse_qs
import logging

# Configure logging
logger = logging.getLogger(__name__)

# ── ACCOUNT ─────────────────────────────────────────────────────────
IMAP_HOST = "imap.gmx.com"
USERNAME = "gamma.invest@gmx.com"
PASSWORD = os.getenv("GMX_PW", "Premiumyield1")

# ── FILTERS ─────────────────────────────────────────────────────────
LOOKBACK_HOURS = 28
SENDER_EMAIL = None  # set to an address later if desired


# ── HELPERS ─────────────────────────────────────────────────────────
def fresh_enough(msg_date, hours):
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - msg_date).total_seconds() <= hours * 3600


def get_attachments(msg):
    """Extract CSV attachments from email message"""
    attachments = []

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_disposition() == 'attachment':
                filename = part.get_filename()
                if filename and filename.lower().endswith('.csv'):
                    content = part.get_payload(decode=True)
                    attachments.append((filename, content))

    return attachments


def extract_document_id(download_link):
    """Extract full documentId from a URL query string"""
    try:
        parsed_url = urlparse(download_link)
        query_params = parse_qs(parsed_url.query)
        doc_ids = query_params.get("documentId", [])
        return doc_ids[0] if doc_ids else None
    except Exception as e:
        logger.error(f"Error parsing documentId from link: {download_link} → {e}")
        return None


# ── MAIN WITH YIELD FOR REAL-TIME UPDATES ──────────────────────────
def fetch_research_summaries():
    """Generator function that yields status updates during email processing"""
    try:
        yield {"status": "info", "message": "🔌 Connecting to email server..."}

        ctx = ssl.create_default_context()
        with IMAPClient(IMAP_HOST, ssl=True, ssl_context=ctx) as imap:
            yield {"status": "info", "message": f"🔐 Logging in as {USERNAME}..."}
            imap.login(USERNAME, PASSWORD)
            imap.select_folder("INBOX")

            yield {"status": "info", "message": "🔍 Searching for emails..."}

            # Calculate date 24 hours ago for IMAP search
            since_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=LOOKBACK_HOURS)
            since_date_str = since_date.strftime('%d-%b-%Y')  # Format: "26-May-2025"

            # Build search criteria with date filter
            if SENDER_EMAIL:
                search_keys = ["FROM", SENDER_EMAIL, "SINCE", since_date_str]
                yield {"status": "info",
                       "message": f"🔍 Searching for emails from {SENDER_EMAIL} since {since_date_str}"}
            else:
                search_keys = ["SINCE", since_date_str]
                yield {"status": "info", "message": f"🔍 Searching for emails since {since_date_str}"}

            uids = imap.search(search_keys)

            if not uids:
                yield {"status": "warning", "message": "📭 No messages found matching search criteria"}
                return

            yield {"status": "info", "message": f"📧 Found {len(uids)} emails to process"}

            processed_count = 0
            total_records_created = 0

            for i, uid in enumerate(uids, 1):
                yield {"status": "info", "message": f"📨 Processing email {i}/{len(uids)} (UID: {uid})"}

                try:
                    raw = imap.fetch(uid, ["RFC822"])[uid][b"RFC822"]
                    msg = email.message_from_bytes(raw)

                    # Get and validate message date
                    msg_date = parsedate_to_datetime(msg["Date"])
                    if msg_date.tzinfo is None:
                        msg_date = msg_date.replace(tzinfo=datetime.timezone.utc)

                    if not fresh_enough(msg_date, LOOKBACK_HOURS):
                        yield {"status": "info",
                               "message": f"⏭️  Email from {msg_date.strftime('%Y-%m-%d %H:%M')} is too old, skipping"}
                        continue

                    # Process sender info
                    sender = msg.get("From", "Unknown Sender")
                    subject = msg.get("Subject", "No Subject")

                    yield {"status": "info",
                           "message": f"📄 Subject: {subject[:50]}{'...' if len(subject) > 50 else ''}"}
                    yield {"status": "info", "message": f"👤 From: {sender}"}

                    attachments = get_attachments(msg)

                    if not attachments:
                        yield {"status": "info", "message": "📎 No CSV attachments found"}
                        continue

                    yield {"status": "success", "message": f"📎 Found {len(attachments)} CSV attachment(s)"}

                    for filename, content in attachments:
                        yield {"status": "info", "message": f"🔄 Processing attachment: {filename}"}

                        try:
                            # Attempt decoding CSV with fallback encodings
                            df = None
                            for encoding in ['utf-8-sig', 'iso-8859-1']:
                                try:
                                    df = pd.read_csv(io.BytesIO(content), encoding=encoding)
                                    break
                                except UnicodeDecodeError:
                                    continue

                            if df is None:
                                yield {"status": "error", "message": f"❌ Unable to decode CSV content in {filename}"}
                                continue

                            yield {"status": "info",
                                   "message": f"📊 CSV has {len(df)} rows and {len(df.columns)} columns"}

                            records_created_this_file = 0

                            for idx, row in df.iterrows():

                                if row.get("Type") == "Expert":
                                    yield {"status": "info",
                                           "message": f"⏩ Row {idx + 1}: Skipping Expert type record"}
                                    continue

                                link = row.get("Download Link", "")
                                doc_id = extract_document_id(link)

                                if not doc_id:
                                    yield {"status": "warning",
                                           "message": f"⚠️  Row {idx + 1}: no valid document ID found"}
                                    continue

                                # Skip if document already exists
                                if ResearchNote.objects.filter(file_id=doc_id).exists():
                                    yield {"status": "info",
                                           "message": f"⏩ Row {idx + 1}: file_id {doc_id} already exists"}
                                    continue

                                try:
                                    # Parse company list and count
                                    company_str = row.get("Company")
                                    if pd.isna(company_str) or str(company_str).strip().lower() == "none":
                                        raw_companies = ""
                                        company_count = 0
                                    else:
                                        raw_companies = str(company_str).strip()
                                        company_count = len([c.strip() for c in raw_companies.split(",") if c.strip()])

                                    # Clean source (Broker)
                                    raw_source = row.get("Broker", "")
                                    cleaned_source = str(raw_source).strip().rstrip("*") if raw_source else None

                                    # Other fields
                                    raw_author = row.get("Author")
                                    raw_title = row.get("Title")
                                    raw_page_count = row.get("Pages")
                                    file_update_time = now()

                                    note = ResearchNote.objects.create(
                                        source=cleaned_source,
                                        provider="AlphaSense",
                                        file_id=doc_id,
                                        download_link=link,
                                        file_directory=None,
                                        raw_companies=raw_companies,
                                        raw_company_count=company_count,
                                        raw_author=raw_author,
                                        raw_title=raw_title,
                                        raw_page_count=raw_page_count,
                                        report_type=None,
                                        report_summary=None,
                                        file_download_time=None,
                                        file_update_time=file_update_time,
                                        status=0,
                                    )

                                    records_created_this_file += 1
                                    total_records_created += 1

                                    title_preview = (raw_title or "Untitled")[:30]
                                    yield {"status": "success",
                                           "message": f"✅ Created: {title_preview}... (ID: {note.id})"}

                                except Exception as e:
                                    yield {"status": "error",
                                           "message": f"❌ Error creating record for row {idx + 1}: {str(e)}"}

                            yield {"status": "success",
                                   "message": f"📁 {filename}: Created {records_created_this_file} new records"}
                            processed_count += 1

                        except Exception as e:
                            yield {"status": "error", "message": f"❌ Error processing {filename}: {str(e)}"}

                except Exception as e:
                    yield {"status": "error", "message": f"❌ Error processing email UID {uid}: {str(e)}"}

            yield {"status": "success", "message": f"🎉 Processing complete!"}
            yield {"status": "success",
                   "message": f"📧 Processed {processed_count} CSV attachments from {len(uids)} emails"}
            yield {"status": "success", "message": f"📝 Created {total_records_created} new research records"}

    except Exception as e:
        yield {"status": "error", "message": f"🚨 Critical error: {str(e)}"}
        logger.exception("Critical error in fetch_research_summaries")