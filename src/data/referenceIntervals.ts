import type { RefInterval } from '../reference/types';

/**
 * 공표된 참고구간 데이터.
 *
 * 기본 출처: RCPA Harmonised Reference Intervals (Table 6), rcpa.edu.au.
 * TODO(verify): 이 개발 환경에서 rcpa.edu.au(및 PubMed/PMC 등 2차 출처)에 접속할 수 없어
 * 표의 값을 확인하지 못했다. 규칙(데이터가 없으면 채우지 않는다)에 따라 비워 둔다.
 * 값을 추가하려면 RefInterval 형식으로 표의 숫자·연령 구간·검체를 그대로 옮길 것.
 */
export const REFERENCE_INTERVALS: RefInterval[] = [];

export const RCPA_URL = 'https://www.rcpa.edu.au/Manuals/RCPA-Manual/Pathology-Tests/Harmonised-Reference-Intervals';
export const CALIPER_URL = 'https://caliperproject.ca';
