from __future__ import annotations

import re
from dataclasses import dataclass

from ceo_talk_monitor.config import CompanyConfig, RelevanceConfig
from ceo_talk_monitor.schemas import MediaCandidate, RelevanceResult


@dataclass(frozen=True)
class MatchedExecutive:
    name: str | None
    role: str | None
    score: float
    reasons: list[str]


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.lower()).strip()


def contains_phrase(text: str, phrase: str) -> bool:
    phrase_clean = phrase.strip()
    normalized = normalize_text(phrase_clean)
    if not normalized:
        return False
    if phrase_clean.isupper() and len(phrase_clean) <= 5:
        return bool(re.search(rf"\b{re.escape(normalized)}\b", text))
    return normalized in text


def _best_executive_match(text: str, company: CompanyConfig) -> MatchedExecutive:
    best = MatchedExecutive(None, None, 0.0, [])
    for executive in company.executives:
        score = 0.0
        reasons: list[str] = []
        for name in executive.all_names:
            if contains_phrase(text, name):
                score += 5.0
                reasons.append(f"matched executive: {name}")
                break
        if contains_phrase(text, executive.role):
            score += 1.0
            reasons.append(f"matched role: {executive.role}")
        if score > best.score:
            best = MatchedExecutive(executive.name, executive.role, score, reasons)
    return best


def score_candidate(candidate: MediaCandidate, company: CompanyConfig, config: RelevanceConfig) -> RelevanceResult:
    title = normalize_text(candidate.title)
    text = normalize_text(" ".join(filter(None, [candidate.title, candidate.description, candidate.feed_name])))
    score = 0.0
    reasons: list[str] = []

    for company_name in company.all_company_names:
        if contains_phrase(text, company_name):
            score += 3.0 if company_name.upper() == company.ticker.upper() else 2.0
            reasons.append(f"matched company: {company_name}")
            break

    exec_match = _best_executive_match(text, company)
    score += exec_match.score
    reasons.extend(exec_match.reasons)

    include_hits = 0
    for term in config.include_terms:
        if contains_phrase(text, term):
            include_hits += 1
            score += 1.5
            reasons.append(f"include term: {term}")

    if _speaker_quote_signal(title, company, exec_match):
        score += 1.0
        include_hits += 1
        reasons.append("speaker quote/title signal")

    for term in config.exclude_terms:
        if contains_phrase(text, term):
            score -= 3.0
            reasons.append(f"exclude term: {term}")

    if exec_match.name is not None and include_hits == 0:
        score -= 2.0
        reasons.append("no interview/speaking signal")

    if candidate.source == "youtube" and "cnbc" in text:
        score += 1.0
        reasons.append("CNBC source/title signal")

    passed = score >= config.threshold and exec_match.name is not None
    return RelevanceResult(
        passed=passed,
        score=round(score, 2),
        company_ticker=company.ticker.upper(),
        executive_name=exec_match.name,
        executive_role=exec_match.role,
        reasons=reasons,
    )


def _speaker_quote_signal(title: str, company: CompanyConfig, exec_match: MatchedExecutive) -> bool:
    if not exec_match.name:
        return False
    executive = normalize_text(exec_match.name)
    role = normalize_text(exec_match.role)
    company_terms = [normalize_text(company.ticker), normalize_text(company.name), *[normalize_text(alias) for alias in company.aliases]]
    if re.search(rf"\b{re.escape(executive)}\s*:", title):
        return True
    if role and re.search(rf"\b{re.escape(role)}\s+{re.escape(executive)}\s*:", title):
        return True
    return any(
        term and role and re.search(rf"\b{re.escape(term)}\s+{re.escape(role)}\s+{re.escape(executive)}\s*:", title)
        for term in company_terms
    )
