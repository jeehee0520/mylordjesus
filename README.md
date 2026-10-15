# mylordjesus — 임상검사 단위 변환 · 참고구간

React + TypeScript + Vite 정적 사이트 (GitHub Pages).

**Pages URL: https://jeehee0520.github.io/mylordjesus/**

## 기능
- **변환 탭:** 분석물 검색(영문·한글·동의어) → 값/원본·대상 단위 → 결과 + "계산 근거"(방법·계수·수식·단계·가정·출처). 단위 스왑, 복사. 근거 없는 변환(예: mg/dL→U/L)은 이유와 함께 거부.
- **참고구간 탭:** 분석물+나이+성별+검체 → 공표 구간만 표시(외삽 없음), 값 입력 시 low/normal/high 판정.

## 엔진
- UCUM(`@lhncbc/ucum-lhc`)으로 단위 검증·차원 검사·스케일 변환.
- 질량↔물질량은 IUPAC 원자량으로 계산한 분자량, mEq는 이온 전하로 계산. 변환 계수를 표에서 복사하지 않는다.
- 특수 변환: HbA1c NGSP↔IFCC, uACR·uPCR mg/g↔mg/mmol, BUN(요소질소)↔요소, 중성지방(트리올레인 분자량 가정).

## 개발
```
npm ci
npm test       # Vitest
npm run build
```
배포: `main` 푸시 시 `.github/workflows/deploy.yml` 이 테스트·빌드 후 Pages에 배포(저장소 Settings → Pages → Source = GitHub Actions 필요).

## 데이터를 구하지 못한 부분과 이유 (TODO(verify))
이 앱을 만든 환경은 외부 사이트 접근이 정책으로 차단돼(DNS/프록시 403) 아래 1차 출처를 열람하지 못했다. 규칙에 따라 추측으로 채우지 않았다.

| 항목 | 상태 | 이유 |
|---|---|---|
| RCPA Harmonised Reference Intervals Table 6 | **데이터 비어 있음** (`src/data/referenceIntervals.ts`) | rcpa.edu.au 접근 불가. PMC/De Gruyter 2차 출처도 불가 |
| CALIPER 소아 구간 | 데이터 없음, 링크로 안내 | caliperproject.ca 접근 불가 (구간 자체가 앱에 없음) |
| HbA1c 마스터 방정식 계수(0.09148, 2.152) | 사용 중, **미검증** | ngsp.org 접근 불가. Hoelzel 2004 로 알려진 값을 기재 |
| KDIGO 2024 uACR/uPCR | 공식은 질량→물질량 계산, 문서 미대조 | kdigo.org 접근 불가. KDIGO의 반올림 경계(30 mg/g≈3 mg/mmol)와 계산값(3.39)이 다를 수 있음 |
| IUPAC 원자량 | 약식(conventional) 값 사용, **미대조** | ciaaw.org 접근 불가 |
| 교차검증(Labcorp, CMEinfo, NBME) | **테스트에서 대조하지 못함** (`it.todo`) | 세 문서 모두 접근 불가. 대신 계산 정합성(왕복, 알려진 대략값)만 테스트 |

모든 항목은 코드 주석/테스트에 `TODO(verify)` 로 표시했다.
