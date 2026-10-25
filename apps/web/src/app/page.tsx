import { CloudWorkspace } from "@/components/workspace/CloudWorkspace";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const parameters = await searchParams;
  const legacyThreadId =
    parameters.legacyThreadId ?? parameters.threadId ?? parameters.thread_id;
  return (
    <CloudWorkspace
      legacyThreadId={
        typeof legacyThreadId === "string" ? legacyThreadId : undefined
      }
      authenticationEnabled={Boolean(
        process.env.COGNITO_DOMAIN && process.env.COGNITO_CLIENT_ID
      )}
    />
  );
}
