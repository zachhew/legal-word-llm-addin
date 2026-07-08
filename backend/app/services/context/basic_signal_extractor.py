import re

from app.schemas.context import DocumentChunk, RawSignal

PERIOD_RE = re.compile(
    r"(?:за\s+|в течение\s+)?\d{1,3}\s+"
    r"(?:рабочих|календарных|банковских)?\s*"
    r"(?:дней|дня|день|часов|часа|час|месяцев|месяца|месяц|лет|года|год)",
    re.IGNORECASE,
)
PERCENT_RE = re.compile(r"\d{1,3}(?:[,.]\d+)?\s?%")
MONEY_RE = re.compile(
    r"\d{1,3}(?:[ \u00a0]?\d{3})*(?:[,.]\d{1,2})?\s*"
    r"(?:руб(?:\.|лей|ля|ль)?|₽)",
    re.IGNORECASE,
)
DATE_RE = re.compile(
    r"(?:\d{1,2}\.\d{1,2}\.\d{2,4}|"
    r"\d{1,2}\s+"
    r"(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|"
    r"октября|ноября|декабря)\s+\d{4})",
    re.IGNORECASE,
)
CLAUSE_REF_RE = re.compile(
    r"(?:п\.|пункт|раздел|статья|приложение\s*№?)\s*\d+(?:\.\d+)*",
    re.IGNORECASE,
)

SIGNAL_PATTERNS = (
    ("period", PERIOD_RE),
    ("percentage", PERCENT_RE),
    ("money", MONEY_RE),
    ("date", DATE_RE),
    ("clause_ref", CLAUSE_REF_RE),
)


def extract_basic_signals(chunks: list[DocumentChunk]) -> list[RawSignal]:
    signals: list[RawSignal] = []
    seen: set[tuple[str, str, str, int]] = set()

    for chunk in chunks:
        for signal_type, pattern in SIGNAL_PATTERNS:
            for match in pattern.finditer(chunk.text):
                value = match.group(0).strip()
                key = (signal_type, value.lower(), chunk.chunk_id, match.start())
                if key in seen:
                    continue

                seen.add(key)
                signals.append(
                    RawSignal(
                        signal_id=f"signal_{len(signals) + 1:04d}",
                        signal_type=signal_type,
                        value=value,
                        chunk_id=chunk.chunk_id,
                        start=match.start(),
                        end=match.end(),
                    )
                )

    return signals
