import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AdminRole, AdminUserRow } from "@/lib/api";

// Stub the api module before importing the component so users-table picks up
// the mocked patchAdminUser at module-eval time.
const patchAdminUserMock = vi.fn();

const SAVE_BUTTON_RE = /save/i;

vi.mock("@/lib/api", () => {
  class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  }
  return {
    ApiError,
    patchAdminUser: (id: string, body: { role: AdminRole }) =>
      patchAdminUserMock(id, body),
  };
});

import { UsersTable } from "./users-table";

function user(
  id: string,
  role: AdminRole,
  overrides: Partial<AdminUserRow> = {}
): AdminUserRow {
  return {
    id,
    email: `${id}@revenueinstitute.com`,
    full_name: `${id} Lastname`,
    role,
    created_at: "2026-04-01T00:00:00.000Z",
    ...overrides,
  };
}

beforeEach(() => {
  patchAdminUserMock.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("UsersTable", () => {
  it("renders one row per user with the email and role select", () => {
    const users = [user("u1", "admin"), user("u2", "viewer")];
    render(<UsersTable currentUserId={null} users={users} />);

    expect(screen.getByText("u1@revenueinstitute.com")).toBeTruthy();
    expect(screen.getByText("u2@revenueinstitute.com")).toBeTruthy();
    expect(screen.getAllByRole("combobox")).toHaveLength(2);
    expect(
      screen.getAllByRole("button", { name: SAVE_BUTTON_RE })
    ).toHaveLength(2);
  });

  it("disables Save when the role is unchanged", () => {
    const users = [user("u1", "viewer")];
    render(<UsersTable currentUserId={null} users={users} />);
    const save = screen.getByRole("button", { name: SAVE_BUTTON_RE });
    expect((save as HTMLButtonElement).disabled).toBe(true);
  });

  it("disables Save when the current admin self-demotes", () => {
    const users = [user("self", "admin")];
    render(<UsersTable currentUserId="self" users={users} />);

    const select = screen.getByRole("combobox") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "viewer" } });

    const save = screen.getByRole("button", { name: SAVE_BUTTON_RE });
    expect((save as HTMLButtonElement).disabled).toBe(true);
    expect(save.getAttribute("title")).toBe(
      "You cannot demote your own admin role."
    );
  });

  it("calls patchAdminUser and surfaces a Saved status on success", async () => {
    patchAdminUserMock.mockResolvedValue({
      ...user("u1", "reviewer"),
    });
    const users = [user("u1", "viewer")];
    render(<UsersTable currentUserId={null} users={users} />);

    const select = screen.getByRole("combobox") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "reviewer" } });

    const save = screen.getByRole("button", { name: SAVE_BUTTON_RE });
    expect((save as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(save);

    await waitFor(() => {
      expect(patchAdminUserMock).toHaveBeenCalledWith("u1", {
        role: "reviewer",
      });
    });
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toContain("Saved");
    });
  });

  it("renders an empty-state when given no users", () => {
    const { container } = render(
      <UsersTable currentUserId={null} users={[]} />
    );
    expect(container.textContent).toContain("No internal users mirrored in");
  });

  it("marks the current user with a (you) badge", () => {
    const users = [user("u1", "admin"), user("self", "viewer")];
    const { container } = render(
      <UsersTable currentUserId="self" users={users} />
    );
    const rows = Array.from(container.querySelectorAll("tbody tr"));
    const selfRow = rows.find((tr) =>
      tr.textContent?.includes("self@revenueinstitute.com")
    ) as HTMLTableRowElement | undefined;
    expect(selfRow).toBeDefined();
    if (!selfRow) {
      throw new Error("expected self row");
    }
    expect(within(selfRow).getByText("(you)")).toBeTruthy();
  });
});
