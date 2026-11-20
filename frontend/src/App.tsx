import { Route, Routes } from "react-router-dom";
import { AuthProvider, RequireAuth } from "./auth/AuthContext";
import { LoginView } from "./auth/LoginView";
import { ConversationView } from "./chat/ConversationView";
import { NewChatView } from "./chat/NewChatView";
import { ConversationsProvider } from "./conversations/ConversationsContext";
import { DocumentsView } from "./documents/DocumentsView";
import { AppShell } from "./layout/AppShell";
import { NotFoundView } from "./NotFoundView";

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginView />} />
        <Route
          element={
            <RequireAuth>
              <ConversationsProvider>
                <AppShell />
              </ConversationsProvider>
            </RequireAuth>
          }
        >
          <Route index element={<NewChatView />} />
          <Route path="c/:conversationId" element={<ConversationView />} />
          <Route path="documents" element={<DocumentsView />} />
          <Route path="*" element={<NotFoundView />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
