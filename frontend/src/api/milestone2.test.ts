import { describe, expect, it } from "vitest";
import { m2Api } from "./milestone2";

describe("M2 explicit mock contract", () => {
  it("keeps a content package in the frozen approval lifecycle", async () => {
    const item = await m2Api.createPackage(1);
    expect(item.status).toBe("draft");
    const submitted = await m2Api.packageAction(item.id, "submit");
    expect(submitted.status).toBe("submitted");
  });

  it("does not expose an image export action before confirmation and approval", async () => {
    const file = new File(["reference"], "reference.png", { type: "image/png" });
    const reference = await m2Api.uploadReference(1, file);
    const item = await m2Api.createTask(1, reference.reference_name, "商品展示图");
    expect(item.confirmed).toBe(false);
    expect(item.approval_status).toBe("draft");
  });
});
