import { describe, expect, it } from 'vitest';
import { ANALYTES, searchAnalytes } from '../src/engine/analytes';
import { molarMass } from '../src/engine/atomic';
import { convert } from '../src/engine/convert';

const an = (id: string) => ANALYTES.find((a) => a.id === id)!;
const val = (id: string, v: number, f: string, t: string) => {
  const r = convert(an(id), v, f, t);
  if (!r.ok) throw new Error(r.reason);
  return r.value;
};

describe('molar mass (IUPAC conventional weights)', () => {
  it('glucose', () => expect(molarMass('C6H12O6')).toBeCloseTo(180.156, 3));
  it('creatinine', () => expect(molarMass('C4H7N3O')).toBeCloseTo(113.12, 3));
  it('urea', () => expect(molarMass('CH4N2O')).toBeCloseTo(60.056, 3));
});

describe('UCUM scale only', () => {
  it('g/dL -> g/L', () => expect(val('hemoglobin', 13, 'g/dL', 'g/L')).toBeCloseTo(130, 9));
  it('U/L -> ukat/L (1 U = 1 umol/min)', () => expect(val('alt', 60, 'U/L', 'ukat/L')).toBeCloseTo(1, 9));
});

describe('mass <-> substance via computed MW', () => {
  it('glucose 100 mg/dL ~ 5.55 mmol/L', () => expect(val('glucose', 100, 'mg/dL', 'mmol/L')).toBeCloseTo(5.5507, 3));
  it('roundtrip', () => {
    const x = val('creatinine', 1.0, 'mg/dL', 'umol/L');
    expect(val('creatinine', x, 'umol/L', 'mg/dL')).toBeCloseTo(1.0, 9);
  });
  it('creatinine 1 mg/dL ~ 88.4 umol/L', () => expect(val('creatinine', 1, 'mg/dL', 'umol/L')).toBeCloseTo(88.4, 0));
  it('TG 150 mg/dL ~ 1.69 mmol/L (triolein assumption)', () =>
    expect(val('triglycerides', 150, 'mg/dL', 'mmol/L')).toBeCloseTo(1.694, 2));
  it('BUN 14 mg/dL ~ 5.0 mmol/L urea', () => expect(val('bun', 14, 'mg/dL', 'mmol/L')).toBeCloseTo(5.0, 1));
});

describe('equivalents use ion charge', () => {
  it('Na 140 mEq/L = 140 mmol/L', () => expect(val('sodium', 140, 'mEq/L', 'mmol/L')).toBeCloseTo(140, 9));
  it('Ca 2.5 mmol/L = 5 mEq/L', () => expect(val('calcium', 2.5, 'mmol/L', 'mEq/L')).toBeCloseTo(5, 9));
  it('Ca 10 mg/dL ~ 2.495 mmol/L', () => expect(val('calcium', 10, 'mg/dL', 'mmol/L')).toBeCloseTo(2.495, 2));
  it('Ca 10 mg/dL ~ 4.99 mEq/L', () => expect(val('calcium', 10, 'mg/dL', 'mEq/L')).toBeCloseTo(4.99, 1));
});

describe('special conversions', () => {
  it('HbA1c IFCC 48 -> NGSP ~6.5', () => expect(val('hba1c', 48, 'mmol/mol', '%')).toBeCloseTo(6.543, 2));
  it('HbA1c NGSP 6.5 -> IFCC ~47.5', () => expect(val('hba1c', 6.5, '%', 'mmol/mol')).toBeCloseTo(47.5, 0));
  it('HbA1c roundtrip', () => expect(val('hba1c', val('hba1c', 7, '%', 'mmol/mol'), 'mmol/mol', '%')).toBeCloseTo(7, 9));
  it('uACR 30 mg/g ~ 3.39 mg/mmol (KDIGO rounds to 3)', () => expect(val('uacr', 30, 'mg/g', 'mg/mmol')).toBeCloseTo(3.39, 1));
  it('uPCR 150 mg/g -> mg/mmol roundtrip', () =>
    expect(val('upcr', val('upcr', 150, 'mg/g', 'mg/mmol'), 'mg/mmol', 'mg/g')).toBeCloseTo(150, 9));
});

describe('rejections (no basis)', () => {
  const rej = (id: string, f: string, t: string) => {
    const r = convert(an(id), 1, f, t);
    expect(r.ok).toBe(false);
    return r.ok ? '' : r.reason;
  };
  it('mg/dL -> U/L', () => expect(rej('alt', 'mg/dL', 'U/L')).toMatch(/효소|차원/));
  it('glucose mg/dL -> U/L', () => expect(rej('glucose', 'mg/dL', 'U/L')).toMatch(/차원|효소/));
  it('albumin g/dL -> mmol/L (no MW)', () => expect(rej('albumin', 'g/dL', 'mmol/L')).toMatch(/분자량/));
  it('glucose mmol/L -> mEq/L (no charge)', () => expect(rej('glucose', 'mmol/L', 'mEq/L')).toMatch(/전하/));
  it('phosphate mmol/L -> mEq/L', () => expect(rej('phosphate', 'mmol/L', 'mEq/L')).toMatch(/전하/));
  it('bad unit', () => expect(rej('glucose', 'foo', 'mmol/L')).toMatch(/단위/));
  it('hba1c unsupported pair', () => expect(rej('hba1c', '%', 'mg/dL')).toMatch(/공식 변환/));
});

describe('search (en/ko/synonym)', () => {
  it('Korean', () => expect(searchAnalytes('혈당').map((a) => a.id)).toContain('glucose'));
  it('synonym', () => expect(searchAnalytes('GPT').map((a) => a.id)).toContain('alt'));
  it('English', () => expect(searchAnalytes('creat').map((a) => a.id)).toContain('creatinine'));
});

// 교차 검증용 자료(Labcorp, CMEinfo, NBME)는 접속 불가로 대조하지 못했다.
describe('cross-validation against published tables', () => {
  it.todo('TODO(verify): Labcorp SI Unit Conversion Table 대조');
  it.todo('TODO(verify): CMEinfo 변환표 PDF 대조');
  it.todo('TODO(verify): NBME Laboratory Reference Values PDF 대조');
});
