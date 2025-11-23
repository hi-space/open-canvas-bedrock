import { useCallback, useState } from "react";
import { API_URL } from "@/constants";

export interface Feedback {
  id?: string;
  run_id?: string;
  key?: string;
  score?: number;
  value?: number;
  comment?: string;
  [key: string]: any;
}

export interface FeedbackResponse {
  success: boolean;
  feedback: Feedback;
}

interface UseFeedbackResult {
  isLoading: boolean;
  error: string | null;
  sendFeedback: (
    runId: string,
    feedbackKey: string,
    score: number,
    comment?: string
  ) => Promise<FeedbackResponse | undefined>;
  getFeedback: (
    runId: string,
    feedbackKey: string
  ) => Promise<Feedback[] | undefined>;
}

export function useFeedback(): UseFeedbackResult {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const sendFeedback = useCallback(
    async (
      runId: string,
      feedbackKey: string,
      score: number,
      comment?: string
    ): Promise<FeedbackResponse | undefined> => {
      setIsLoading(true);
      setError(null);

      try {
        const res = await fetch(`${API_URL}/runs/feedback`, {
          method: "POST",
          body: JSON.stringify({ runId, feedbackKey, score, comment }),
          headers: {
            "Content-Type": "application/json",
          },
        });

        if (!res.ok) {
          return;
        }

        return (await res.json()) as FeedbackResponse;
      } catch (error) {
        console.error("Error sending feedback:", error);
        setError(
          error instanceof Error ? error.message : "An unknown error occurred"
        );
        return;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const getFeedback = useCallback(
    async (
      runId: string,
      feedbackKey: string
    ): Promise<Feedback[] | undefined> => {
      setIsLoading(true);
      setError(null);
      try {
        const res = await fetch(
          `${API_URL}/runs/feedback?runId=${encodeURIComponent(runId)}&feedbackKey=${encodeURIComponent(feedbackKey)}`
        );

        if (!res.ok) {
          return;
        }

        const data = await res.json();
        return data.feedback;
      } catch (error) {
        console.error("Error getting feedback:", error);
        setError(
          error instanceof Error ? error.message : "An unknown error occurred"
        );
        return;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  return {
    isLoading,
    sendFeedback,
    getFeedback,
    error,
  };
}
