import { useToast } from "@/hooks/use-toast";
import { Assistant } from "@langchain/langgraph-sdk";
import { ContextDocument } from "@/shared/types";
import {
  createContext,
  Dispatch,
  ReactNode,
  SetStateAction,
  useContext,
  useRef,
  useState,
} from "react";
import { API_URL } from "@/constants";

type AssistantContentType = {
  assistants: Assistant[];
  selectedAssistant: Assistant | undefined;
  isLoadingAllAssistants: boolean;
  isDeletingAssistant: boolean;
  isCreatingAssistant: boolean;
  isEditingAssistant: boolean;
  getOrCreateAssistant: (userId: string) => Promise<void>;
  getAssistants: (userId: string) => Promise<void>;
  deleteAssistant: (assistantId: string) => Promise<boolean>;
  createCustomAssistant: (
    args: CreateCustomAssistantArgs
  ) => Promise<Assistant | undefined>;
  editCustomAssistant: (
    args: EditCustomAssistantArgs
  ) => Promise<Assistant | undefined>;
  setSelectedAssistant: Dispatch<SetStateAction<Assistant | undefined>>;
};

export type AssistantTool = {
  /**
   * The name of the tool
   */
  name: string;
  /**
   * The tool's description.
   */
  description: string;
  /**
   * JSON Schema for the parameters of the tool.
   */
  parameters: Record<string, any>;
};

export interface CreateAssistantFields {
  iconData?: {
    /**
     * The name of the Lucide icon to use for the assistant.
     * @default "User"
     */
    iconName: string;
    /**
     * The hex color code to use for the icon.
     */
    iconColor: string;
  };
  /**
   * The name of the assistant.
   */
  name: string;
  /**
   * An optional description of the assistant, provided by the user/
   */
  description?: string;
  /**
   * The tools the assistant has access to.
   */
  tools?: Array<AssistantTool>;
  /**
   * An optional system prompt to prefix all generations with.
   */
  systemPrompt?: string;
  is_default?: boolean;
  /**
   * The documents to include in the LLMs context.
   */
  documents?: ContextDocument[];
}

export type CreateCustomAssistantArgs = {
  newAssistant: CreateAssistantFields;
  userId: string;
  successCallback?: (id: string) => void;
};

export type EditCustomAssistantArgs = {
  editedAssistant: CreateAssistantFields;
  assistantId: string;
  userId: string;
};

const AssistantContext = createContext<AssistantContentType | undefined>(
  undefined
);

