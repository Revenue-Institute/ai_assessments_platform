import taxonomyJson from "./taxonomy.json";

export type Competency = {
  id: string;
  domain: string;
  label: string;
  parent_id: string | null;
  description?: string;
};

export const taxonomy: Competency[] = taxonomyJson as Competency[];

export const competencyIds: string[] = taxonomy.map((c) => c.id);
export const competencyIdSet: Set<string> = new Set(competencyIds);

export function isValidCompetencyId(id: string): boolean {
  return competencyIdSet.has(id);
}

export function competenciesByDomain(domain: string): Competency[] {
  return taxonomy.filter((c) => c.domain === domain);
}

export function childrenOf(parentId: string): Competency[] {
  return taxonomy.filter((c) => c.parent_id === parentId);
}
