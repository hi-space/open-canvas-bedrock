import { parse, type DefaultTreeAdapterTypes } from "parse5";

const MANAGED_IMAGE =
  /^\/api\/research\/assets\/[A-Za-z0-9_-]{1,80}\/[A-Za-z0-9_-]{1,80}\.png$/;
const MAX_IMAGES = 12;
const MAX_IMAGE_BYTES = 2 * 1024 * 1024;
const MAX_TOTAL_BYTES = 8 * 1024 * 1024;
const MAX_IMAGE_PIXELS = 64 * 1024 * 1024;
const LOAD_TIMEOUT_MS = 15000;
const PNG_SIGNATURE = [137, 80, 78, 71, 13, 10, 26, 10];

interface ImageReference {
  url: string;
  start: number;
  end: number;
}

function researchImages(content: string): ImageReference[] {
  const tree = parse(content, { sourceCodeLocationInfo: true });
  const images: ImageReference[] = [];
  const visit = (node: DefaultTreeAdapterTypes.Node) => {
    if ("tagName" in node && node.tagName === "img") {
      const url = node.attrs.find(
        (attribute) => attribute.name === "src"
      )?.value;
      const location = node.sourceCodeLocation?.attrs?.src;
      if (url && location && MANAGED_IMAGE.test(url))
        images.push({
          url,
          start: location.startOffset,
          end: location.endOffset,
        });
    }
    if ("childNodes" in node) node.childNodes.forEach(visit);
  };
  visit(tree);
  return images;
}

async function readPng(response: Response, limit: number): Promise<Uint8Array> {
  if (
    !response.ok ||
    response.redirected ||
    response.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !==
      "image/png"
  )
    throw new Error("Unavailable research image");
  const reader = response.body?.getReader();
  if (!reader) throw new Error("Empty research image");
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      size += chunk.value.byteLength;
      if (size > limit) {
        await reader.cancel();
        throw new Error("Research image exceeds the download limit");
      }
      chunks.push(chunk.value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  if (
    size < 33 ||
    !PNG_SIGNATURE.every((value, index) => bytes[index] === value) ||
    String.fromCharCode(...bytes.subarray(12, 16)) !== "IHDR"
  )
    throw new Error("Invalid research PNG");
  const header = new DataView(bytes.buffer);
  const width = header.getUint32(16);
  const height = header.getUint32(20);
  if (!width || !height || width * height > MAX_IMAGE_PIXELS)
    throw new Error("Research PNG dimensions exceed the decoding limit");
  return bytes;
}

function dataImage(bytes: Uint8Array): string {
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 16384)
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 16384));
  return `data:image/png;base64,${btoa(binary)}`;
}

function verifyImage(embedded: string, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    let finished = false;
    const finish = (error?: Error) => {
      if (finished) return;
      finished = true;
      image.onload = null;
      image.onerror = null;
      signal.removeEventListener("abort", cancel);
      image.removeAttribute("src");
      if (error) reject(error);
      else resolve();
    };
    const cancel = () => finish(new DOMException("Aborted", "AbortError"));
    image.onload = () =>
      finish(
        image.naturalWidth && image.naturalHeight
          ? undefined
          : new Error("Research PNG could not be decoded")
      );
    image.onerror = () =>
      finish(new Error("Research PNG could not be decoded"));
    signal.addEventListener("abort", cancel, { once: true });
    if (signal.aborted) cancel();
    else image.src = embedded;
  });
}

/** Resolve only authenticated managed figures, without changing canonical HTML. */
export async function resolveHtmlResearchImages(
  content: string,
  signal?: AbortSignal
): Promise<{ content: string; missing: string[] }> {
  const references = researchImages(content);
  if (!references.length) return { content, missing: [] };
  const urls = [...new Set(references.map((image) => image.url))];
  const images = new Map<string, string>();
  const missing: string[] = [];
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal?.addEventListener("abort", cancel, { once: true });
  if (signal?.aborted) cancel();
  const timeout = setTimeout(cancel, LOAD_TIMEOUT_MS);
  let totalBytes = 0;
  try {
    for (const [index, url] of urls.entries()) {
      if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
      if (
        index >= MAX_IMAGES ||
        controller.signal.aborted ||
        totalBytes >= MAX_TOTAL_BYTES
      ) {
        missing.push(url);
        continue;
      }
      try {
        const response = await fetch(url, {
          credentials: "same-origin",
          redirect: "error",
          cache: "no-store",
          signal: controller.signal,
        });
        if (controller.signal.aborted)
          throw new DOMException("Aborted", "AbortError");
        const bytes = await readPng(
          response,
          Math.min(MAX_IMAGE_BYTES, MAX_TOTAL_BYTES - totalBytes)
        );
        totalBytes += bytes.byteLength;
        const embedded = dataImage(bytes);
        await verifyImage(embedded, controller.signal);
        images.set(url, embedded);
      } catch {
        if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
        missing.push(url);
      }
    }
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", cancel);
  }
  let resolved = content;
  for (const reference of [...references].sort((a, b) => b.start - a.start)) {
    const embedded = images.get(reference.url);
    if (embedded)
      resolved =
        resolved.slice(0, reference.start) +
        `src="${embedded}"` +
        resolved.slice(reference.end);
  }
  return { content: resolved, missing };
}

/** A download must contain every managed image, never an expiring app URL. */
export async function standaloneHtml(
  content: string,
  signal?: AbortSignal
): Promise<string> {
  const resolved = await resolveHtmlResearchImages(content, signal);
  if (resolved.missing.length)
    throw new Error(
      `그림 ${resolved.missing.length}개를 불러오지 못해 다운로드를 준비하지 못했습니다. 다시 시도해 주세요.`
    );
  return resolved.content;
}
