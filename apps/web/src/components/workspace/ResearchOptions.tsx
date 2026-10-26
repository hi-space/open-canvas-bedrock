import type { CloudFileSummary } from "../../lib/workspace/cloud-types";
import cloud from "./cloud.module.css";

export function ResearchOptions({
  files,
  selectedPaths,
  onChange,
  sourceCount,
  disabled = false,
}: {
  files: Pick<CloudFileSummary, "path">[];
  selectedPaths: string[];
  onChange: (paths: string[]) => void;
  sourceCount: number;
  disabled?: boolean;
}) {
  return (
    <fieldset className={cloud.researchMaterials}>
      <legend>프로젝트 자료 · {selectedPaths.length}개 선택</legend>
      {!!files.length && (
        <div className={cloud.researchFileList}>
          {files.map((file) => {
            const checked = selectedPaths.includes(file.path);
            return (
              <label key={file.path}>
                <input
                  type="checkbox"
                  value={file.path}
                  checked={checked}
                  disabled={disabled || (!checked && selectedPaths.length >= 5)}
                  onChange={(event) =>
                    onChange(
                      event.currentTarget.checked
                        ? [...selectedPaths, file.path]
                        : selectedPaths.filter((path) => path !== file.path)
                    )
                  }
                />
                <span>{file.path}</span>
              </label>
            );
          })}
        </div>
      )}
      <p>
        {files.length ? "파일은 다섯 개까지 선택할 수 있어요. " : ""}
        {sourceCount
          ? `보관된 출처 ${sourceCount}개에서 필요한 근거를 검색해 읽습니다.`
          : "웹 자료를 함께 조사합니다."}{" "}
        긴 파일은 도입부와 끝부분을 참고합니다.
      </p>
    </fieldset>
  );
}
