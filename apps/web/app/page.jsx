import { fetchCompanies, fetchCompare, fetchSearch, fetchTalks } from "../lib/api";

export const dynamic = "force-dynamic";

const DEFAULT_COMPANY = "NVDA";
const DEFAULT_TOPIC = "AI demand";
const DEFAULT_QUERY = "Jensen Huang supply constraint";

export default async function Home({ searchParams }) {
  const params = await searchParams;
  const company = String(params?.company || DEFAULT_COMPANY).toUpperCase();
  const topic = String(params?.topic || DEFAULT_TOPIC);
  const query = String(params?.q || DEFAULT_QUERY);

  const [companiesResult, talksResult, compareResult, searchResult] = await Promise.all([
    fetchCompanies(),
    fetchTalks(company),
    fetchCompare(company, topic),
    fetchSearch(query),
  ]);

  const companies = companiesResult.data || [];
  const talks = talksResult.data || [];
  const compare = compareResult.data || { timeline: [] };
  const search = searchResult.data || { vector_results: [], text_results: [] };
  const errors = [companiesResult, talksResult, compareResult, searchResult].filter((result) => result.error);

  const readyCount = talks.filter((talk) => talk.status === "ready").length;
  const tones = countBy(talks, (talk) => talk.summary?.management_tone || "pending");

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
        <Metric label="Optimistic" value={tones["樂觀"] || 0} />
        <Metric label="Neutral" value={tones["中性"] || 0} />
        <Metric label="Conservative" value={tones["保守"] || 0} />
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

function countBy(items, getKey) {
  return items.reduce((acc, item) => {
    const key = getKey(item);
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

