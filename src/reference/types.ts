export type Sex = 'M' | 'F' | 'any';
export type Specimen = 'serum' | 'plasma' | 'whole-blood' | 'urine' | 'serum-or-plasma';

export interface RefInterval {
  analyteId: string;
  specimen: Specimen;
  sex: Sex;
  /** 포함 하한(세). 연령 구간을 표에 명시된 그대로 옮긴다. */
  ageMinYears: number;
  /** 미포함 상한(세). null 이면 상한 없음. */
  ageMaxYears: number | null;
  /** 한쪽만 공표된 구간이면 null */
  low: number | null;
  high: number | null;
  unit: string;
  /** 표의 연령 표기 원문 */
  ageLabel: string;
  source: string;
  sourceUrl: string;
}

export type Flag = 'low' | 'normal' | 'high';
