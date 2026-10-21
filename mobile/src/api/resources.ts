import { USE_MOCK } from "../config";
import { api } from "./client";
import { MOCK_RESOURCES, type Resource } from "./mock";

export type { Resource };

export async function listResources(): Promise<Resource[]> {
  if (USE_MOCK) return MOCK_RESOURCES;
  const page = await api<{ items: Resource[] }>("/resources");
  return page.items;
}
