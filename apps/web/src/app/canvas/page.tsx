import { redirect } from "next/navigation";

export default async function ConversationCanvas({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const parameters = await searchParams;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(parameters)) {
    if (typeof value === "string") query.set(key, value);
    else if (Array.isArray(value))
      value.forEach((item) => query.append(key, item));
  }
  const threadId = query.get("threadId") ?? query.get("thread_id");
  if (threadId) query.set("legacyThreadId", threadId);
  redirect(query.size ? `/?${query}` : "/");
}
