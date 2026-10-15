import { useMemo, useState } from 'react';
import { ANALYTES } from '../engine/analytes';
import { convert } from '../engine/convert';
import { fmt } from '../engine/format';
import type { Analyte } from '../engine/types';
import AnalytePicker from './AnalytePicker';

export default function ConvertTab() {
  const [analyte, setAnalyte] = useState<Analyte>(ANALYTES[0]);
  const [input, setInput] = useState('100');
  const [from, setFrom] = useState(analyte.defaultFrom);
  const [to, setTo] = useState(analyte.defaultTo);
  const [copied, setCopied] = useState(false);

  const pick = (a: Analyte) => {
    setAnalyte(a);
    setFrom(a.defaultFrom);
    setTo(a.defaultTo);
  };

  const value = Number(input);
  const result = useMemo(
    () => (input.trim() === '' || !Number.isFinite(value) ? null : convert(analyte, value, from, to)),
    [analyte, input, value, from, to],
  );

  const text = result && result.ok ? `${fmt(result.value, 5)} ${to}` : '';
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* 클립보드 권한이 없으면 무시 */
    }
  };
  const swap = () => {
    if (result && result.ok) setInput(String(Number(result.value.toPrecision(8))));
    setFrom(to);
    setTo(from);
  };

  return (
    <section>
      <AnalytePicker value={analyte} onChange={pick} />
      <div className="row">
        <div className="field">
          <label htmlFor="val">값</label>
          <input id="val" inputMode="decimal" value={input} onChange={(e) => setInput(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="from">원본 단위</label>
          <input id="from" list="units" value={from} onChange={(e) => setFrom(e.target.value)} />
        </div>
        <button className="swap" onClick={swap} aria-label="단위 맞바꾸기">⇄</button>
        <div className="field">
          <label htmlFor="to">대상 단위</label>
          <input id="to" list="units" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        <datalist id="units">{analyte.units.map((u) => <option key={u} value={u} />)}</datalist>
      </div>

      {result === null && <p className="muted">값을 입력하세요.</p>}
      {result && !result.ok && (
        <div className="reject" role="alert">
          <strong>변환할 수 없음</strong>
          <p>{result.reason}</p>
        </div>
      )}
      {result && result.ok && (
        <>
          <div className="result" aria-live="polite">
            <span className="big">{fmt(result.value, 5)}</span> <span className="unit">{to}</span>
            <button onClick={copy}>{copied ? '복사됨' : '복사'}</button>
          </div>
          <details open className="basis">
            <summary>계산 근거</summary>
            <dl>
              <dt>방법</dt><dd>{result.basis.method}</dd>
              <dt>계수</dt>
              <dd>{result.basis.coefficient === null ? '선형 계수 없음 (회귀식)' : `1 ${from} = ${fmt(result.basis.coefficient, 6)} ${to}`}</dd>
              <dt>수식</dt><dd><code>{result.basis.formula}</code></dd>
              <dt>단계</dt><dd><ol>{result.basis.steps.map((s, i) => <li key={i}>{s}</li>)}</ol></dd>
              <dt>가정</dt>
              <dd>{result.basis.assumptions.length ? <ul>{result.basis.assumptions.map((s, i) => <li key={i}>{s}</li>)}</ul> : '없음'}</dd>
              <dt>출처</dt>
              <dd><ul>{result.basis.sources.map((s) => <li key={s.url}><a href={s.url} target="_blank" rel="noreferrer">{s.label}</a></li>)}</ul></dd>
            </dl>
          </details>
        </>
      )}
    </section>
  );
}
