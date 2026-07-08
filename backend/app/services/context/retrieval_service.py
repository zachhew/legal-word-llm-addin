import re

from app.schemas.context import DocumentChunk

RISK_REVIEW_KEYWORDS = {
    "ответственность",
    "убытки",
    "штраф",
    "неустойка",
    "пеня",
    "нарушение",
    "возмещение",
    "ограничение ответственности",
    "приемка",
    "оплата",
    "срок",
    "расторжение",
    "конфиденциальность",
    "интеллектуальные права",
    "персональные данные",
    "подсудность",
}

INCONSISTENCY_KEYWORDS = {
    "срок",
    "дней",
    "рабочих дней",
    "календарных дней",
    "оплата",
    "приемка",
    "ответственность",
    "лимит",
    "sla",
    "доступность",
    "инцидент",
    "уведомление",
    "удаление данных",
    "подсудность",
    "применимое право",
    "автопродление",
}

SUMMARY_KEYWORDS = {
    "предмет",
    "стороны",
    "срок",
    "оплата",
    "приемка",
    "ответственность",
    "конфиденциальность",
    "права",
    "расторжение",
    "подсудность",
    "приложение",
}

CLAUSE_REWRITE_KEYWORDS = set()


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9]{3,}", text.lower())}


def _scenario_keywords(scenario: str) -> set[str]:
    if scenario == "risk_review":
        return RISK_REVIEW_KEYWORDS
    if scenario == "inconsistency_check":
        return INCONSISTENCY_KEYWORDS
    if scenario == "clause_rewrite":
        return CLAUSE_REWRITE_KEYWORDS
    return SUMMARY_KEYWORDS


def retrieve_relevant_chunks(
    chunks: list[DocumentChunk],
    scenario: str,
    query: str,
    selected_text: str | None = None,
    selected_party: str | None = None,
    limit: int = 6,
) -> list[DocumentChunk]:
    query_tokens = _tokens(query)
    selected_tokens = _tokens(selected_text or "")
    keywords = _scenario_keywords(scenario)
    scored: list[tuple[float, int, DocumentChunk]] = []

    for index, chunk in enumerate(chunks):
        chunk_text = f"{chunk.title or ''}\n{chunk.text}".lower()
        chunk_tokens = _tokens(chunk_text)
        score = 0.0

        if query_tokens:
            score += len(query_tokens & chunk_tokens) * 2.0

        if selected_tokens:
            score += len(selected_tokens & chunk_tokens) * 1.5

        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in chunk_text:
                score += 3.0 if " " in keyword_lower else 1.2
                if chunk.title and keyword_lower in chunk.title.lower():
                    score += 2.0

        if selected_party and selected_party.lower() in chunk_text:
            score += 3.0

        if chunk.title:
            score += 0.5

        if selected_text and selected_text.strip() and selected_text.strip() in chunk.text:
            score += 8.0

        if score > 0:
            scored.append((score, -index, chunk))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [chunk for _, _, chunk in scored[:limit]]
