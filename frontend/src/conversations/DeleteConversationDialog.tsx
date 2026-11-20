import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { deleteConversation } from "../api/conversations";
import { clearTurn, stopTurn } from "../chat/turns";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { UNTITLED, useConversations } from "./ConversationsContext";

interface Props {
  conversation: { id: string; title: string | null } | null;
  onClose: () => void;
}

/** Confirms and deletes a conversation; leaves it if it's the one on screen. */
export function DeleteConversationDialog({ conversation, onClose }: Props) {
  const { remove } = useConversations();
  const navigate = useNavigate();
  const location = useLocation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    if (!conversation) return;
    setBusy(true);
    setError(null);
    try {
      // Stop any answer in progress first; the server discards its question.
      stopTurn(conversation.id);
      await deleteConversation(conversation.id);
    } catch (err) {
      // 404: already gone (deleted in another tab). The outcome is the same.
      if (!(err instanceof ApiError && err.status === 404)) {
        setError(err instanceof ApiError ? err.message : "Couldn't delete this conversation. Try again.");
        setBusy(false);
        return;
      }
    }
    clearTurn(conversation.id);
    remove(conversation.id);
    if (location.pathname === `/c/${conversation.id}`) navigate("/", { replace: true });
    setBusy(false);
    onClose();
  }

  return (
    <ConfirmDialog
      open={conversation !== null}
      title="Delete conversation?"
      confirmLabel="Delete"
      busyLabel="Deleting…"
      busy={busy}
      error={error}
      onConfirm={confirm}
      onCancel={() => {
        setError(null);
        onClose();
      }}
    >
      <p>
        <span className="font-medium text-ink">“{conversation?.title ?? UNTITLED}”</span> and all
        of its answers will be permanently deleted.
      </p>
    </ConfirmDialog>
  );
}
