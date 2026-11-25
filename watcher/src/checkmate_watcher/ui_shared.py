"""Fragments JavaScript partages par les interfaces locales."""

API_JS = """async function api(path, body) {
  const options = {
    method: body ? "POST" : "GET",
    headers: { "X-CheckMate-Token": TOKEN },
  };
  if (body) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || ("erreur " + response.status));
  }
  return data;
}"""
