import { UcumLhcUtils } from '@lhncbc/ucum-lhc';

const utils = UcumLhcUtils.getInstance();

export function validateUnit(unit: string): { ok: boolean; msg: string } {
  if (!unit.trim()) return { ok: false, msg: '단위가 비어 있음' };
  const r = utils.validateUnitString(unit.trim());
  return r.status === 'valid'
    ? { ok: true, msg: '' }
    : { ok: false, msg: (r.msg ?? []).join(' ') || `UCUM에서 인식할 수 없는 단위: ${unit}` };
}

/** UCUM 스케일 변환. 차원이 다르면 null. */
export function ucumConvert(from: string, value: number, to: string): number | null {
  const r = utils.convertUnitTo(from.trim(), value, to.trim());
  return r.status === 'succeeded' && r.toVal !== null ? r.toVal : null;
}

export type UnitKind = 'mass' | 'substance' | 'equiv' | 'catalytic' | 'other';

/** 농도 단위의 종류를 UCUM 차원 검사로 판정한다. */
export function unitKind(unit: string): UnitKind {
  if (/eq/i.test(unit) && ucumConvert(unit, 1, 'eq/L') !== null) return 'equiv';
  if (ucumConvert(unit, 1, 'g/L') !== null) return 'mass';
  if (ucumConvert(unit, 1, 'mol/L') !== null) return 'substance';
  if (ucumConvert(unit, 1, 'ukat/L') !== null) return 'catalytic';
  return 'other';
}
