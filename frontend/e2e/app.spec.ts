import { expect, test } from "@playwright/test";

test("loads the EvalForge evaluation workspace", async ({ page }) => {
  await page.route("**/health/live", async (route) => {
    await route.fulfill({ json: { status: "ok", service: "api" } });
  });
  await page.route("**/api/v1/lifecycle", async (route) => {
    await route.fulfill({ json: { evaluation_run_statuses: ["queued", "completed"] } });
  });
  await page.route("**/api/v1/metrics", async (route) => {
    await route.fulfill({
      json: {
        metrics: [
          {
            name: "exact_match",
            display_name: "Exact Match",
            direction: "higher_is_better",
            semantics: "Deterministic equality check.",
          },
        ],
      },
    });
  });

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Evaluation Control Plane" })).toBeVisible();
  await expect(page.getByText("API live")).toBeVisible();
  await expect(page.getByText("Exact Match")).toBeVisible();
});
