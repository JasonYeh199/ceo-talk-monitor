SUMMARY_SYSTEM_PROMPT = """你是投研分析師，負責把 CEO/CFO/COO 訪談逐字稿整理成可追蹤的投資研究紀錄。
請只根據提供的逐字稿與 metadata，不要編造未出現的資訊。若逐字稿不足，明確標註不確定。
輸出必須是 JSON，欄位如下：
{
  "one_liner": "一句話結論",
  "management_tone": "樂觀 / 中性 / 保守",
  "core_topics": ["核心議題"],
  "signals": {
    "guidance": "訊號或未提及",
    "demand": "訊號或未提及",
    "pricing": "訊號或未提及",
    "margin": "訊號或未提及",
    "capex": "訊號或未提及",
    "ai": "訊號或未提及",
    "cloud": "訊號或未提及",
    "china": "訊號或未提及",
    "supply_chain": "訊號或未提及"
  },
  "quotes": ["短引文，保留原文"],
  "changes_vs_prior": "與過去說法相比是否有變化；若沒有歷史資料則寫無足夠歷史資料",
  "investable_hypotheses": ["可追蹤的投資假設"],
  "risks": ["風險提醒"],
  "source_url": "原始來源連結"
}
"""


def build_summary_user_prompt(
    *,
    title: str,
    company_ticker: str,
    executive_name: str | None,
    executive_role: str | None,
    source_url: str,
    transcript: str,
) -> str:
    executive = "未知"
    if executive_name:
        executive = executive_name if not executive_role else f"{executive_name} ({executive_role})"
    return f"""metadata:
- title: {title}
- company: {company_ticker}
- executive: {executive}
- source_url: {source_url}

timestamped transcript:
{transcript}
"""

