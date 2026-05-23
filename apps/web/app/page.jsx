import { fetchCompanies, fetchCompare, fetchJobs, fetchSearch, fetchTalks } from "../lib/api";

export const dynamic = "force-dynamic";

const DEFAULT_COMPANY = "NVDA";
const DEFAULT_TOPIC = "AI demand";
const DEFAULT_QUERY = "Jensen Huang supply constraint";

export default async function Home({ searchParams }) {
  const params = await searchParams;
  const company = String(params?.company || DEFAULT_COMPANY).toUpperCase();
  const topic = String(params?.topic || DEFAULT_TOPIC);
  const query = String(params?.q || DEFAULT_QUERY);

  const [companiesResult, talksResult, compareResult, searchResult, jobsResult] = await Promise.all([
    fetchCompanies(),
    fetchTalks(company),
    fetchCompare(company, topic),
    fetchSearch(query),
    fetchJobs(),
  ]);

  const companies = companiesResult.data || [];
  const talks = talksResult.data || [];
  const compare = compareResult.data || { timeline: [] };
  const search = searchResult.data || { vector_results: [], text_results: [] };
  const jobs = jobsResult.data || [];
  const errors = [companiesResult, talksResult, compareResult, searchResult, jobsResult].filter((result) => result.error);
  const latestJob = jobs[0];

  const readyCount = talks.filter((talk) => talk.status === "ready").length;
  const toneCounts = {
    optimistic: countTone(talks, ["optimistic", "positive", "bullish", "\u6a02\u89c0"]),
    neutral: countTone(talks, ["neutral", "\u4e2d\u6027"]),
    conservative: countTone(talks, ["conservative", "cautious", "\u4fdd\u5b88"]),
  };

  return (
    <main>
      <header className="topbar">
        <div>
          <p className="eyebrow">Research Workspace</p>
          <h1>CEO Talk Monitor</h1>
        </div>
        <div className="status-strip">
          <span>{company}</span>
          <span>{readyCount}/{talks.length} ready</span>
          <span>{compare.count || 0} topic hits</span>
          <span>{latestJob ? `${latestJob.job_name}: ${latestJob.status}` : "no jobs"}</span>
        </div>
      </header>

      <section className="controls">
        <form className="control-group">
          <label>
            Company
            <select name="company" defaultValue={company}>
              {companies.length === 0 ? <option value={company}>{company}</option> : null}
              {companies.map((item) => (
                <option key={item.ticker} value={item.ticker}>
                  {item.ticker} - {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Topic
            <input name="topic" defaultValue={topic} />
          </label>
          <label>
            Search
            <input name="q" defaultValue={query} />
          </label>
          <button type="submit">Apply</button>
        </form>
      </section>

      {errors.length > 0 ? (
        <section className="notice">
          <strong>API connection issue</strong>
          <span>{errors[0].error}</span>
        </section>
      ) : null}

      <section className="metrics">
        <Metric label="Talks" value={talks.length} />
        <Metric label="Ready" value={readyCount} />
        <Metric label="Optimistic" value={toneCounts.optimistic} />
        <Metric label="Neutral" value={toneCounts.neutral} />
        <Metric label="Conservative" value={toneCounts.conservative} />
      </section>

      <section className="workspace">
        <div className="main-column">
          <SectionTitle title="Talks" subtitle={`${company} executive interviews`} />
          <div className="talk-table" role="table">
            <div className="table-row table-head" role="row">
              <span>Title</span>
              <span>Tone</span>
              <span>Status</span>
              <span>Score</span>
            </div>
            {talks.map((talk) => (
              <a className="table-row" href={talk.source_url} key={talk.id} role="row">
                <span>
                  <strong>{talk.title}</strong>
                  <small>
                    {talk.executive || "Unknown"} {talk.role ? `(${talk.role})` : ""}
                  </small>
                </span>
                <span>{talk.summary?.management_tone || "-"}</span>
                <span>{talk.status}</span>
                <span>{talk.relevance_score}</span>
              </a>
            ))}
          </div>
        </div>

        <aside className="side-column">
          <SectionTitle title="Topic Compare" subtitle={topic} />
          <div className="timeline">
            {(compare.timeline || []).map((item) => (
              <a className="timeline-item" href={item.source_url} key={item.talk_id}>
                <span className="tone">{item.tone || "-"}</span>
                <strong>{item.title}</strong>
                <p>{item.one_liner}</p>
              </a>
            ))}
          </div>
        </aside>
      </section>

      <section className="search-band">
        <SectionTitle title="Search" subtitle={query} />
        <div className="search-grid">
          <ResultList title="Vector" items={search.vector_results || []} kind="vector" />
          <ResultList title="Text" items={search.text_results || []} kind="text" />
        </div>
      </section>

      <section className="operations-band">
        <SectionTitle title="Operations" subtitle="Recent ingestion runs" />
        <div className="job-list">
          {jobs.length === 0 ? <p className="empty">No runs</p> : null}
          {jobs.map((job) => (
            <div className="job-row" key={job.id}>
              <span className={`job-status ${job.status}`}>{job.status}</span>
              <strong>{job.job_name}</strong>
              <span>{job.source}{job.company ? ` / ${job.company}` : ""}</span>
              <span>{formatDate(job.started_at)}</span>
              <span>{formatDuration(job.duration_seconds)}</span>
              <span>{job.metrics?.accepted_total ?? "-"} accepted</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SectionTitle({ title, subtitle }) {
  return (
    <div className="section-title">
      <h2>{title}</h2>
      <span>{subtitle}</span>
    </div>
  );
}

function ResultList({ title, items, kind }) {
  return (
    <div className="result-list">
      <h3>{title}</h3>
      {items.length === 0 ? <p className="empty">No results</p> : null}
      {items.map((item) => {
        const payload = item.payload || item;
        const key = `${kind}-${payload.talk_id || item.id}`;
        return (
          <a href={payload.source_url} key={key}>
            <strong>{payload.title}</strong>
            <small>
              {payload.company || ""} {payload.executive ? `- ${payload.executive}` : ""}
              {item.score ? ` - score ${item.score.toFixed(3)}` : ""}
            </small>
            {payload.one_liner ? <p>{payload.one_liner}</p> : null}
          </a>
        );
      })}
    </div>
  );
}

function countTone(items, aliases) {
  return items.reduce((count, item) => {
    const tone = String(item.summary?.management_tone || "").toLowerCase();
    const matches = aliases.some((alias) => tone.includes(alias.toLowerCase()));
    return matches ? count + 1 : count;
  }, 0);
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDuration(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (value < 60) {
    return `${Math.round(value)}s`;
  }
  return `${Math.round(value / 60)}m`;
}
