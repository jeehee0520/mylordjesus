import { useState } from 'react';
import ConvertTab from './components/ConvertTab';
import ReferenceTab from './components/ReferenceTab';

export default function App() {
  const [tab, setTab] = useState<'convert' | 'ref'>('convert');
  return (
    <main>
      <h1>임상검사 단위 변환 · 참고구간</h1>
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'convert'} onClick={() => setTab('convert')}>변환</button>
        <button role="tab" aria-selected={tab === 'ref'} onClick={() => setTab('ref')}>참고구간</button>
      </div>
      {tab === 'convert' ? <ConvertTab /> : <ReferenceTab />}
      <footer>
        교육·참고용입니다. 임상 판단은 각 검사실의 공식 참고구간과 단위를 따르세요.
      </footer>
    </main>
  );
}
