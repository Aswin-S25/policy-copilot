import { Link } from "react-router-dom";
import { ViewHeader } from "./layout/ViewHeader";

export function NotFoundView() {
  return (
    <>
      <ViewHeader title="Page not found" />
      <div className="mx-auto flex w-full max-w-[46rem] flex-1 flex-col justify-center px-6">
        <h2 className="text-heading font-semibold text-ink">This page doesn't exist</h2>
        <p className="mt-2 text-body text-muted">
          Check the address, or{" "}
          <Link to="/" className="font-medium text-accent underline-offset-2 hover:underline">
            start a new conversation
          </Link>
          .
        </p>
      </div>
    </>
  );
}
