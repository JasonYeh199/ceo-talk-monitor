const configuredApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "";
const runningOnVercel = Boolean(process.env.VERCEL);
const localhostPattern = /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/;
const API_BASE_URL = configuredApiBaseUrl || (runningOnVercel ? "" : "http://localhost:8000");
const API_CONFIG_ERROR =
  runningOnVercel && !configuredApiBaseUrl
    ? "NEXT_PUBLIC_API_BASE_URL is not configured in Vercel. Deploy the FastAPI API and set this variable to its public HTTPS URL."
    : runningOnVercel && localhostPattern.test(configuredApiBaseUrl)
      ? "NEXT_PUBLIC_API_BASE_URL points to localhost. Vercel needs a public HTTPS API URL."
      : null;

export async function fetchCompanies() {
  return fetchJson("/companies");
}

export async function fetchTalks(company) {
  return fetchJson(`/talks?company=${encodeURIComponent(company)}`);
}

export async function fetchCompare(company, topic) {
  return fetchJson(`/compare?company=${encodeURIComponent(company)}&topic=${encodeURIComponent(topic)}`);
}

export async function fetchSearch(query) {
  return fetchJson(`/search?q=${encodeURIComponent(query)}`);
}

export async function fetchJobs() {
  return fetchJson("/jobs?limit=5");
}

async function fetchJson(path) {
  if (API_CONFIG_ERROR) {
    return { data: null, error: API_CONFIG_ERROR };
  }

  try {
    const response = await fetch(`${API_BASE_URL.replace(/\/$/, "")}${path}`, {
      cache: "no-store",
      headers: {
        accept: "application/json",
      },
    });
    if (!response.ok) {
      return { data: null, error: `${response.status} ${response.statusText}` };
    }
    return { data: await response.json(), error: null };
  } catch (error) {
    return { data: null, error: error instanceof Error ? error.message : String(error) };
  }
}
