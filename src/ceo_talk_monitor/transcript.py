from __future__ import annotations

import json
from pathlib import Path

from ceo_talk_monitor.config import TranscriptionConfig
from ceo_talk_monitor.schemas import TranscriptPayload, TranscriptSegmentPayload


class TranscriptProcessor:
    def __init__(self, config: TranscriptionConfig):
        self.config = config

    def transcribe(self, audio_path: str | Path) -> TranscriptPayload:
        provider = self.config.provider.lower()
        if provider == "faster_whisper":
            return self._transcribe_faster_whisper(audio_path)
        if provider == "openai":
            return self._transcribe_openai(audio_path)
        if provider == "none":
            return TranscriptPayload(language=self.config.language, segments=[])
        raise ValueError(f"Unsupported transcription provider: {self.config.provider}")

    def _transcribe_faster_whisper(self, audio_path: str | Path) -> TranscriptPayload:
        from faster_whisper import WhisperModel

        model = WhisperModel(self.config.model_size, device=self.config.device, compute_type=self.config.compute_type)
        segments, info = model.transcribe(str(audio_path), language=self.config.language)
        payload_segments = [
            TranscriptSegmentPayload(
                start_seconds=float(segment.start),
                end_seconds=float(segment.end),
                text=segment.text.strip(),
                speaker=None,
            )
            for segment in segments
            if segment.text.strip()
        ]
        return TranscriptPayload(language=getattr(info, "language", self.config.language), segments=payload_segments)

    def _transcribe_openai(self, audio_path: str | Path) -> TranscriptPayload:
        from openai import OpenAI

        client = OpenAI()
        with Path(audio_path).open("rb") as handle:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=handle,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
        segments = getattr(result, "segments", None) or []
        payload_segments = [
            TranscriptSegmentPayload(
                start_seconds=float(_segment_value(segment, "start", 0.0)),
                end_seconds=float(_segment_value(segment, "end", 0.0)),
                text=str(_segment_value(segment, "text", "")).strip(),
            )
            for segment in segments
            if str(_segment_value(segment, "text", "")).strip()
        ]
        if not payload_segments:
            text = getattr(result, "text", "")
            payload_segments = [TranscriptSegmentPayload(start_seconds=0.0, end_seconds=0.0, text=text)]
        return TranscriptPayload(language=self.config.language, segments=payload_segments)

    @staticmethod
    def write_transcript(payload: TranscriptPayload, output_dir: str | Path, stem: str) -> Path:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        transcript_path = output_path / f"{stem}.json"
        with transcript_path.open("w", encoding="utf-8") as handle:
            json.dump(payload.model_dump(), handle, ensure_ascii=False, indent=2)
        txt_path = output_path / f"{stem}.txt"
        with txt_path.open("w", encoding="utf-8") as handle:
            for segment in payload.segments:
                handle.write(f"[{segment.start_seconds:.2f}-{segment.end_seconds:.2f}] {segment.text}\n")
        return transcript_path


def _segment_value(segment, key: str, default):
    if isinstance(segment, dict):
        return segment.get(key, default)
    return getattr(segment, key, default)
