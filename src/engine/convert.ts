import { molarMass, molarMassBreakdown } from './atomic';
import { fmt } from './format';
import { unitKind, ucumConvert, validateUnit } from './ucum';
import type { Analyte, Basis, ConvResult, Source } from './types';

const UCUM: Source = { label: 'UCUM (Unified Code for Units of Measure)', url: 'https://ucum.org/ucum' };
const IUPAC: Source = { label: 'IUPAC/CIAAW 표준 원자량', url: 'https://ciaaw.org/atomic-weights.htm' };

// 표시용 표기(mEq, µ)를 UCUM 대소문자 코드(meq, u)로 맞춘다.
const norm = (u: string) =>
  u.trim().replace(/\s+/g, '').replace(/[µμ]/g, 'u').replace(/Eq/g, 'eq');
const same = (a: string, b: string) => norm(a).toLowerCase() === norm(b).toLowerCase();

const reject = (reason: string): ConvResult => ({ ok: false, reason });

export function convert(analyte: Analyte, value: number, fromRaw: string, toRaw: string): ConvResult {
  const from = norm(fromRaw);
  const to = norm(toRaw);
  if (!Number.isFinite(value)) return reject('값이 숫자가 아님');

  // --- 특수(공식 명시) 변환 -------------------------------------------------
  const sp = analyte.special;
  if (sp) {
    const fwd = same(from, sp.from) && same(to, sp.to);
    const rev = same(from, sp.to) && same(to, sp.from);
    if (same(from, to)) return { ok: true, value, basis: identityBasis(from) };
    if (!fwd && !rev) {
      return reject(`${analyte.nameKo}은(는) ${sp.from} ↔ ${sp.to} 사이의 공식 변환만 근거가 있습니다.`);
    }
    const y = fwd ? sp.forward(value) : sp.inverse(value);
    const basis: Basis = {
      method: sp.method,
      coefficient: sp.coefficient ? (fwd ? sp.coefficient() : 1 / sp.coefficient()) : null,
      formula: fwd ? sp.formula : sp.inverseFormula,
      steps: [`입력 ${fmt(value)} ${from} → ${fmt(y)} ${to}`],
      assumptions: sp.assumptions,
      sources: sp.sources,
    };
    return { ok: true, value: y, basis };
  }

  // --- 표준 변환: UCUM 차원 검사 + (필요 시) 분자량·전하 -------------------
  for (const u of [from, to]) {
    const v = validateUnit(u);
    if (!v.ok) return reject(`단위 "${u}" 오류: ${v.msg}`);
  }
  const kf = unitKind(from);
  const kt = unitKind(to);
  if (kf === 'other' || kt === 'other') {
    return reject('농도 단위(질량/물질량/당량/효소활성 per volume)가 아니어서 변환 근거가 없습니다.');
  }
  if (kf === 'catalytic' || kt === 'catalytic') {
    if (kf !== kt) {
      return reject(
        `효소 활성(U/L, µkat/L)은 질량·물질량 농도와 차원이 달라 변환할 수 없습니다. ` +
          `활성 단위는 분석 방법·기질·온도에 의존하며 분자량으로 환산되지 않습니다. (${from} → ${to})`,
      );
    }
  }

  // 같은 종류 → UCUM 스케일만 (당량 제외하고도 동일 종류면 스케일로 충분)
  if (kf === kt) {
    const y = ucumConvert(from, value, to);
    if (y === null) return reject(`UCUM 차원 불일치: ${from} → ${to}`);
    const k = ucumConvert(from, 1, to);
    return {
      ok: true,
      value: y,
      basis: {
        method: 'UCUM 차원 검사 + 스케일 변환',
        coefficient: k,
        formula: `${to} = ${from} × ${fmt(k ?? NaN, 6)}`,
        steps: [`UCUM: 1 ${from} = ${fmt(k ?? NaN, 6)} ${to}`],
        assumptions: ['동일 차원 단위 간 변환이므로 분자량 가정이 필요 없음.'],
        sources: [UCUM],
      },
    };
  }

  // 서로 다른 종류: 분석물 정보 필요
  const needMW = kf === 'mass' || kt === 'mass';
  const needZ = kf === 'equiv' || kt === 'equiv';
  if (needMW && !analyte.formula) {
    return reject(
      `${analyte.nameKo}: 분자량(화학식) 근거가 없어 질량 ↔ 물질량/당량 변환을 할 수 없습니다. ` +
        `(예: 단백질·혼합물은 단일 분자량이 없음)`,
    );
  }
  if (needZ && !analyte.charge) {
    return reject(`${analyte.nameKo}: 이온 전하 근거가 없어 mEq 변환을 할 수 없습니다. mmol/L 단위를 사용하세요.`);
  }

  const mw = analyte.formula ? molarMass(analyte.formula) : NaN;
  const z = analyte.charge ?? 1;
  const steps: string[] = [];
  let mol: number;
  if (kf === 'mass') {
    const g = ucumConvert(from, value, 'g/L')!;
    steps.push(`UCUM: ${fmt(value)} ${from} = ${fmt(g)} g/L`);
    mol = g / mw;
    steps.push(`÷ MW ${fmt(mw, 5)} g/mol → ${fmt(mol)} mol/L`);
  } else if (kf === 'equiv') {
    const eq = ucumConvert(from, value, 'eq/L')!;
    steps.push(`UCUM: ${fmt(value)} ${from} = ${fmt(eq)} eq/L`);
    mol = eq / z;
    steps.push(`÷ 전하 ${z} → ${fmt(mol)} mol/L`);
  } else {
    mol = ucumConvert(from, value, 'mol/L')!;
    steps.push(`UCUM: ${fmt(value)} ${from} = ${fmt(mol)} mol/L`);
  }
  let y: number;
  if (kt === 'mass') {
    const g = mol * mw;
    steps.push(`× MW ${fmt(mw, 5)} g/mol → ${fmt(g)} g/L`);
    y = ucumConvert('g/L', g, to)!;
  } else if (kt === 'equiv') {
    const eq = mol * z;
    steps.push(`× 전하 ${z} → ${fmt(eq)} eq/L`);
    y = ucumConvert('eq/L', eq, to)!;
  } else {
    y = ucumConvert('mol/L', mol, to)!;
  }
  steps.push(`UCUM: → ${fmt(y)} ${to}`);

  const coefficient = value !== 0 ? y / value : (convert(analyte, 1, from, to) as { value: number }).value;
  const formulaParts: string[] = [];
  if (needMW) formulaParts.push(kf === 'mass' ? 'mol = mass ÷ MW' : 'mass = mol × MW');
  if (needZ) formulaParts.push(kf === 'equiv' ? 'mol = eq ÷ z' : 'eq = mol × z');
  const assumptions: string[] = [];
  if (needMW && analyte.formula) assumptions.push(`분자량: ${molarMassBreakdown(analyte.formula)}`);
  if (needZ) assumptions.push(`이온 전하 |z| = ${z} (mEq = mmol × ${z})`);
  if (analyte.assumption) assumptions.push(analyte.assumption);
  const basis: Basis = {
    method: 'UCUM 스케일 변환 + 분자량/전하 (계산값, 표 복사 아님)',
    coefficient,
    formula: formulaParts.join('; '),
    steps,
    assumptions,
    sources: needMW ? [UCUM, IUPAC] : [UCUM],
  };
  return { ok: true, value: y, basis };
}

function identityBasis(unit: string): Basis {
  return {
    method: '동일 단위',
    coefficient: 1,
    formula: 'y = x',
    steps: [`${unit} → ${unit}`],
    assumptions: [],
    sources: [UCUM],
  };
}
