import { useState } from 'react';
import { CALIPER_URL, RCPA_URL, REFERENCE_INTERVALS } from '../data/referenceIntervals';
import { ANALYTES } from '../engine/analytes';
import type { Analyte } from '../engine/types';
import { judge, lookup } from '../reference/lookup';
import type { Sex, Specimen } from '../reference/types';
import AnalytePicker from './AnalytePicker';

const SPECIMENS: [Specimen, string][] = [
  ['serum', '혈청'],
  ['plasma', '혈장'],
  ['serum-or-plasma', '혈청 또는 혈장'],
  ['whole-blood', '전혈'],
  ['urine', '소변'],
];
const FLAG_LABEL = { low: '낮음 (low)', normal: '정상 (normal)', high: '높음 (high)' };

export default function ReferenceTab() {
  const [analyte, setAnalyte] = useState<Analyte>(ANALYTES[0]);
  const [age, setAge] = useState('40');
  const [sex, setSex] = useState<Sex>('F');
  const [specimen, setSpecimen] = useState<Specimen>('serum');
  const [val, setVal] = useState('');

  const res = lookup(REFERENCE_INTERVALS, { analyteId: analyte.id, ageYears: Number(age), sex, specimen });
  const v = Number(val);

  return (
    <section>
      <AnalytePicker value={analyte} onChange={setAnalyte} />
      <div className="row">
        <div className="field">
          <label htmlFor="age">나이 (세)</label>
          <input id="age" inputMode="decimal" value={age} onChange={(e) => setAge(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="sex">성별</label>
          <select id="sex" value={sex} onChange={(e) => setSex(e.target.value as Sex)}>
            <option value="F">여</option>
            <option value="M">남</option>
            <option value="any">구분 없음</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="sp">검체</label>
          <select id="sp" value={specimen} onChange={(e) => setSpecimen(e.target.value as Specimen)}>
            {SPECIMENS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
      </div>

      {res.status === 'found' ? (
        <div className="result">
          <div>
            공표 참고구간: <span className="big">
              {res.interval.low ?? '—'} – {res.interval.high ?? '—'}
            </span> <span className="unit">{res.interval.unit}</span>
          </div>
          <p className="muted">
            검체: {SPECIMENS.find(([k]) => k === res.interval.specimen)?.[1]} · 나이 구간: {res.interval.ageLabel} · 성별:{' '}
            {res.interval.sex === 'any' ? '구분 없음' : res.interval.sex === 'M' ? '남' : '여'} ·{' '}
            출처: <a href={res.interval.sourceUrl} target="_blank" rel="noreferrer">{res.interval.source}</a>
          </p>
          <div className="field">
            <label htmlFor="rv">결과 값 ({res.interval.unit})</label>
            <input id="rv" inputMode="decimal" value={val} onChange={(e) => setVal(e.target.value)} />
          </div>
          {val.trim() !== '' && Number.isFinite(v) && (
            <p className={`flag ${judge(v, res.interval)}`}>{FLAG_LABEL[judge(v, res.interval)]}</p>
          )}
        </div>
      ) : (
        <div className="reject" role="status">
          <strong>표시할 공표 구간이 없습니다</strong>
          <p>{res.reason}</p>
          <p>
            이 앱은 값을 추정·외삽하지 않습니다. 원 자료:{' '}
            <a href={RCPA_URL} target="_blank" rel="noreferrer">RCPA Harmonised Reference Intervals</a> ·{' '}
            소아: <a href={CALIPER_URL} target="_blank" rel="noreferrer">CALIPER</a>
          </p>
        </div>
      )}
      {REFERENCE_INTERVALS.length === 0 && (
        <p className="muted">
          현재 이 앱의 참고구간 데이터는 비어 있습니다. RCPA Table 6 원문을 확인하지 못해 임의로 채우지 않았습니다 (README 참조).
        </p>
      )}
    </section>
  );
}
