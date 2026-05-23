from __future__ import annotations

import json
import re
from typing import Any

from ceo_talk_monitor.config import SummarizationConfig, get_settings
from ceo_talk_monitor.prompts import SUMMARY_SYSTEM_PROMPT, build_summary_user_prompt
from ceo_talk_monitor.schemas import SummaryPayload, TranscriptPayload


SIGNAL_TERMS = {
    "guidance": ["guidance", "outlook", "forecast", "guide"],
    "demand": ["demand", "orders", "backlog", "customer"],
    "pricing": ["pricing", "price", "asp"],
    "margin": ["margin", "gross margin", "operating margin"],
    "capex": ["capex", "capital expenditure", "data center investment"],
    "ai": ["ai", "artificial intelligence", "accelerated computing", "gpu"],
    "cloud": ["cloud", "hyperscaler", "azure", "aws", "google cloud"],
    "china": ["china", "export control", "geopolitical"],
    "supply_chain": ["supply", "constraint", "capacity", "lead time", "inventory"],
}


class Summarizer:
    def __init__(self, config: SummarizationConfig):
        self.config = config

    def summarize(
        self,
        *,
        title: str,
        company_ticker: str,
        executive_name: str | None,
        executive_role: str | None,
        source_url: str,
        transcript: TranscriptPayload,
        previous_summaries: list[str] | None = None,
    ) -> SummaryPayload:
        if self.config.provider.lower() == "openai":
            try:
                return self._summarize_openai(
                    title=title,
                    company_ticker=company_ticker,
                    executive_name=executive_name,
                    executive_role=executive_role,
                    source_url=source_url,
                    transcript=transcript,
                )
            except Exception as exc:
                return self._summarize_heuristic(
                    title=title,
                    company_ticker=company_ticker,
                    executive_name=executive_name,
                    executive_role=executive_role,
                    source_url=source_url,
                    transcript=transcript,
                    error=f"OpenAI summary failed: {exc}",
                )
        return self._summarize_heuristic(
            title=title,
            company_ticker=company_ticker,
            executive_name=executive_name,
            executive_role=executive_role,
            source_url=source_url,
            transcript=transcript,
        )

    def _summarize_openai(
        self,
        *,
        title: str,
        company_ticker: str,
        executive_name: str | None,
        executive_role: str | None,
        source_url: str,
        transcript: TranscriptPayload,
    ) -> SummaryPayload:
        from openai import OpenAI

        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        client = OpenAI(api_key=settings.openai_api_key)
        transcript_text = _timestamped_text(transcript)[: self.config.max_transcript_chars]
        response = client.responses.create(
            model=settings.openai_summary_model or self.config.model,
            input=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_summary_user_prompt(
                        title=title,
                        company_ticker=company_ticker,
                        executive_name=executive_name,
                        executive_role=executive_role,
                        source_url=source_url,
                        transcript=transcript_text,
                    ),
                },
            ],
        )
        raw_text = getattr(response, "output_text", "") or ""
        data = _load_json_object(raw_text)
        return SummaryPayload(
            one_liner=data.get("one_liner") or title,
            management_tone=data.get("management_tone") or "中性",
            core_topics=list(data.get("core_topics") or []),
            signals=dict(data.get("signals") or {}),
            quotes=list(data.get("quotes") or []),
            changes_vs_prior=data.get("changes_vs_prior"),
            investable_hypotheses=list(data.get("investable_hypotheses") or []),
            risks=list(data.get("risks") or []),
            source_url=data.get("source_url") or source_url,
            raw=data,
        )

    def _summarize_heuristic(
        self,
        *,
        title: str,
        company_ticker: str,
        executive_name: str | None,
        executive_role: str | None,
        source_url: str,
        transcript: TranscriptPayload,
        error: str | None = None,
    ) -> SummaryPayload:
        text = transcript.text
        sentences = _split_sentences(text)
        signals: dict[str, Any] = {}
        topics: list[str] = []
        quotes: list[str] = []
        for signal, terms in SIGNAL_TERMS.items():
            matched = _first_sentence_with_terms(sentences, terms)
            if matched:
                signals[signal] = matched
                topics.append(signal)
                if len(quotes) < 3:
                    quotes.append(matched[:280])
            else:
                signals[signal] = "未提及或逐字稿不足"

        tone = _infer_tone(text)
        speaker = executive_name or executive_role or "management"
        one_liner = f"{company_ticker} {speaker} 訪談重點偏{tone}，主要議題為 {', '.join(topics[:4]) if topics else '逐字稿待補'}。"
        raw = {"provider": "heuristic"}
        if error:
            raw["warning"] = error
        return SummaryPayload(
            one_liner=one_liner,
            management_tone=tone,
            core_topics=topics[:8],
            signals=signals,
            quotes=quotes,
            changes_vs_prior="無足夠歷史資料；請使用 compare 指令檢視同主題歷史摘要。",
            investable_hypotheses=[
                f"追蹤 {company_ticker} 管理層後續是否重複提到 {topic}。"
                for topic in topics[:3]
            ],
            risks=["規則式摘要可能漏掉語境；重要投資決策前請回看原始片段與完整逐字稿。"],
            source_url=source_url,
            raw=raw,
        )


def _timestamped_text(transcript: TranscriptPayload) -> str:
    return "\n".join(
        f"[{segment.start_seconds:.2f}-{segment.end_seconds:.2f}] {segment.text}"
        for segment in transcript.segments
    )


def _load_json_object(raw_text: str) -> dict[str, Any]:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+", text)
    return [chunk.strip() for chunk in chunks if len(chunk.strip()) > 20]


def _first_sentence_with_terms(sentences: list[str], terms: list[str]) -> str | None:
    lower_terms = [term.lower() for term in terms]
    for sentence in sentences:
        lowered = sentence.lower()
        if any(term in lowered for term in lower_terms):
            return sentence
    return None


def _infer_tone(text: str) -> str:
    lowered = text.lower()
    optimistic = sum(lowered.count(word) for word in ["strong", "growth", "accelerating", "robust", "confident"])
    cautious = sum(lowered.count(word) for word in ["uncertain", "challenge", "constraint", "risk", "slowdown"])
    if optimistic > cautious + 1:
        return "樂觀"
    if cautious > optimistic + 1:
        return "保守"
    return "中性"

