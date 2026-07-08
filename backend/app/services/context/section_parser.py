import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedSection:
    title: str
    text: str
    start_char: int
    end_char: int
    section_path: list[str]


SECTION_PATTERNS = (
    re.compile(r"^\s*\d{1,2}\.\s+[А-ЯA-ZЁ][^\n]{2,120}$"),
    re.compile(r"^\s*Раздел\s+\d+[.\s]+[А-ЯA-ZЁ][^\n]{0,120}$", re.IGNORECASE),
    re.compile(r"^\s*Статья\s+\d+[.\s]+[А-ЯA-ZЁ][^\n]{0,120}$", re.IGNORECASE),
    re.compile(r"^\s*Приложение\s*(?:№|N)?\s*\d+[^\n]{0,120}$", re.IGNORECASE),
)


def detect_section_title(line: str) -> str | None:
    candidate = line.strip()
    if not candidate or len(candidate) > 140:
        return None

    if any(pattern.match(candidate) for pattern in SECTION_PATTERNS):
        return candidate

    letters = re.findall(r"[A-Za-zА-Яа-яЁё]", candidate)
    if 3 <= len(letters) <= 80:
        uppercase_letters = re.findall(r"[A-ZА-ЯЁ]", candidate)
        if len(uppercase_letters) / len(letters) >= 0.75:
            return candidate

    return None


def parse_sections(text: str) -> list[ParsedSection]:
    lines = text.splitlines(keepends=True)
    detected: list[tuple[str, int]] = []
    position = 0

    for line in lines:
        title = detect_section_title(line)
        if title:
            detected.append((title, position))
        position += len(line)

    if not detected:
        return [
            ParsedSection(
                title="Document",
                text=text,
                start_char=0,
                end_char=len(text),
                section_path=["Document"],
            )
        ]

    sections: list[ParsedSection] = []
    for index, (title, start_char) in enumerate(detected):
        end_char = detected[index + 1][1] if index + 1 < len(detected) else len(text)
        section_text = text[start_char:end_char].strip()
        sections.append(
            ParsedSection(
                title=title,
                text=section_text,
                start_char=start_char,
                end_char=end_char,
                section_path=[title],
            )
        )

    return sections
