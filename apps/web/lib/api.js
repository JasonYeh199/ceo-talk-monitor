const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

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

async function fetchJson(path) {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
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

