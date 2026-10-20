# 투고 양식 도우미 (Manuscript Assistant)

저널 투고 규정을 읽어 **Word 원고 템플릿**을 만들고, **Figure 해상도·형식**을 맞추고, 올린 원고의 **서식만** 규정에 맞게 바꾸고, **오타·오류 목록**에서 고른 항목만 Word 변경 내용 추적으로 고친 파일을 만드는 프로그램입니다.

🔒 **외부 API를 전혀 사용하지 않습니다.** 규정 분석, 맞춤법 검사, 문서 수정은 모두 프로그램이 돌아가는 컴퓨터(또는 기관 서버) 안에서 이루어집니다. Streamlit 사용 통계 전송도 꺼져 있습니다(`.streamlit/config.toml`).

## 설치 (Python 필요 없음)

[Releases](https://github.com/jeehee0520/mylordjesus/releases) 페이지에서 내 컴퓨터에 맞는 파일을 받으세요.

| 운영체제 | 파일 | 설치 · 실행 |
|---|---|---|
| Windows 10/11 | `ManuscriptAssistant-Setup-x.y.z.exe` | 실행해 설치하면 시작 메뉴(와 선택 시 바탕화면)에 **Manuscript Assistant**가 생깁니다. 관리자 권한이 필요 없습니다. 설치 없이 쓰려면 `windows-portable.zip`을 압축 해제한 뒤 `ManuscriptAssistant.exe` 실행 |
| macOS (Apple silicon) | `…-macos-arm64.dmg` | dmg를 열고 앱을 **응용 프로그램** 폴더로 끌어 놓은 뒤 실행 |
| Linux (x64) | `…-linux-x64.tar.gz` | 압축 해제 후 `ManuscriptAssistant/ManuscriptAssistant` 실행 |

프로그램을 실행하면 기본 브라우저에 앱 화면이 열립니다. 앱은 이 컴퓨터 안에서만(127.0.0.1) 동작하며 인터넷이 필요 없습니다.
끝낼 때는 앱 왼쪽의 **⏻ 프로그램 종료**를 누르세요 (Windows/Linux에서는 함께 뜨는 검은 창을 닫아도 됩니다).

### 처음 실행할 때 보안 경고가 나오면

이 프로그램은 코드 서명 인증서로 서명되어 있지 않아, 운영체제가 처음 한 번 경고를 보여줍니다.

- **Windows** "Windows의 PC 보호" 화면 → **추가 정보** → **실행**
- **macOS** "확인되지 않은 개발자" 또는 "손상되었기 때문에 열 수 없습니다" → 앱을 **Control+클릭 → 열기**, 또는 **시스템 설정 › 개인정보 보호 및 보안 › 그래도 열기**.
  그래도 열리지 않으면 터미널에서 `xattr -dr com.apple.quarantine "/Applications/ManuscriptAssistant.app"`
- 브라우저가 자동으로 열리지 않으면 검은 창(Windows/Linux)에 표시된 주소(예: `http://localhost:8501`)를 직접 입력하세요.
  macOS에서는 문제가 생기면 `~/.manuscript_assistant/app.log`에 기록이 남습니다.

> 미발표 원고를 다루므로 외부 호스팅(예: Streamlit Community Cloud)에 올리지 말고 개인 PC나 기관 내부 서버에서 실행하세요.
> 기관 서버에 올릴 때는 Docker를 쓸 수 있습니다: `docker build -t manuscript-assistant .` → `docker run -p 8501:8501 manuscript-assistant`

## 사용 순서

1. **① 투고 규정** — 규정 텍스트를 붙여넣거나 PDF·Word·TXT(·HTML) 파일을 올리고 '규정 분석'을 누릅니다.
   - 웹페이지는 브라우저에서 `Ctrl+P → PDF로 저장`(접힌 섹션은 모두 펼친 뒤)해서 올리는 것이 가장 정확합니다.
   - 추출된 규칙마다 **원문 인용과 페이지**가 표시됩니다. 🟢 규정 근거 / 🟡 규정에 없어 기본값 / ⚪ 적용 안 함 / 🔵 사용자 지정.
   - 값을 확인·수정한 뒤 **확정**해야 다음 단계가 열립니다. 프로필(.json)로 저장해 두면 다음에 다시 쓸 수 있습니다.
   - **붙여넣은 규정은 자동 저장**됩니다(이 컴퓨터의 `~/.manuscript_assistant/guidelines`, 외부로 전송되지 않음). 확정한 값도 함께 저장되므로, 다음에는 맨 위 **💾 저장된 투고 규정**에서 고르고 '불러오기'만 누르면 됩니다. 같은 텍스트는 한 번만 저장되고, 필요 없으면 '삭제'로 지웁니다.
2. **② 원고 템플릿** — 서식(용지·여백·글꼴·줄 간격·줄 번호·페이지 번호)과 섹션 순서, 안내 문구를 갖춘 `.docx`와 투고 체크리스트를 받습니다.
3. **③ Figure 변환** — 그림 파일을 올리거나 원고에 삽입된 그림을 추출해, 그림 종류(사진/혼합/선화)별 dpi와 인쇄 폭(1단/2단)에 맞춰 PNG·PDF로 변환합니다. 결과 파일을 다시 열어 잰 픽셀·dpi·mm를 보여줍니다.
   - **PowerPoint(.pptx)**: 슬라이드 하나가 그림 하나가 됩니다(`파일명_slide3.png/pdf`). 변환할 슬라이드를 고를 수 있고(예: `1, 3-5`), 슬라이드의 흰 여백을 자동으로 잘라 그림 부분만 남깁니다. PDF 출력은 벡터로 유지됩니다.
   - 슬라이드 변환에는 이 컴퓨터의 **Microsoft PowerPoint(Windows)** 또는 **LibreOffice**를 씁니다. 둘 다 없으면 PowerPoint에서 `파일 › 다른 이름으로 저장 › PDF`로 저장한 PDF를 올리면 같은 결과를 얻습니다.
   - 슬라이드 안의 사진(또는 내보내기 과정에서 비트맵이 된 도형)이 목표 해상도보다 낮으면, 최종 크기에서의 실제 dpi와 함께 경고합니다.
4. **④ 원고 서식 변환** — 원고(.docx)의 서식만 바꿉니다. 변환 후 원본과 내용을 자동 비교하고, 하나라도 다르면 파일을 만들지 않습니다. 글자를 바꿔야 하는 규정(초록 길이, 키워드 수, 섹션 제목, 인용 형식 등)은 **준수 점검 보고서**로 보여줍니다.
   - **표 각주 기호**: 규정의 기호와 순서(예: 일반 각주 † ‡ § ¶, P값 * ** ***)에 맞게 바꿉니다. 각주 문장에 P value가 언급되면 P값 각주로 보고, 기호는 표 안에 처음 나오는 순서대로 붙입니다. 표 아래에 정의된 각주 표시만 바꾸며(예: `kg/m²`의 ²는 그대로), 결과는 **변경 내용 추적**으로 들어가 Word에서 하나씩 확인할 수 있습니다.
5. **⑤ 오타·오류 점검** — 목록에서 '적용'을 체크하고 수정안을 필요하면 고친 뒤 '수정 파일 만들기'를 누르면, 변경 내용 추적본과 반영본 두 파일이 만들어집니다.

## 정확성을 위한 장치

- **규칙을 지어내지 않음**: 규정 분석은 규칙 기반(정규식)이며, 명시된 문구가 있을 때만 '규정 근거'로 표시합니다. 근거 문장과 위치를 항상 함께 보여줍니다.
- **내용 불변 검증** (`core/content_guard.py`): 본문·각주·미주·메모·머리글/바닥글의 텍스트, 기존 변경 추적(작성자·날짜 포함), 필드 코드(EndNote/Zotero), 그림(해시), 하이퍼링크, 표 구조를 순서대로 비교합니다.
- **오타 수정 이중 검증** (`core/track_changes.py`): ① 도구의 변경을 모두 거부하면 원본과 완전히 같아야 하고, ② 모두 수락하면 승인한 항목만 바뀌어야 합니다. 둘 중 하나라도 실패하면 파일을 주지 않습니다.
- **보호 영역**: EndNote 인용 결과, 하이퍼링크, 탭, 그림이 걸친 범위는 자동 수정하지 않고 '확인 필요'로 남깁니다.
- **해상도에 대한 정직한 안내**: 업스케일로는 세부가 생기지 않는다는 경고를 보여주고, 2배를 넘는 업스케일은 사용자가 허용해야만 진행합니다.

## 오타·오류 점검 범위

| 범주 | 내용 | 자동 수정 |
|---|---|---|
| 띄어쓰기·문장부호 | 이중 공백, 문장부호 앞 공백, 쉼표/마침표/쌍점 뒤 공백 누락, 반복 문장부호 | ○ |
| 반복 | "the the" | ○ |
| 철자 | 오프라인 영어 사전 + 의학 용어 목록 + 원고 자체 어휘 + 사용자 사전 | ○ (추천이 있을 때) |
| 저널 철자 규칙 | 영국식/미국식 (예: randomized → randomised); 고유명사는 제외 | ○ |
| 표기 일관성 | LC-MS/MS ↔ LC–MS/MS, Bland-Altman ↔ Bland–Altman | ○ |
| 인용 | 남아 있는 임시 인용(PMID), 번호 순서, 목록에 없는 번호, 인용되지 않은 참고문헌 | 일부 |
| 그림·표 번호 | 언급 순서, 범례/제목 누락, 본문에서 언급되지 않은 그림·표 | 보고만 |
| 약어 | 정의 없이 사용, 정의보다 먼저 사용 | 보고만 |
| 표 각주 기호 | 규정의 각주 기호·순서(예: † ‡ § ¶)와 P값 전용 기호(예: * ** ***). ④ 탭과 같은 기준이며 기본 선택됨 | ○ |
| 문법 (선택) | 같은 컴퓨터/기관 내부의 LanguageTool 서버가 있을 때만 (`LT_ALLOWED_HOSTS`로 허용 호스트 지정) | ○ |

문법·문맥 오류는 오프라인 사전만으로는 한계가 있습니다. 더 넓게 점검하려면 LanguageTool을 기관 내부에 설치하세요 (`docker run -p 8081:8010 erikvl87/languagetool` 후 `http://localhost:8081` 입력).

## 개발

```
pip install -r requirements.txt pytest reportlab
python desktop.py            # 소스에서 실행 (브라우저 자동 열림)
pytest                       # 합성 문서로 하는 테스트
MA_GUIDELINE=규정.pdf MA_MANUSCRIPT=원고.docx pytest tests/test_real_files.py   # 내 파일로 검증
```

### 설치 파일 만들기 (배포)

설치 파일은 GitHub Actions(`.github/workflows/manuscript-assistant.yml`)가 Windows·macOS·Linux에서 PyInstaller로 만듭니다.
각 운영체제에서 만든 프로그램을 `--selftest`로 실제로 실행해 모든 기능(규정 분석·템플릿·서식 변환·오류 점검·Figure·웹 화면)이 동작하는지 확인한 뒤에만 파일을 올립니다.

- 코드를 푸시하면 Actions 실행 결과의 **Artifacts**에서 설치 파일을 받을 수 있습니다.
- **Releases**에 공개하는 방법 (둘 중 하나):
  - `VERSION` 파일의 버전을 올리고, 커밋 메시지에 `[release]`를 넣어 푸시 → 빌드·자가 점검이 모두 통과하면 `ma-v<버전>` 태그와 Release가 자동으로 만들어집니다.
  - 또는 `ma-v1.2.3` 같은 태그를 직접 푸시: `git tag ma-v1.2.3 && git push origin ma-v1.2.3`
- 직접 만들려면: `pyinstaller --noconfirm --distpath packaging/dist --workpath packaging/build packaging/ManuscriptAssistant.spec`
  (Windows 설치 프로그램은 그 뒤 Inno Setup으로 `iscc packaging\windows\installer.iss`)

| 파일 | 역할 |
|---|---|
| `desktop.py` | 데스크톱 실행 진입점 (빈 포트 선택, 브라우저 열기, `--selftest`) |
| `app.py` | 화면 (Streamlit) |
| `packaging/` | PyInstaller 설정, Windows 설치 프로그램 스크립트 |
| `core/guideline_loader.py` | 규정 텍스트/PDF/DOCX/TXT/HTML 읽기 (페이지 위치 보존) |
| `core/profile_extractor.py`, `core/profile.py` | 규칙 추출과 Journal Profile |
| `core/template_builder.py` | Word 템플릿·체크리스트 |
| `core/figure_processor.py` | Figure 변환·측정 |
| `core/manuscript_formatter.py` | 서식 변환·규정 준수 점검 |
| `core/content_guard.py` | 내용 불변 검증 |
| `core/proofreader.py`, `core/track_changes.py` | 오류 점검, 변경 내용 추적 수정 |
| `core/table_footnotes.py` | 표 각주 기호를 규정의 기호·순서로 바꾸는 계획 |
| `core/storage.py` | 붙여넣은 규정과 확정한 프로필의 로컬 저장 |
| `data/medical_words.txt` | 맞춤법 검사기에 추가하는 의학 용어 |

원고나 규정 파일(.docx, .pdf)은 git에 올라가지 않도록 `.gitignore`에 등록되어 있습니다.
