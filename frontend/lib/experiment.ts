import type { Condition, PoolMode, Surface } from "./types";

export const conditions: Condition[] = [
  "control_recommendation",
  "treatment_search",
  "treatment_problematic_content",
];

export const testerConditions: Condition[] = [
  "control_recommendation",
  "treatment_problematic_content",
];

export const defaultCondition: Condition = "treatment_problematic_content";

export function isCondition(value: string | null | undefined): value is Condition {
  return conditions.includes(value as Condition);
}

export function normalizeCondition(value: string | null | undefined): Condition {
  return isCondition(value) ? value : defaultCondition;
}

export function isPoolMode(value: string | null | undefined): value is PoolMode {
  return value === "safe" || value === "problematic" || value === "mixed";
}

export function poolModeForCondition(condition: Condition, requested?: string | null): PoolMode {
  if (isPoolMode(requested)) return requested;
  return condition === "treatment_problematic_content" ? "mixed" : "safe";
}

export function conditionLabel(condition: Condition): string {
  if (condition === "control_recommendation") return "Standardfeed";
  if (condition === "treatment_problematic_content") return "Balanceret feed";
  return "Søgning først";
}

export function conditionCopy(condition: Condition): string {
  if (condition === "treatment_search") {
    return "Søgning fremhæves, så forskere kan sammenligne aktiv opdagelse med passive anbefalinger.";
  }
  if (condition === "treatment_problematic_content") {
    return "En balanceret feed-variant vises til sammenlignende målinger.";
  }
  return "Standardfeedet med anbefalinger vises som sammenligningsgrundlag.";
}

export function conditionQuery(condition: Condition): string {
  return `condition=${encodeURIComponent(condition)}`;
}

export function appendCondition(path: string, condition: Condition): string {
  const joiner = path.includes("?") ? "&" : "?";
  return `${path}${joiner}${conditionQuery(condition)}`;
}

export function validSurface(value: string | undefined): Surface {
  return value === "search" || value === "related" || value === "shorts" || value === "recommendation" ? value : "recommendation";
}
