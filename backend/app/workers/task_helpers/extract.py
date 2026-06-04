"""
Text extraction utilities for knowledge base processing.
"""
import logging

logger = logging.getLogger(__name__)


def _extract_text(content: bytes, file_type: str) -> str:
    """Extract text from file content in a sandboxed manner."""
    try:
        if file_type == "pdf":
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            return "\n".join(page.get_text() for page in doc)
        elif file_type == "docx":
            import io
            from docx import Document
            doc = Document(io.BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        elif file_type == "xlsx":
            import io
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
            texts = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    texts.append(" ".join(str(c) for c in row if c is not None))
            return "\n".join(texts)
        elif file_type == "txt":
            return content.decode("utf-8", errors="ignore")
        elif file_type == "audio":
            from app.config import settings
            if not settings.OPENAI_API_KEY:
                logger.warning("OPENAI_API_KEY not set — skipping Whisper transcription")
                return ""
            import io
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            audio_file = io.BytesIO(content)
            audio_file.name = "audio.mp3"
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es",
            )
            return transcript.text
        else:
            return ""
    except Exception as e:
        logger.error("[EXTRACT ERROR] file_type=%s error=%s", file_type, e)
        return ""
