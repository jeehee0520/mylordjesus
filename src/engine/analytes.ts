import { hba1c, uacr, upcr } from './special';
import type { Analyte } from './types';

type Seed = Omit<Analyte, 'units' | 'defaultFrom' | 'defaultTo'> & { units?: string[]; from: string; to: string };

const MASS_MOLE = ['mg/dL', 'mmol/L', 'umol/L', 'g/L'];

function a(s: Seed): Analyte {
  const { from, to, units, ...rest } = s;
  return { ...rest, units: units ?? [from, to], defaultFrom: from, defaultTo: to };
}

const enzyme = (id: string, en: string, ko: string, syn: string[]) =>
  a({ id, nameEn: en, nameKo: ko, synonyms: syn, category: '효소', units: ['U/L', 'ukat/L', 'nkat/L'], from: 'U/L', to: 'ukat/L' });

export const ANALYTES: Analyte[] = [
  a({ id: 'glucose', nameEn: 'Glucose', nameKo: '포도당(혈당)', synonyms: ['blood sugar', 'FBS', 'glc', '혈당', '당'], category: '당·대사', formula: 'C6H12O6', from: 'mg/dL', to: 'mmol/L', units: ['mg/dL', 'mmol/L', 'g/L'] }),
  a({ id: 'creatinine', nameEn: 'Creatinine', nameKo: '크레아티닌', synonyms: ['Cr', 'creat', '크레아티닌'], category: '신장', formula: 'C4H7N3O', from: 'mg/dL', to: 'umol/L', units: ['mg/dL', 'umol/L', 'mmol/L'] }),
  a({ id: 'urea', nameEn: 'Urea', nameKo: '요소', synonyms: ['요소'], category: '신장', formula: 'CH4N2O', from: 'mg/dL', to: 'mmol/L', units: MASS_MOLE }),
  a({
    id: 'bun', nameEn: 'Blood urea nitrogen (BUN)', nameKo: '혈액요소질소(BUN)', synonyms: ['BUN', 'urea nitrogen', '요소질소'], category: '신장',
    formula: 'N2', from: 'mg/dL', to: 'mmol/L', units: ['mg/dL', 'mmol/L', 'umol/L'],
    assumption: 'BUN(mg/dL)은 요소 속 질소의 질량이다. 요소 1분자에 질소 2원자(N₂ = 28.014 g/mol)이므로 mmol/L는 "요소의 mmol/L"를 뜻한다. 요소 질량(mg/dL)으로 바꾸려면 "요소" 항목을 사용.',
  }),
  a({ id: 'uric-acid', nameEn: 'Uric acid', nameKo: '요산', synonyms: ['urate', 'UA', '요산'], category: '신장', formula: 'C5H4N4O3', from: 'mg/dL', to: 'umol/L', units: ['mg/dL', 'umol/L', 'mmol/L'] }),
  a({ id: 'cholesterol', nameEn: 'Cholesterol (total/HDL/LDL)', nameKo: '콜레스테롤(총/HDL/LDL)', synonyms: ['TC', 'HDL', 'LDL', 'chol', '총콜레스테롤'], category: '지질', formula: 'C27H46O', from: 'mg/dL', to: 'mmol/L', units: ['mg/dL', 'mmol/L', 'g/L'] }),
  a({
    id: 'triglycerides', nameEn: 'Triglycerides', nameKo: '중성지방', synonyms: ['TG', 'triacylglycerol', 'TAG', '트리글리세라이드'], category: '지질', formula: 'C57H104O6', from: 'mg/dL', to: 'mmol/L', units: ['mg/dL', 'mmol/L', 'g/L'],
    assumption: '중성지방은 지방산 조성이 다른 혼합물이라 단일 분자량이 없다. 관례적으로 트리올레인(C57H104O6)의 분자량을 대표값으로 가정한다. 이는 근사이다.',
  }),
  a({ id: 'bilirubin', nameEn: 'Bilirubin (total/direct)', nameKo: '빌리루빈', synonyms: ['T.bil', 'D.bil', 'TB', '총빌리루빈'], category: '간', formula: 'C33H36N4O6', from: 'mg/dL', to: 'umol/L', units: ['mg/dL', 'umol/L'] }),
  a({ id: 'lactate', nameEn: 'Lactate', nameKo: '젖산(락테이트)', synonyms: ['lactic acid', 'LA', '젖산'], category: '당·대사', formula: 'C3H6O3', from: 'mg/dL', to: 'mmol/L', units: MASS_MOLE }),
  a({ id: 'ammonia', nameEn: 'Ammonia', nameKo: '암모니아', synonyms: ['NH3', '암모니아'], category: '당·대사', formula: 'NH3', from: 'ug/dL', to: 'umol/L', units: ['ug/dL', 'umol/L', 'ug/L'] }),
  a({ id: 'sodium', nameEn: 'Sodium', nameKo: '나트륨', synonyms: ['Na', 'Na+', '소디움'], category: '전해질', formula: 'Na', charge: 1, from: 'mEq/L', to: 'mmol/L', units: ['mEq/L', 'mmol/L', 'mg/dL'] }),
  a({ id: 'potassium', nameEn: 'Potassium', nameKo: '칼륨', synonyms: ['K', 'K+', '포타슘'], category: '전해질', formula: 'K', charge: 1, from: 'mEq/L', to: 'mmol/L', units: ['mEq/L', 'mmol/L', 'mg/dL'] }),
  a({ id: 'chloride', nameEn: 'Chloride', nameKo: '염소', synonyms: ['Cl', 'Cl-', '클로라이드'], category: '전해질', formula: 'Cl', charge: 1, from: 'mEq/L', to: 'mmol/L', units: ['mEq/L', 'mmol/L', 'mg/dL'] }),
  a({ id: 'bicarbonate', nameEn: 'Bicarbonate (total CO2)', nameKo: '중탄산염(총 CO2)', synonyms: ['HCO3', 'tCO2', 'CO2', '중탄산'], category: '전해질', formula: 'CHO3', charge: 1, from: 'mEq/L', to: 'mmol/L', units: ['mEq/L', 'mmol/L'] }),
  a({ id: 'calcium', nameEn: 'Calcium (total)', nameKo: '칼슘(총)', synonyms: ['Ca', 'Ca2+', '칼슘'], category: '전해질', formula: 'Ca', charge: 2, from: 'mg/dL', to: 'mmol/L', units: ['mg/dL', 'mmol/L', 'mEq/L'], assumption: '총 칼슘 기준. 이온화 칼슘·알부민 보정은 다루지 않는다.' }),
  a({ id: 'magnesium', nameEn: 'Magnesium', nameKo: '마그네슘', synonyms: ['Mg', 'Mg2+', '마그네슘'], category: '전해질', formula: 'Mg', charge: 2, from: 'mg/dL', to: 'mmol/L', units: ['mg/dL', 'mmol/L', 'mEq/L'] }),
  a({ id: 'phosphate', nameEn: 'Phosphate (inorganic phosphorus)', nameKo: '인(무기인산)', synonyms: ['Phos', 'P', 'PO4', '인', '인산염'], category: '전해질', formula: 'P', from: 'mg/dL', to: 'mmol/L', units: ['mg/dL', 'mmol/L'], assumption: 'mg/dL는 인(P 원소)의 질량 기준이다. 인산염은 pH에 따라 전하가 달라 mEq 변환은 제공하지 않는다.' }),
  a({ id: 'iron', nameEn: 'Iron', nameKo: '철', synonyms: ['Fe', 'serum iron', '혈청철'], category: '미량원소', formula: 'Fe', from: 'ug/dL', to: 'umol/L', units: ['ug/dL', 'umol/L'] }),
  a({ id: 'zinc', nameEn: 'Zinc', nameKo: '아연', synonyms: ['Zn', '아연'], category: '미량원소', formula: 'Zn', from: 'ug/dL', to: 'umol/L', units: ['ug/dL', 'umol/L'] }),
  a({ id: 'copper', nameEn: 'Copper', nameKo: '구리', synonyms: ['Cu', '구리'], category: '미량원소', formula: 'Cu', from: 'ug/dL', to: 'umol/L', units: ['ug/dL', 'umol/L'] }),
  a({ id: 'hemoglobin', nameEn: 'Hemoglobin', nameKo: '헤모글로빈', synonyms: ['Hb', 'Hgb', '혈색소'], category: '혈액', from: 'g/dL', to: 'g/L', units: ['g/dL', 'g/L'] }),
  a({ id: 'albumin', nameEn: 'Albumin', nameKo: '알부민', synonyms: ['Alb', '알부민'], category: '단백', from: 'g/dL', to: 'g/L', units: ['g/dL', 'g/L'] }),
  a({ id: 'total-protein', nameEn: 'Total protein', nameKo: '총단백', synonyms: ['TP', '총단백질'], category: '단백', from: 'g/dL', to: 'g/L', units: ['g/dL', 'g/L'] }),
  enzyme('alt', 'ALT (alanine aminotransferase)', 'ALT(알라닌아미노전이효소)', ['GPT', 'SGPT']),
  enzyme('ast', 'AST (aspartate aminotransferase)', 'AST(아스파르테이트아미노전이효소)', ['GOT', 'SGOT']),
  enzyme('alp', 'Alkaline phosphatase (ALP)', '알칼리인산분해효소(ALP)', ['ALP', 'alk phos']),
  enzyme('ggt', 'GGT (gamma-glutamyl transferase)', '감마글루타밀전이효소(GGT)', ['GGT', 'gamma GT']),
  enzyme('ldh', 'Lactate dehydrogenase (LDH)', '젖산탈수소효소(LDH)', ['LDH', 'LD']),
  enzyme('ck', 'Creatine kinase (CK)', '크레아틴키나제(CK)', ['CPK', 'CK']),
  enzyme('amylase', 'Amylase', '아밀라제', ['AMY']),
  enzyme('lipase', 'Lipase', '리파제', ['LPS']),
  a({ id: 'hba1c', nameEn: 'HbA1c (NGSP ↔ IFCC)', nameKo: '당화혈색소(HbA1c)', synonyms: ['A1c', 'glycated hemoglobin', 'glycohemoglobin', '당화헤모글로빈'], category: '특수 변환', from: '%', to: 'mmol/mol', special: hba1c }),
  a({ id: 'uacr', nameEn: 'Urine albumin/creatinine ratio (uACR)', nameKo: '소변 알부민/크레아티닌 비(uACR)', synonyms: ['ACR', 'albuminuria', '알부민뇨', '미세알부민'], category: '특수 변환', from: 'mg/g', to: 'mg/mmol', special: uacr }),
  a({ id: 'upcr', nameEn: 'Urine protein/creatinine ratio (uPCR)', nameKo: '소변 단백/크레아티닌 비(uPCR)', synonyms: ['PCR', 'proteinuria', '단백뇨'], category: '특수 변환', from: 'mg/g', to: 'mg/mmol', special: upcr }),
];

export function searchAnalytes(q: string): Analyte[] {
  const s = q.trim().toLowerCase();
  if (!s) return ANALYTES;
  return ANALYTES.filter((x) =>
    [x.nameEn, x.nameKo, x.id, ...x.synonyms].some((t) => t.toLowerCase().includes(s)),
  );
}
