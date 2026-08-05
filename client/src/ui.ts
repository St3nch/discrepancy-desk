import {
  approveRun,
  createCase,
  createRun,
  getCase,
  listCases,
  type CaseRecord,
  type GetCaseResult,
  type RunRecord,
} from "./api.ts";

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Record<string, string> = {},
  children: (Node | string)[] = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "className") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) {
    node.append(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

type View =
  | { kind: "list" }
  | { kind: "detail"; caseId: number };

export function mount(root: HTMLElement): void {
  let view: View = { kind: "list" };
  const status = el("p", { className: "status" });
  const main = el("div", { className: "main" });

  async function setStatus(message: string, isError = false): Promise<void> {
    status.textContent = message;
    status.classList.toggle("error", isError);
  }

  async function render(): Promise<void> {
    main.replaceChildren();
    if (view.kind === "list") {
      await renderList();
    } else {
      await renderDetail(view.caseId);
    }
  }

  async function renderList(): Promise<void> {
    const titleInput = el("input", {
      type: "text",
      "aria-label": "Case title",
      placeholder: "Case title (investigation topic)",
    }) as HTMLInputElement;

    const createBtn = el("button", { type: "button", text: "Create case" });
    createBtn.addEventListener("click", () => {
      void (async () => {
        try {
          const created = await createCase(titleInput.value);
          titleInput.value = "";
          await setStatus(`Created case #${created.case_id}: ${created.title}`);
          await render();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    const listEl = el("ul", { className: "case-list" });
    let cases: CaseRecord[] = [];
    try {
      const result = await listCases();
      cases = result.cases;
      await setStatus(
        cases.length === 0
          ? "No cases yet. Create one to begin."
          : `${cases.length} case(s).`,
      );
    } catch (err) {
      await setStatus(err instanceof Error ? err.message : String(err), true);
    }

    if (cases.length === 0) {
      listEl.append(el("li", { className: "empty", text: "No cases yet." }));
    } else {
      for (const c of cases) {
        const openBtn = el("button", {
          type: "button",
          className: "linkish",
          text: "Open",
        });
        openBtn.addEventListener("click", () => {
          view = { kind: "detail", caseId: c.case_id };
          void render();
        });
        listEl.append(
          el("li", {}, [
            el("strong", { text: `#${c.case_id} ` }),
            document.createTextNode(c.title),
            el("span", { className: "meta", text: ` · ${c.created_at}` }),
            document.createTextNode(" "),
            openBtn,
          ]),
        );
      }
    }

    main.append(
      el("section", { className: "panel" }, [
        el("h2", { text: "Create case" }),
        el("label", {}, ["Title ", titleInput]),
        el("div", { className: "row" }, [createBtn]),
      ]),
      el("section", { className: "panel" }, [
        el("h2", { text: "Cases" }),
        listEl,
      ]),
    );
  }

  function renderRunRow(run: RunRecord, onChange: () => void): HTMLElement {
    const row = el("li", { className: "run-row" }, [
      el("strong", { text: `#${run.run_id} ` }),
      el("span", { className: `status-chip status-${run.status}`, text: run.status }),
      document.createTextNode(` — ${run.question}`),
      el("div", { className: "meta", text: `scope: ${run.scope}` }),
    ]);

    if (run.status === "draft") {
      const approveBtn = el("button", { type: "button", text: "Approve" });
      approveBtn.addEventListener("click", () => {
        void (async () => {
          try {
            await approveRun(run.run_id);
            await setStatus(`Approved run #${run.run_id} (now claimable).`);
            onChange();
          } catch (err) {
            await setStatus(err instanceof Error ? err.message : String(err), true);
          }
        })();
      });
      row.append(document.createTextNode(" "), approveBtn);
    }

    return row;
  }

  async function renderDetail(caseId: number): Promise<void> {
    let detail: GetCaseResult | null = null;
    try {
      detail = await getCase(caseId);
      await setStatus(`Opened case #${caseId}.`);
    } catch (err) {
      await setStatus(err instanceof Error ? err.message : String(err), true);
    }

    const backBtn = el("button", { type: "button", text: "← All cases" });
    backBtn.addEventListener("click", () => {
      view = { kind: "list" };
      void render();
    });

    if (!detail) {
      main.append(
        el("section", { className: "panel" }, [
          backBtn,
          el("p", { text: "Could not load case." }),
        ]),
      );
      return;
    }

    const c = detail.case;
    const questionInput = el("input", {
      type: "text",
      "aria-label": "Run question",
      placeholder: "Explicit research question",
    }) as HTMLInputElement;
    const scopeInput = el("textarea", {
      rows: "2",
      "aria-label": "Run scope",
      placeholder: "Bounded scope",
    }) as HTMLTextAreaElement;

    const dispatchBtn = el("button", {
      type: "button",
      text: "Create run (draft)",
    });
    dispatchBtn.addEventListener("click", () => {
      void (async () => {
        try {
          const run = await createRun(caseId, questionInput.value, scopeInput.value);
          questionInput.value = "";
          scopeInput.value = "";
          await setStatus(`Created run #${run.run_id} as draft.`);
          await render();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    const runsList = el("ul", { className: "run-list" });
    if (detail.runs.length === 0) {
      runsList.append(el("li", { className: "empty", text: "No runs yet." }));
    } else {
      for (const run of detail.runs) {
        runsList.append(
          renderRunRow(run, () => {
            void render();
          }),
        );
      }
    }

    main.append(
      el("section", { className: "panel" }, [
        backBtn,
        el("h2", { text: c.title }),
        el("p", {
          className: "meta",
          text: `Case #${c.case_id} · created ${c.created_at}`,
        }),
      ]),
      el("section", { className: "panel" }, [
        el("h2", { text: "Dispatch research run" }),
        el("p", {
          className: "subtitle",
          text: "Creates a draft. Approve to make it claimable by an executor (pull).",
        }),
        el("label", {}, ["Question ", questionInput]),
        el("label", {}, ["Scope ", scopeInput]),
        el("div", { className: "row" }, [dispatchBtn]),
      ]),
      el("section", { className: "panel" }, [
        el("h2", { text: "Runs" }),
        el("p", {
          className: "subtitle",
          text: "Statuses: draft · approved · claimed (full vocabulary includes suspended, complete, abandoned, cancelled).",
        }),
        runsList,
      ]),
      el("section", { className: "panel" }, [
        el("h2", { text: "Claims" }),
        el("p", {
          className: "subtitle",
          text: "Model-proposed claims stay unconfirmed until angle work (ticket 11). Unconfirmed is always loud.",
        }),
        detail.claims.length === 0
          ? el("p", { className: "empty", text: "No claims yet." })
          : el(
              "ul",
              { className: "claim-list" },
              detail.claims.map((cl) => {
                const isUnconfirmed = cl.confirmation_status === "unconfirmed";
                return el(
                  "li",
                  {
                    className: isUnconfirmed
                      ? "claim-card claim-unconfirmed"
                      : "claim-card",
                  },
                  [
                    el("div", { className: "claim-banner" }, [
                      el("span", {
                        className: "claim-status-badge",
                        text: isUnconfirmed
                          ? "⚠ UNCONFIRMED — model-proposed, not human-reviewed"
                          : cl.confirmation_status.toUpperCase(),
                      }),
                    ]),
                    el("p", {
                      className: "claim-proposition",
                      text: `#${cl.claim_id}: ${cl.proposition}`,
                    }),
                    el("p", {
                      className: "meta",
                      text: `run #${cl.run_id} · ${cl.posture} · ${cl.source_basis} · ${cl.certainty}`,
                    }),
                  ],
                );
              }),
            ),
      ]),
      el("section", { className: "panel" }, [
        el("h2", { text: "Also on this case" }),
        el("ul", { className: "empty-slots" }, [
          el("li", { text: `Captures: ${detail.captures.length}` }),
          el("li", { text: `Open questions: ${detail.open_questions.length}` }),
          el("li", { text: `Angles: ${detail.angles.length}` }),
          el("li", { text: `Renditions: ${detail.renditions.length}` }),
        ]),
      ]),
    );
  }

  root.replaceChildren(
    el("header", {}, [
      el("h1", { text: "Discrepancy Desk" }),
      el("p", {
        className: "subtitle",
        text: "Cases and research runs. Dispatch is human-only; executors claim via MCP.",
      }),
    ]),
    status,
    main,
  );

  void render();
}
