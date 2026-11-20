import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import type { ConversationSummary } from "../api/types";
import { useAuth, useSession } from "../auth/AuthContext";
import { demoPersonaName, roleName } from "../auth/session";
import { isInFlight, useTurn } from "../chat/turns";
import { groupByRecency, UNTITLED, useConversations } from "../conversations/ConversationsContext";
import { DeleteConversationDialog } from "../conversations/DeleteConversationDialog";
import { Button, IconButton } from "../ui/Button";
import { BrandMark, Spinner } from "../ui/feedback";
import { CloseIcon, DocumentIcon, PlusIcon, SidebarIcon, SignOutIcon, TrashIcon } from "../ui/icons";
import { useShell } from "./shell";

export function Sidebar() {
  const { isDesktop, hideSidebar } = useShell();
  const navigate = useNavigate();

  return (
    <nav aria-label="Main" className="flex h-full flex-col">
      <div className="flex h-14 shrink-0 items-center justify-between gap-2 pr-2 pl-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <BrandMark size={24} />
          <span className="truncate text-control font-semibold tracking-[-0.01em] text-ink">
            Policy Copilot
          </span>
        </div>
        <IconButton label={isDesktop ? "Hide sidebar" : "Close navigation"} onClick={hideSidebar}>
          {isDesktop ? <SidebarIcon /> : <CloseIcon />}
        </IconButton>
      </div>

      <div className="shrink-0 space-y-0.5 px-3 pb-3">
        <Button
          className="mb-2 w-full justify-start"
          icon={<PlusIcon size={16} />}
          onClick={() => navigate("/")}
          aria-keyshortcuts="Control+Shift+O Meta+Shift+O"
          title="New chat (Ctrl+Shift+O)"
        >
          New chat
        </Button>
        <NavLink
          to="/documents"
          className={({ isActive }) =>
            "flex h-8 items-center gap-2.5 rounded-control px-2 text-ui transition-colors duration-100 " +
            (isActive
              ? "bg-surface font-medium text-ink shadow-[inset_0_0_0_1px_var(--color-line)]"
              : "text-ink-soft hover:bg-sunken hover:text-ink")
          }
        >
          <DocumentIcon size={16} className="text-muted" />
          Policy documents
        </NavLink>
      </div>

      <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto px-2 pb-4">
        <ConversationList />
      </div>

      <AccountFooter />
    </nav>
  );
}

function ConversationList() {
  const { status, items, error, refresh } = useConversations();
  const [deleting, setDeleting] = useState<ConversationSummary | null>(null);

  if (status === "loading") {
    return (
      <div aria-busy="true" aria-label="Loading conversations" className="space-y-1 px-2 pt-3">
        {[72, 88, 64, 80].map((width) => (
          <div key={width} className="flex h-8 items-center">
            <div className="h-2.5 animate-pulse rounded-full bg-line" style={{ width: `${width}%` }} />
          </div>
        ))}
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="px-2 pt-3 text-ui">
        <p className="text-muted">{error}</p>
        <button
          type="button"
          onClick={refresh}
          className="mt-1.5 font-medium text-accent underline-offset-2 hover:underline"
        >
          Try again
        </button>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <p className="px-2 pt-3 text-ui text-faint">
        No conversations yet. Questions you ask are saved here.
      </p>
    );
  }

  return (
    <>
      <h2 className="sr-only">Conversations</h2>
      {groupByRecency(items).map((group) => (
        <section key={group.label} aria-labelledby={`group-${group.label}`} className="pt-3 first:pt-1">
          <h3 id={`group-${group.label}`} className="px-2 pb-1 text-meta font-medium text-muted">
            {group.label}
          </h3>
          <ul>
            {group.items.map((item) => (
              <li key={item.id}>
                <ConversationLink item={item} onDelete={() => setDeleting(item)} />
              </li>
            ))}
          </ul>
        </section>
      ))}
      <DeleteConversationDialog conversation={deleting} onClose={() => setDeleting(null)} />
    </>
  );
}

function ConversationLink({ item, onDelete }: { item: ConversationSummary; onDelete: () => void }) {
  const turn = useTurn(item.id);
  const busy = isInFlight(turn);
  const title = item.title ?? turn?.question ?? UNTITLED;

  return (
    // The delete button is a sibling of the link, not inside it: a button
    // inside a link is invalid and unreachable for assistive tech.
    <div className="group relative">
      <NavLink
        to={`/c/${item.id}`}
        className={({ isActive }) =>
          "flex h-8 items-center gap-2 rounded-control pr-8 pl-2 text-ui transition-colors duration-100 " +
          (isActive
            ? "bg-surface font-medium text-ink shadow-[inset_0_0_0_1px_var(--color-line)]"
            : "text-ink-soft hover:bg-sunken hover:text-ink")
        }
      >
        <span className="min-w-0 flex-1 truncate">{title}</span>
        {busy && <Spinner size={12} label="Answering" />}
      </NavLink>
      <IconButton
        label={`Delete “${title}”`}
        size="sm"
        onClick={onDelete}
        className={
          "absolute top-0.5 right-0.5 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 " +
          "pointer-coarse:opacity-100"
        }
      >
        <TrashIcon size={15} />
      </IconButton>
    </div>
  );
}

function AccountFooter() {
  const session = useSession();
  const { signOut } = useAuth();
  const roles = session.roles.map(roleName).join(", ");
  // Demo identities are random ("demo-hr-1a2b3c4d"); show the role instead.
  const demoPersona = demoPersonaName(session);
  const name = demoPersona ? `${demoPersona} (demo)` : session.subject;

  return (
    <div className="flex shrink-0 items-center gap-2.5 border-t border-line px-3 py-2.5">
      <span
        aria-hidden="true"
        className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-ui font-semibold text-accent-ink uppercase"
      >
        {name.slice(0, 1)}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-ui font-medium text-ink">{name}</p>
        <p className="truncate text-meta text-muted" title={roles}>
          {roles}
        </p>
      </div>
      <IconButton label={demoPersona ? "Sign out to switch role" : "Sign out"} onClick={() => signOut()}>
        <SignOutIcon size={17} />
      </IconButton>
    </div>
  );
}
