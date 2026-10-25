// Authentication is disabled, but the context retains the user contract used
// by canvas consumers and their anonymous-user fallback.
export type User = {
  id: string;
  email?: string;
};
import { createContext, ReactNode, useContext } from "react";

type UserContentType = {
  getUser: () => Promise<User | undefined>;
  user: User | undefined;
  loading: boolean;
};

const UserContext = createContext<UserContentType | undefined>(undefined);

const contextValue: UserContentType = {
  getUser: async () => undefined,
  user: undefined,
  loading: false,
};

export function UserProvider({ children }: { children: ReactNode }) {
  return (
    <UserContext.Provider value={contextValue}>{children}</UserContext.Provider>
  );
}

export function useUserContext() {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error("useUserContext must be used within a UserProvider");
  }
  return context;
}
