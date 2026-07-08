from app.core.config import settings
from app.schemas.context import DocumentChunk
from app.services.context.document_normalizer import normalize_document_text
from app.services.context.section_parser import parse_sections

CHUNK_TARGET_CHARS = settings.chunk_target_chars
CHUNK_OVERLAP_CHARS = settings.chunk_overlap_chars
MAX_CHUNK_CHARS = max(settings.chunk_target_chars + settings.chunk_overlap_chars * 3, 3500)


def _make_chunk(
    *,
    index: int,
    title: str | None,
    text: str,
    section_path: list[str],
    start_char: int,
    end_char: int,
) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=f"chunk_{index:04d}",
        title=title,
        text=text.strip(),
        section_path=section_path,
        start_char=start_char,
        end_char=end_char,
        character_count=len(text.strip()),
    )


def _split_long_section(
    *,
    section_title: str,
    section_text: str,
    section_path: list[str],
    section_start: int,
    start_index: int,
) -> list[DocumentChunk]:
    paragraphs = [
        paragraph.strip()
        for paragraph in section_text.split("\n\n")
        if paragraph.strip()
    ]
    chunks: list[DocumentChunk] = []
    buffer: list[str] = []
    buffer_start_offset = 0
    cursor = 0
    next_index = start_index

    for paragraph in paragraphs:
        paragraph_offset = section_text.find(paragraph, cursor)
        if paragraph_offset < 0:
            paragraph_offset = cursor

        current_text = "\n\n".join(buffer)
        would_exceed = buffer and len(current_text) + len(paragraph) + 2 > CHUNK_TARGET_CHARS

        if would_exceed:
            chunk_text = "\n\n".join(buffer)
            chunk_start = section_start + buffer_start_offset
            chunk_end = chunk_start + len(chunk_text)
            chunks.append(
                _make_chunk(
                    index=next_index,
                    title=section_title,
                    text=chunk_text,
                    section_path=section_path,
                    start_char=chunk_start,
                    end_char=chunk_end,
                )
            )
            next_index += 1

            overlap = chunk_text[-CHUNK_OVERLAP_CHARS:].strip()
            buffer = [overlap, paragraph] if overlap else [paragraph]
            buffer_start_offset = max(0, paragraph_offset - len(overlap))
        else:
            if not buffer:
                buffer_start_offset = paragraph_offset
            buffer.append(paragraph)

        cursor = paragraph_offset + len(paragraph)

    if buffer:
        chunk_text = "\n\n".join(buffer)
        chunk_start = section_start + buffer_start_offset
        chunk_end = min(section_start + len(section_text), chunk_start + len(chunk_text))
        chunks.append(
            _make_chunk(
                index=next_index,
                title=section_title,
                text=chunk_text,
                section_path=section_path,
                start_char=chunk_start,
                end_char=chunk_end,
            )
        )

    return chunks


def build_document_chunks(text: str) -> list[DocumentChunk]:
    normalized_text = normalize_document_text(text)
    if not normalized_text:
        return []

    chunks: list[DocumentChunk] = []
    next_index = 1

    for section in parse_sections(normalized_text):
        if len(section.text) <= MAX_CHUNK_CHARS:
            chunks.append(
                _make_chunk(
                    index=next_index,
                    title=section.title,
                    text=section.text,
                    section_path=section.section_path,
                    start_char=section.start_char,
                    end_char=section.end_char,
                )
            )
            next_index += 1
            continue

        section_chunks = _split_long_section(
            section_title=section.title,
            section_text=section.text,
            section_path=section.section_path,
            section_start=section.start_char,
            start_index=next_index,
        )
        chunks.extend(section_chunks)
        next_index += len(section_chunks)

    return chunks
