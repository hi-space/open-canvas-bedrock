# 시각화 도구

## 모든 그래프 다이어그램 생성

모든 그래프(메인 + 서브그래프)의 다이어그램을 한 번에 생성:

```bash
# 모든 그래프 생성
python3 generate_diagrams.py

# 특정 그래프만 생성
python3 generate_diagrams.py open_canvas
python3 generate_diagrams.py reflection web_search

# 사용 가능한 그래프 목록
# - open_canvas
# - reflection
# - web_search
# - summarizer
# - thread_title
```

이 명령은 다음을 생성합니다:
- **Mermaid 다이어그램**: `*_diagram.mmd` - LangGraph가 자동 생성한 Mermaid 코드
- **PNG 이미지**: `*_diagram.png` - 그래프 시각화 이미지
  - 먼저 `pygraphviz`를 시도하고, 없으면 `graphviz` dot 명령어를 사용합니다
  - graphviz 설치: `sudo apt-get install graphviz` (Linux) 또는 `brew install graphviz` (macOS)
- **ASCII 다이어그램** (선택사항): `grandalf` 패키지 설치 시 (`pip install grandalf`)

생성된 Mermaid 파일은 GitHub, GitLab, 또는 [Mermaid Live Editor](https://mermaid.live/)에서 바로 확인할 수 있습니다.

