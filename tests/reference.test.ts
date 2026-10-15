import { describe, expect, it } from 'vitest';
import { REFERENCE_INTERVALS } from '../src/data/referenceIntervals';
import { judge, lookup } from '../src/reference/lookup';
import type { RefInterval } from '../src/reference/types';

// 아래 값은 로직 검증용 가상 fixture 이며 실제 공표값이 아니다(앱에는 포함되지 않음).
const mk = (o: Partial<RefInterval>): RefInterval => ({
  analyteId: 'x', specimen: 'serum', sex: 'any', ageMinYears: 18, ageMaxYears: null,
  low: 10, high: 20, unit: 'u', ageLabel: '>=18', source: 'fixture', sourceUrl: '', ...o,
});
const data = [
  mk({ sex: 'M', low: 12, high: 22, ageMinYears: 18, ageMaxYears: 60 }),
  mk({ sex: 'any', low: 10, high: 20, ageMinYears: 18, ageMaxYears: 60 }),
  mk({ sex: 'any', low: null, high: 30, ageMinYears: 60, ageMaxYears: null }),
];
const q = { analyteId: 'x', specimen: 'serum' as const };

describe('lookup', () => {
  it('prefers sex-specific row', () => {
    const r = lookup(data, { ...q, ageYears: 30, sex: 'M' });
    expect(r.status === 'found' && r.interval.low).toBe(12);
  });
  it('falls back to any-sex row', () => {
    const r = lookup(data, { ...q, ageYears: 30, sex: 'F' });
    expect(r.status === 'found' && r.interval.low).toBe(10);
  });
  it('age boundary is lower-inclusive, upper-exclusive', () => {
    const r = lookup(data, { ...q, ageYears: 60, sex: 'F' });
    expect(r.status === 'found' && r.interval.high).toBe(30);
  });
  it('does not extrapolate to uncovered ages (pediatric -> CALIPER)', () => {
    expect(lookup(data, { ...q, ageYears: 5, sex: 'F' }).status).toBe('pediatric');
  });
  it('does not extrapolate to another specimen', () => {
    expect(lookup(data, { ...q, specimen: 'urine', ageYears: 30, sex: 'F' }).status).toBe('not-found');
  });
  it('rejects invalid age', () => {
    expect(lookup(data, { ...q, ageYears: -1, sex: 'F' }).status).toBe('not-found');
  });
});

describe('judge', () => {
  const iv = mk({});
  it('low/normal/high with inclusive bounds', () => {
    expect(judge(9.99, iv)).toBe('low');
    expect(judge(10, iv)).toBe('normal');
    expect(judge(20, iv)).toBe('normal');
    expect(judge(20.01, iv)).toBe('high');
  });
  it('one-sided interval', () => {
    expect(judge(-5, mk({ low: null, high: 5 }))).toBe('normal');
  });
});

describe('shipped dataset', () => {
  it('is empty until values are verified against RCPA Table 6', () => {
    expect(REFERENCE_INTERVALS).toHaveLength(0); // TODO(verify)
  });
});
