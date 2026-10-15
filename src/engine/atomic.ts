// IUPAC(CIAAW) 약식(conventional) 표준 원자량, g/mol.
// TODO(verify): ciaaw.org 에 접속할 수 없어 값을 1차 출처와 대조하지 못했다.
export const ATOMIC_WEIGHTS: Record<string, number> = {
  H: 1.008,
  C: 12.011,
  N: 14.007,
  O: 15.999,
  Na: 22.99,
  Mg: 24.305,
  P: 30.974,
  S: 32.06,
  Cl: 35.45,
  K: 39.098,
  Ca: 40.078,
  Fe: 55.845,
  Cu: 63.546,
  Zn: 65.38,
};

export interface FormulaPart {
  symbol: string;
  count: number;
  weight: number;
}

export function parseFormula(formula: string): FormulaPart[] {
  const parts: FormulaPart[] = [];
  const re = /([A-Z][a-z]?)(\d*)/g;
  let consumed = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(formula)) !== null) {
    const w = ATOMIC_WEIGHTS[m[1]];
    if (w === undefined) throw new Error(`원자량 없음: ${m[1]}`);
    parts.push({ symbol: m[1], count: m[2] ? Number(m[2]) : 1, weight: w });
    consumed += m[0].length;
  }
  if (consumed !== formula.length) throw new Error(`화학식 해석 실패: ${formula}`);
  return parts;
}

export function molarMass(formula: string): number {
  return parseFormula(formula).reduce((s, p) => s + p.count * p.weight, 0);
}

export function molarMassBreakdown(formula: string): string {
  const parts = parseFormula(formula);
  return `${formula} = ${parts.map((p) => `${p.count}×${p.weight}`).join(' + ')} = ${molarMass(formula).toFixed(3)} g/mol`;
}
