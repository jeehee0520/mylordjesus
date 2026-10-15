import { useState } from 'react';
import { searchAnalytes } from '../engine/analytes';
import type { Analyte } from '../engine/types';

interface Props {
  value: Analyte;
  onChange: (a: Analyte) => void;
}

export default function AnalytePicker({ value, onChange }: Props) {
  const [q, setQ] = useState('');
  const list = searchAnalytes(q);
  return (
    <div className="field">
      <label htmlFor="q">분석물 검색 (영문·한글·동의어)</label>
      <input id="q" value={q} placeholder="예: glucose, 혈당, GPT, A1c" onChange={(e) => setQ(e.target.value)} />
      <select
        aria-label="분석물"
        size={Math.min(6, Math.max(2, list.length))}
        value={list.some((a) => a.id === value.id) ? value.id : ''}
        onChange={(e) => {
          const a = list.find((x) => x.id === e.target.value);
          if (a) onChange(a);
        }}
      >
        {list.map((a) => (
          <option key={a.id} value={a.id}>{a.nameKo} — {a.nameEn}</option>
        ))}
      </select>
      {list.length === 0 && <p className="muted">검색 결과가 없습니다.</p>}
    </div>
  );
}
