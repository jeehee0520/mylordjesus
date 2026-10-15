import { molarMass, molarMassBreakdown } from './atomic';
import type { SpecialConversion, Source } from './types';

const NGSP: Source = { label: 'NGSP – IFCC standardization (ngsp.org/ifcc.asp)', url: 'https://www.ngsp.org/ifcc.asp' };
const KDIGO: Source = {
  label: 'KDIGO 2024 CKD Guideline (kdigo.org)',
  url: 'https://kdigo.org/guidelines/ckd-evaluation-and-management/',
};

// HbA1c 마스터 방정식 (Hoelzel W et al., Clin Chem 2004;50:166-174; NGSP 게시)
// TODO(verify): ngsp.org 접속 불가로 계수를 해당 페이지와 직접 대조하지 못했다.
export const HBA1C_SLOPE = 0.09148;
export const HBA1C_INTERCEPT = 2.152;

export const hba1c: SpecialConversion = {
  from: '%',
  to: 'mmol/mol',
  forward: (ngsp) => (ngsp - HBA1C_INTERCEPT) / HBA1C_SLOPE,
  inverse: (ifcc) => HBA1C_SLOPE * ifcc + HBA1C_INTERCEPT,
  method: 'HbA1c 마스터 방정식 (NGSP↔IFCC, 선형 회귀식)',
  formula: `IFCC(mmol/mol) = (NGSP(%) − ${HBA1C_INTERCEPT}) / ${HBA1C_SLOPE}`,
  inverseFormula: `NGSP(%) = ${HBA1C_SLOPE} × IFCC(mmol/mol) + ${HBA1C_INTERCEPT}`,
  assumptions: ['단순 단위 환산이 아니라 두 표준화 체계 간 회귀식이다(절편 존재).', '값의 비율이 아니므로 계수 하나로 표현할 수 없다.'],
  sources: [NGSP],
};

const crMW = () => molarMass('C4H7N3O');
const crAssume = () => [
  `크레아티닌 분자량은 IUPAC 원자량으로 계산: ${molarMassBreakdown('C4H7N3O')}`,
  'KDIGO 표는 mg/mmol 경계를 반올림(예: 30 mg/g ≈ 3 mg/mmol)해 제시하며, 여기 값은 정확 계산값이라 약간 다를 수 있다.',
];

function ratio(id: 'uacr' | 'upcr'): SpecialConversion {
  const name = id === 'uacr' ? '알부민' : '단백질';
  return {
    from: 'mg/g',
    to: 'mg/mmol',
    forward: (x) => (x * crMW()) / 1000,
    inverse: (y) => (y * 1000) / crMW(),
    coefficient: () => crMW() / 1000,
    method: `뇨 ${name}/크레아티닌 비: 분모 크레아티닌의 질량→물질량 환산`,
    formula: `mg/mmol = mg/g × MW(크레아티닌) / 1000`,
    inverseFormula: `mg/g = mg/mmol × 1000 / MW(크레아티닌)`,
    assumptions: crAssume(),
    sources: [KDIGO],
  };
}
export const uacr = ratio('uacr');
export const upcr = ratio('upcr');
