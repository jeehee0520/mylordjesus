export interface Source {
  label: string;
  url: string;
}

export interface Basis {
  method: string;
  /** 단위 x → 단위 y 로 환산할 때 곱해지는 실효 계수(비선형이면 null) */
  coefficient: number | null;
  formula: string;
  steps: string[];
  assumptions: string[];
  sources: Source[];
}

export type ConvResult = { ok: true; value: number; basis: Basis } | { ok: false; reason: string };

export interface Analyte {
  id: string;
  nameEn: string;
  nameKo: string;
  synonyms: string[];
  category: string;
  /** 분자량 계산용 화학식 (질량↔물질량 변환 근거) */
  formula?: string;
  /** 이온 전하 절댓값 (mEq 변환 근거) */
  charge?: number;
  /** 화학식/전하에 대한 가정 설명 */
  assumption?: string;
  units: string[];
  defaultFrom: string;
  defaultTo: string;
  /** 비선형·공식 기반 특수 변환 */
  special?: SpecialConversion;
}

export interface SpecialConversion {
  from: string;
  to: string;
  forward: (x: number) => number;
  inverse: (y: number) => number;
  method: string;
  formula: string;
  inverseFormula: string;
  assumptions: string[];
  sources: Source[];
  /** 선형이면 계수(from→to) */
  coefficient?: () => number;
}
