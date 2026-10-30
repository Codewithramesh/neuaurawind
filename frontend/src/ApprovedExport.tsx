import { useState } from "react";
import { api } from "./api";
import { ErrorNotice } from "./ui";
export function ApprovedExport() {
  const [error, setError] = useState("");
  return (
    <div className="approved-export">
      <button
        className="button secondary small"
        onClick={async () => {
          setError("");
          try {
            const data = await api("/exports");
            const url = URL.createObjectURL(
              new Blob([JSON.stringify(data, null, 2)], {
                type: "application/json",
              }),
            );
            const link = document.createElement("a");
            link.href = url;
            link.download = "neuaura-approved.json";
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          } catch (e) {
            setError((e as Error).message);
          }
        }}
      >
        Export approved records (JSON)
      </button>
      <p className="field-help">
        Reviewer access required. Includes approved findings and approved tasks
        only. Downloaded copies cannot be recalled.
      </p>
      <ErrorNotice message={error} />
    </div>
  );
}
