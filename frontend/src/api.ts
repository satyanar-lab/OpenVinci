export type ConfigResponse = {
  project: string;
  module: string;
  source: string;
  data: { class: string; [k: string]: unknown };
};

export async function fetchConfig(
  module = "Com",
  project = "canapp-min",
): Promise<ConfigResponse> {
  const url = `/api/config?project=${encodeURIComponent(project)}&module=${encodeURIComponent(module)}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`GET ${url} → ${response.status}`);
  }
  return (await response.json()) as ConfigResponse;
}
