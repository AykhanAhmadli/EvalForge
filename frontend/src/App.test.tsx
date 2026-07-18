import "@testing-library/jest-dom";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, test, vi } from "vitest";

import { App } from "./App";

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

describe("App", () => {
  test("renders evaluation metadata from the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.endsWith("/health/live")) {
          return Promise.resolve(new Response(JSON.stringify({ status: "ok", service: "api" })));
        }
        if (url.endsWith("/api/v1/lifecycle")) {
          return Promise.resolve(
            new Response(JSON.stringify({ evaluation_run_statuses: ["queued", "completed"] })),
          );
        }
        return Promise.resolve(
          new Response(
            JSON.stringify({
              metrics: [
                {
                  name: "exact_match",
                  display_name: "Exact Match",
                  direction: "higher_is_better",
                  semantics: "Deterministic equality check.",
                },
              ],
            }),
          ),
        );
      }),
    );

    renderApp();

    expect(screen.getByRole("heading", { name: "Evaluation Control Plane" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("API live")).toBeInTheDocument());
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText("Exact Match")).toBeInTheDocument();
  });
});
