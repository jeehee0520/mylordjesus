import type { Flag, RefInterval, Sex, Specimen } from './types';

export const ADULT_MIN_AGE = 18;

export interface Query {
  analyteId: string;
  ageYears: number;
  sex: Sex;
  specimen: Specimen;
}

export type LookupResult =
  | { status: 'found'; interval: RefInterval }
  | { status: 'pediatric'; reason: string }
  | { status: 'not-found'; reason: string };

const specimenMatches = (row: Specimen, want: Specimen) =>
  row === want ||
  (row === 'serum-or-plasma' && (want === 'serum' || want === 'plasma')) ||
  (want === 'serum-or-plasma' && (row === 'serum' || row === 'plasma'));

/**
 * 공표된 구간만 반환한다. 나이 범위를 벗어나면 외삽하지 않고 not-found 를 돌려준다.
 * 성별 전용 행이 있으면 우선하고, 없으면 sex='any' 행을 쓴다.
 */
export function lookup(data: RefInterval[], q: Query): LookupResult {
  if (!Number.isFinite(q.ageYears) || q.ageYears < 0) {
    return { status: 'not-found', reason: '나이를 0 이상의 숫자로 입력하세요.' };
  }
  const rows = data.filter(
    (r) =>
      r.analyteId === q.analyteId &&
      specimenMatches(r.specimen, q.specimen) &&
      q.ageYears >= r.ageMinYears &&
      (r.ageMaxYears === null || q.ageYears < r.ageMaxYears),
  );
  const exact = rows.find((r) => r.sex === q.sex && q.sex !== 'any');
  const any = rows.find((r) => r.sex === 'any');
  const hit = exact ?? any;
  if (hit) return { status: 'found', interval: hit };

  if (q.ageYears < ADULT_MIN_AGE) {
    return {
      status: 'pediatric',
      reason: `${ADULT_MIN_AGE}세 미만은 이 앱에 공표된 구간이 없습니다. 소아는 CALIPER를 참조하세요(외삽하지 않음).`,
    };
  }
  const hasAnalyte = data.some((r) => r.analyteId === q.analyteId);
  return {
    status: 'not-found',
    reason: hasAnalyte
      ? '선택한 나이·성별·검체 조합에 공표된 구간이 데이터에 없습니다(외삽하지 않음).'
      : '이 분석물의 공표 구간이 데이터에 없습니다.',
  };
}

export function judge(value: number, iv: RefInterval): Flag {
  if (iv.low !== null && value < iv.low) return 'low';
  if (iv.high !== null && value > iv.high) return 'high';
  return 'normal';
}
