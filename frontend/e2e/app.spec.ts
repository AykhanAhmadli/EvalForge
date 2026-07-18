import { expect, test } from "@playwright/test";

test("loads the seeded evaluation workspace", async ({ page }) => {
  await page.route("**/health/live", async (route) =>
    route.fulfill({ json: { status: "ok", service: "api" } }),
  );
  await page.route("**/api/v1/workspaces", async (route) =>
    route.fulfill({
      json: [{ id: "workspace-1", name: "Local Workspace", slug: "local", description: null }],
    }),
  );
  await page.route("**/api/v1/runs", async (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/workspaces/workspace-1/evaluation-runs", async (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/workspaces/workspace-1/datasets", async (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/workspaces/workspace-1/prompt-templates", async (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/workspaces/workspace-1/model-configurations", async (route) =>
    route.fulfill({ json: [] }),
  );

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("Local Workspace")).toBeVisible();
});