export function AssistantProvider({ children }: { children: ReactNode }) {
  const { toast } = useToast();
  const [isLoadingAllAssistants, setIsLoadingAllAssistants] = useState(false);
  const [isDeletingAssistant, setIsDeletingAssistant] = useState(false);
  const [isCreatingAssistant, setIsCreatingAssistant] = useState(false);
  const [isEditingAssistant, setIsEditingAssistant] = useState(false);
  const [assistants, setAssistants] = useState<Assistant[]>([]);
  const [selectedAssistant, setSelectedAssistant] = useState<Assistant>();
  
  // Use ref to track if getOrCreateAssistant is currently running to prevent duplicate calls
  const isGettingOrCreatingRef = useRef(false);

  const getAssistants = async (userId: string): Promise<void> => {
    // Skip for anonymous users
    if (userId === "anonymous") {
      setAssistants([]);
      return;
    }

    setIsLoadingAllAssistants(true);
    try {
      // Use fixed user_id for now (will be used for multi-user support later)
      const fixedUserId = "default";
      const response = await fetch(`${API_URL}/api/assistants/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          graph_id: "agent",
          metadata: {
            user_id: fixedUserId,
          },
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to get assistants: ${response.statusText}`);
      }

      const assistantsArray = await response.json();
      console.log("getAssistants response:", assistantsArray);
      setAssistants(Array.isArray(assistantsArray) ? assistantsArray : []);
      setIsLoadingAllAssistants(false);
    } catch (e) {
      toast({
        title: "Failed to get assistants",
        description: "Please try again later.",
      });
      console.error("Failed to get assistants", e);
      setIsLoadingAllAssistants(false);
    }
  };

  const deleteAssistant = async (assistantId: string): Promise<boolean> => {
    setIsDeletingAssistant(true);
    try {
      const response = await fetch(`${API_URL}/api/assistants/${assistantId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error(`Failed to delete assistant: ${response.statusText}`);
      }

      if (selectedAssistant?.assistant_id === assistantId) {
        // If deleting the selected assistant, set to "No Assistant" mode
        // User can manually select another assistant if they want
        setSelectedAssistant(undefined);
      }

      setAssistants((prev) =>
        prev.filter((assistant) => assistant.assistant_id !== assistantId)
      );
      setIsDeletingAssistant(false);
      return true;
    } catch (e) {
      toast({
        title: "Failed to delete assistant",
        description: "Please try again later.",
      });
      console.error("Failed to delete assistant", e);
      setIsDeletingAssistant(false);
      return false;
    }
  };

  const createCustomAssistant = async ({
    newAssistant,
    userId,
    successCallback,
  }: CreateCustomAssistantArgs): Promise<Assistant | undefined> => {
    // Skip for anonymous users
    if (userId === "anonymous") {
      toast({
        title: "Cannot create assistant",
        description: "Assistants are not available for anonymous users.",
        variant: "destructive",
      });
      return undefined;
    }

    setIsCreatingAssistant(true);
    try {
      const { tools, systemPrompt, name, documents, ...metadata } =
        newAssistant;
      // Use fixed user_id for now (will be used for multi-user support later)
      const fixedUserId = "default";
      const response = await fetch(`${API_URL}/api/assistants`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          graph_id: "agent",
          name,
          metadata: {
            user_id: fixedUserId,
            ...metadata,
          },
          config: {
            configurable: {
              tools,
              systemPrompt,
              documents,
            },
          },
          if_exists: "return_existing",
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to create assistant: ${response.statusText}`);
      }

      const createdAssistant = await response.json();
      setAssistants((prev) => [...prev, createdAssistant]);
      setSelectedAssistant(createdAssistant);
      successCallback?.(createdAssistant.assistant_id);
      setIsCreatingAssistant(false);
      return createdAssistant;
    } catch (e) {
      toast({
        title: "Failed to create assistant",
        description: "Please try again later.",
      });
      setIsCreatingAssistant(false);
      console.error("Failed to create an assistant", e);
      return undefined;
    }
  };

  const editCustomAssistant = async ({
    editedAssistant,
    assistantId,
    userId,
  }: EditCustomAssistantArgs): Promise<Assistant | undefined> => {
    setIsEditingAssistant(true);
    try {
      const { tools, systemPrompt, name, documents, ...metadata } =
        editedAssistant;
      // Use fixed user_id for now (will be used for multi-user support later)
      const fixedUserId = "default";
      const response = await fetch(`${API_URL}/api/assistants/${assistantId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name,
          graph_id: "agent",
          metadata: {
            user_id: fixedUserId,
            ...metadata,
          },
          config: {
            configurable: {
              tools,
              systemPrompt,
              documents,
            },
          },
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to update assistant: ${response.statusText}`);
      }

      const updatedAssistant = await response.json();
      setAssistants((prev) =>
        prev.map((assistant) => {
          if (assistant.assistant_id === assistantId) {
            return updatedAssistant;
          }
          return assistant;
        })
      );
      setIsEditingAssistant(false);
      return updatedAssistant;
    } catch (e) {
      console.error("Failed to edit assistant", e);
      setIsEditingAssistant(false);
      return undefined;
    }
  };

  const getOrCreateAssistant = async (userId: string) => {
    // Early return if already have an assistant
    if (selectedAssistant) {
      return;
    }
    
    // Prevent concurrent execution
    if (isGettingOrCreatingRef.current) {
      return;
    }
    
    isGettingOrCreatingRef.current = true;
    setIsLoadingAllAssistants(true);

    try {
      const fixedUserId = "default";

      // Search for existing assistants
      const searchResponse = await fetch(`${API_URL}/api/assistants/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          graph_id: "agent",
          metadata: {
            user_id: fixedUserId,
          },
          limit: 100,
        }),
      });

      if (!searchResponse.ok) {
        throw new Error(`Failed to search assistants: ${searchResponse.statusText}`);
      }

      const searchResult = await searchResponse.json();
      let userAssistants: Assistant[] = Array.isArray(searchResult) ? searchResult : [];

      // No assistants mode: Don't create default assistant automatically
      // "No Assistant" is the default - users can create assistants manually if they want reflection functionality
      // Don't auto-select assistants even if they exist - let user choose explicitly

      // Update state with assistants (but don't auto-select)
      setAssistants(userAssistants);
      // Keep selectedAssistant as undefined (No Assistant mode)
    } catch (e) {
      console.error("Failed to get or create assistant", e);
    } finally {
      isGettingOrCreatingRef.current = false;
      setIsLoadingAllAssistants(false);
    }
  };

  const contextValue: AssistantContentType = {
    assistants,
    selectedAssistant,
    isLoadingAllAssistants,
    isDeletingAssistant,
    isCreatingAssistant,
    isEditingAssistant,
    getOrCreateAssistant,
    getAssistants,
    deleteAssistant,
    createCustomAssistant,
    editCustomAssistant,
    setSelectedAssistant,
  };

  return (
    <AssistantContext.Provider value={contextValue}>
      {children}
    </AssistantContext.Provider>
  );
}

export function useAssistantContext() {
  const context = useContext(AssistantContext);
  if (context === undefined) {
    throw new Error(
      "useAssistantContext must be used within a AssistantProvider"
    );
  }
  return context;
}
