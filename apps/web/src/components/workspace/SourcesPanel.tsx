import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUpRight,
  BookOpen,
  Link2,
  LoaderCircle,
  Plus,
  Quote,
  Trash2,
  X,
} from "lucide-react";
import {
  extractReferences,
  mergeReferences,
  referenceUrl,
} from "../../lib/workspace/sources";
import type {
  SourceReference,
  TextSelection,
  WorkspaceDocument,
} from "../../lib/workspace/types";
import styles from "./workspace.module.css";

export function SourcesPanel({
  document,
  hasSelection,
  onAdd,
  onCite,
  onRemove,
  selection,
  html = false,
  projectSources = false,
  onRead,
}: {
  document: WorkspaceDocument;
  hasSelection: boolean;
  onAdd: (source: SourceReference) => void;
  onCite: (source: SourceReference) => void;
  onRemove: (id: string) => void;
  selection?: TextSelection;
  html?: boolean;
  projectSources?: boolean;
  onRead?: (id: string) => Promise<SourceReference>;
}) {
  const [showForm, setShowForm] = useState(false);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [excerpt, setExcerpt] = useState("");
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | undefined>(undefined);
  const urlRef = useRef(url);
  const alive = useRef(true);
  const [sourceQuery, setSourceQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(20);
  const [bodies, setBodies] = useState<Record<string, SourceReference>>({});
  const [opened, setOpened] = useState<Record<string, boolean>>({});
  const [reading, setReading] = useState<Record<string, boolean>>({});
  const [readErrors, setReadErrors] = useState<Record<string, string>>({});
  const references = useMemo(
    () => mergeReferences(document.content, document.sources),
    [document.content, document.sources]
  );
  const cited = useMemo(
    () => extractReferences(document.content),
    [document.content]
  );
  const selectedSources = useMemo(() => {
    const urls = new Set(
      selection
        ? extractReferences(selection.text).map((source) => source.url)
        : []
    );
    for (const source of document.sources) {
      if (selection?.sourceIds?.includes(source.id)) urls.add(source.url);
    }
    return urls;
  }, [document.sources, selection]);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      controller.current?.abort();
    };
  }, []);

  const filtered = projectSources
    ? references.filter((source) =>
        `${source.title} ${source.url}`
          .toLocaleLowerCase()
          .includes(sourceQuery.trim().toLocaleLowerCase())
      )
    : references;
  const shown = projectSources ? filtered.slice(0, visibleCount) : filtered;

  const openExcerpt = async (source: SourceReference) => {
    const key = `${source.id}/${source.version ?? ""}`;
    if (opened[key]) {
      setOpened((current) => ({ ...current, [key]: false }));
      return;
    }
    if (bodies[key] || source.excerpt) {
      setOpened((current) => ({ ...current, [key]: true }));
      return;
    }
    if (!onRead) return;
    setReading((current) => ({ ...current, [key]: true }));
    setReadErrors((current) => ({ ...current, [key]: "" }));
    try {
      const body = await onRead(source.id);
      if (body.id !== source.id)
        throw new Error("요청한 출처와 응답이 다릅니다. 다시 읽어 주세요.");
      if (source.version && body.version && source.version !== body.version)
        throw new Error(
          "출처가 변경되었습니다. 최신 목록에서 다시 읽어 주세요."
        );
      if (alive.current) {
        setBodies((current) => ({ ...current, [key]: body }));
        setOpened((current) => ({ ...current, [key]: true }));
      }
    } catch (error) {
      if (alive.current)
        setReadErrors((current) => ({
          ...current,
          [key]:
            error instanceof Error
              ? error.message
              : "발췌문을 읽지 못했습니다.",
        }));
    } finally {
      if (alive.current)
        setReading((current) => ({ ...current, [key]: false }));
    }
  };

  const fetchSource = async (): Promise<
    { title: string; excerpt: string } | undefined
  > => {
    const safeUrl = referenceUrl(url);
    if (!safeUrl) {
      setError("http 또는 https로 시작하는 링크를 입력해 주세요.");
      return;
    }
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setFetching(true);
    setError("");
    const timeout = setTimeout(() => request.abort(), 30000);
    try {
      const response = await fetch("/api/firecrawl/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls: [safeUrl] }),
        signal: request.signal,
      });
      const data = (await response.json()) as {
        success?: boolean;
        documents?: {
          data?: string;
          name?: string;
          metadata?: { title?: string };
        }[];
      };
      const result = data.documents?.[0];
      if (
        !response.ok ||
        !data.success ||
        typeof result?.data !== "string" ||
        !result.data.trim()
      ) {
        throw new Error("링크를 읽지 못했습니다.");
      }
      const retrieved = {
        title:
          result.metadata?.title || result.name || new URL(safeUrl).hostname,
        excerpt: result.data.slice(0, 20000),
      };
      if (
        controller.current !== request ||
        referenceUrl(urlRef.current) !== safeUrl
      )
        return;
      setTitle(retrieved.title);
      setExcerpt(retrieved.excerpt);
      return retrieved;
    } catch {
      if (request.signal.aborted && controller.current !== request) return;
      setError(
        "참고 글을 불러오지 못했습니다. 제목과 필요한 발췌를 직접 입력해도 출처를 추가할 수 있습니다."
      );
    } finally {
      clearTimeout(timeout);
      if (controller.current === request) {
        controller.current = undefined;
        setFetching(false);
      }
    }
  };

  const add = async () => {
    const safeUrl = referenceUrl(url);
    if (!safeUrl) {
      setError("올바른 링크를 입력해 주세요.");
      return;
    }
    if (safeUrl.length > 2048) {
      setError("참고 자료 링크는 2,048자 이하로 입력해 주세요.");
      return;
    }
    if (
      !projectSources &&
      document.sources.length >= 50 &&
      !document.sources.some((source) => source.url === safeUrl)
    ) {
      setError("문서당 참고 자료는 50개까지 추가할 수 있습니다.");
      return;
    }
    const retrieved =
      !title.trim() && !excerpt.trim() ? await fetchSource() : undefined;
    if (referenceUrl(urlRef.current) !== safeUrl) return;
    onAdd({
      id:
        document.sources.find((source) => source.url === safeUrl)?.id ??
        crypto.randomUUID(),
      url: safeUrl,
      title: (
        retrieved?.title ||
        title.trim() ||
        new URL(safeUrl).hostname
      ).slice(0, 500),
      excerpt:
        (retrieved?.excerpt || excerpt.trim()).slice(0, 20000) || undefined,
    });
    setUrl("");
    urlRef.current = "";
    setTitle("");
    setExcerpt("");
    if (retrieved || title.trim() || excerpt.trim()) setError("");
    setShowForm(false);
  };

  return (
    <div className={styles.sourcesPanel}>
      <div className={styles.panelIntro}>
        <BookOpen size={21} strokeWidth={1.5} />
        <h3>{projectSources ? "프로젝트 출처" : "글에 근거를 더하세요."}</h3>
        <p>
          {projectSources
            ? `출처 ${document.sources.length}개를 보관 중입니다. AI는 요청에 필요한 발췌만 읽습니다.`
            : "문장 옆에 인용을 남기고, 한 번의 클릭으로 원문을 확인하세요."}
        </p>
      </div>
      {projectSources && (
        <div className={styles.sourceForm}>
          <label>
            출처 찾기
            <input
              type="search"
              aria-label="출처 제목·주소 검색"
              placeholder="제목 또는 주소 검색"
              value={sourceQuery}
              onChange={(event) => {
                setSourceQuery(event.target.value);
                setVisibleCount(20);
              }}
            />
          </label>
        </div>
      )}
      {selection?.nodeId && (
        <p className={styles.fieldHint}>
          {selectedSources.size
            ? `선택한 영역에 연결된 근거 ${selectedSources.size}개를 표시합니다.`
            : "선택한 영역에 연결된 근거가 없습니다. 참고 자료를 인용해 연결할 수 있어요."}
        </p>
      )}
      <button
        className={styles.addSourceButton}
        onClick={() => {
          setShowForm(!showForm);
          setError("");
        }}
      >
        {showForm ? <X size={15} /> : <Plus size={15} />}
        {showForm ? "입력 닫기" : "참고 자료 추가"}
      </button>
      {showForm && (
        <form
          className={styles.sourceForm}
          onSubmit={(event) => {
            event.preventDefault();
            void add();
          }}
        >
          <label>
            원문 링크
            <input
              type="url"
              required
              value={url}
              onChange={(event) => {
                const next = event.target.value;
                if (referenceUrl(next) !== referenceUrl(urlRef.current)) {
                  controller.current?.abort();
                  controller.current = undefined;
                  setFetching(false);
                  setTitle("");
                  setExcerpt("");
                  setError("");
                }
                urlRef.current = next;
                setUrl(next);
              }}
              placeholder="https://…"
            />
          </label>
          <button
            className={styles.textButton}
            type="button"
            onClick={() => void fetchSource()}
            disabled={fetching || !referenceUrl(url)}
          >
            {fetching ? (
              <LoaderCircle size={14} className={styles.spin} />
            ) : (
              <Link2 size={14} />
            )}{" "}
            링크에서 제목·발췌 불러오기
          </button>
          <label>
            제목
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={500}
              placeholder="참고 글의 제목"
            />
          </label>
          <label>
            참고할 발췌 <span>선택</span>
            <textarea
              value={excerpt}
              onChange={(event) => setExcerpt(event.target.value)}
              maxLength={20000}
              rows={4}
              placeholder="AI가 근거로 활용할 내용을 붙여넣으세요."
            />
          </label>
          <p className={styles.fieldHint}>
            발췌가 있는 자료를 AI 교정의 근거로 사용합니다.
          </p>
          <button
            className={styles.acceptButton}
            disabled={fetching}
            type="submit"
          >
            {fetching ? "불러오는 중…" : "출처 추가"}
          </button>
        </form>
      )}
      {error && (
        <p className={styles.fieldError} aria-live="polite">
          {error}
        </p>
      )}
      <div className={styles.sourceList}>
        {shown.map((source, index) => {
          const citation = cited.find((item) => item.url === source.url);
          const stored = document.sources.some((item) => item.id === source.id);
          const key = `${source.id}/${source.version ?? ""}`;
          const hasExcerpt =
            (source.excerptCharacters ?? source.excerpt?.length ?? 0) > 0;
          const excerpt = bodies[key]?.excerpt ?? source.excerpt;
          return (
            <article className={styles.sourceCard} key={source.url}>
              <div className={styles.sourceCardHeading}>
                <span className={styles.sourceNumber}>
                  {citation?.label.match(/^\d+$/)
                    ? citation.label
                    : String(index + 1).padStart(2, "0")}
                </span>
                <span>
                  {new URL(source.url).hostname.replace(/^www\./, "")}
                </span>
                {stored && (
                  <button
                    className={styles.iconButton}
                    title="참고 자료 목록에서 제거 (본문 링크는 유지)"
                    aria-label={`${source.title} 참고 자료 제거`}
                    onClick={() => onRemove(source.id)}
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.sourceTitle}
              >
                {source.title}
                <ArrowUpRight size={14} />
              </a>
              {projectSources && stored && hasExcerpt && (
                <button
                  className={styles.textButton}
                  disabled={reading[key]}
                  aria-expanded={!!opened[key]}
                  onClick={() => void openExcerpt(source)}
                >
                  {reading[key]
                    ? "발췌 불러오는 중…"
                    : opened[key]
                      ? "발췌 닫기"
                      : readErrors[key]
                        ? "다시 읽기"
                        : "발췌 보기"}
                </button>
              )}
              {readErrors[key] && (
                <output className={styles.fieldError}>
                  {readErrors[key]}
                </output>
              )}
              {excerpt && (!projectSources || opened[key]) && (
                <p
                  className={styles.sourceExcerpt}
                  style={
                    projectSources
                      ? {
                          WebkitLineClamp: "unset",
                          maxHeight: "18rem",
                          overflowY: "auto",
                        }
                      : undefined
                  }
                >
                  {excerpt}
                </p>
              )}
              <div className={styles.sourceCardFooter}>
                <span>
                  {selectedSources.has(source.url)
                    ? "선택 영역의 근거"
                    : citation
                      ? `본문 ${citation.count}회 인용`
                      : hasExcerpt
                        ? "발췌 준비됨"
                        : "발췌 없음"}
                </span>
                <button
                  className={styles.textButton}
                  onClick={() => onCite(source)}
                >
                  <Quote size={13} /> 인용 넣기
                </button>
              </div>
            </article>
          );
        })}
      </div>
      {projectSources && filtered.length > shown.length && (
        <button
          className={styles.addSourceButton}
          onClick={() => setVisibleCount((count) => count + 20)}
        >
          더 보기 · {shown.length}/{filtered.length}
        </button>
      )}
      {projectSources && sourceQuery && !filtered.length && (
        <p className={styles.emptyHint}>일치하는 제목이나 주소가 없습니다.</p>
      )}
      {!references.length && (
        <p className={styles.emptyHint}>
          아직 연결된 출처가 없습니다.
          <br />
          URL을 추가하면 이곳에서 함께 관리할 수 있어요.
        </p>
      )}
      {!!references.length && (
        <p className={styles.fieldHint}>
          {hasSelection
            ? html
              ? "선택한 영역에 출처를 연결하고 인용 링크를 넣습니다."
              : "선택한 문장 바로 뒤에 인용을 넣습니다."
            : html
              ? "페이지 본문 끝에 인용 링크를 넣습니다."
              : "커서 위치 또는 문서 끝에 인용을 넣습니다."}
        </p>
      )}
    </div>
  );
}
