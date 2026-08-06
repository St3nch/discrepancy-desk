import {
  addLead,
  answerSuspendedRun,
  approveRun,
  attachLead,
  cancelRun,
  createCase,
  createOperatorOpenQuestion,
  createRun,
  decideOpenQuestion,
  disposeLead,
  getCase,
  getRunClose,
  listCases,
  listLeads,
  promoteLead,
  summariseLead,
  type CaseRecord,
  type GetCaseResult,
  type GetRunCloseResult,
  type LeadRecord,
  type OpenQuestionRecord,
  type RunRecord,
} from "./api.ts";

/** D9 / F-29 — must appear on every suspended run panel. */
export const INSTANCE_VS_CLASS_NOTICE =
  "This answer resolves this run instance only. If the same uncertainty keeps recurring, amend the relevant rubric separately.";

const DISPOSITIONS = [
  "not-yet-worked",
  "unresolved-awaiting-external-development",
  "unresolved-likely-permanent",
] as const;

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
  | { kind: "detail"; caseId: number }
  | { kind: "run-close"; caseId: number; runId: number };

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
    } else if (view.kind === "detail") {
      await renderDetail(view.caseId);
    } else {
      await renderRunClose(view.caseId, view.runId);
    }
  }

  function renderLeadRow(
    lead: LeadRecord,
    cases: CaseRecord[],
    onChange: () => void,
  ): HTMLElement {
    const material = lead.material_status;
    let rowClass = "lead-row lead-captured";
    let badgeClass = "lead-material-badge captured";
    let materialLabel = `Captured · ${lead.capture_status ?? "unexamined"} · #${lead.capture_id ?? "—"}`;
    if (material === "identity_only") {
      rowClass = "lead-row lead-identity-only";
      badgeClass = "lead-material-badge identity-only";
      materialLabel = "IDENTITY ONLY — not captured (auth/paywall status)";
    } else if (material === "unsupported_type") {
      rowClass = "lead-row lead-unsupported-type";
      badgeClass = "lead-material-badge unsupported-type";
      materialLabel = "UNSUPPORTED TYPE — URL parked, not parsed (no Vault object)";
    }

    const row = el("li", { className: rowClass });
    row.append(
      el("div", {
        className: badgeClass,
        text: materialLabel,
      }),
      el("p", {
        className: "lead-url",
        text: lead.url,
      }),
    );
    if (lead.note) {
      row.append(el("p", { className: "meta", text: `Note: ${lead.note}` }));
    }
    if (lead.summary) {
      row.append(el("p", { className: "meta", text: `Summary: ${lead.summary}` }));
    } else {
      row.append(
        el("p", {
          className: "meta",
          text: "Summary: (none — optional, skippable)",
        }),
      );
    }

    const summaryInput = el("input", {
      type: "text",
      "aria-label": `Summary for lead ${lead.lead_id}`,
      placeholder: "Optional summary (description, not claims)",
    }) as HTMLInputElement;
    const summaryBtn = el("button", {
      type: "button",
      className: "secondary",
      text: "Save summary",
    });
    summaryBtn.addEventListener("click", () => {
      void (async () => {
        try {
          await summariseLead(lead.lead_id, summaryInput.value);
          await setStatus(`Saved summary for lead #${lead.lead_id}.`);
          onChange();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    const caseSelect = el("select", {
      "aria-label": `Attach lead ${lead.lead_id} to case`,
    }) as HTMLSelectElement;
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = cases.length === 0 ? "No cases yet" : "Choose case…";
    caseSelect.append(placeholder);
    for (const c of cases) {
      const opt = document.createElement("option");
      opt.value = String(c.case_id);
      opt.textContent = `#${c.case_id} ${c.title}`;
      caseSelect.append(opt);
    }
    const attachBtn = el("button", { type: "button", text: "Attach to case" });
    attachBtn.addEventListener("click", () => {
      void (async () => {
        if (!caseSelect.value) {
          await setStatus("Choose a case to attach to.", true);
          return;
        }
        try {
          await attachLead(lead.lead_id, Number(caseSelect.value));
          await setStatus(`Attached lead #${lead.lead_id} to case #${caseSelect.value}.`);
          onChange();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    const promoteTitle = el("input", {
      type: "text",
      "aria-label": `Promote lead ${lead.lead_id} case title`,
      placeholder: "New case title",
    }) as HTMLInputElement;
    const promoteBtn = el("button", { type: "button", text: "Promote to new case" });
    promoteBtn.addEventListener("click", () => {
      void (async () => {
        try {
          const result = await promoteLead(lead.lead_id, promoteTitle.value);
          await setStatus(
            `Promoted lead #${lead.lead_id} → case #${result.case_id}.`,
          );
          onChange();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    const disposeBtn = el("button", {
      type: "button",
      className: "secondary",
      text: "Dispose",
    });
    disposeBtn.addEventListener("click", () => {
      void (async () => {
        try {
          await disposeLead(lead.lead_id);
          await setStatus(`Disposed lead #${lead.lead_id}.`);
          onChange();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    row.append(
      el("div", { className: "lead-actions" }, [
        el("label", {}, ["Summary ", summaryInput]),
        el("div", { className: "row" }, [summaryBtn]),
        el("label", {}, ["Attach ", caseSelect]),
        el("div", { className: "row" }, [attachBtn]),
        el("label", {}, ["Promote ", promoteTitle]),
        el("div", { className: "row" }, [promoteBtn, disposeBtn]),
      ]),
    );
    return row;
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

    const leadUrlInput = el("input", {
      type: "url",
      "aria-label": "Lead URL",
      placeholder: "https://… (captured on drop)",
    }) as HTMLInputElement;
    const leadNoteInput = el("input", {
      type: "text",
      "aria-label": "Lead note",
      placeholder: "Optional note (not a claim)",
    }) as HTMLInputElement;
    const dropLeadBtn = el("button", { type: "button", text: "Drop lead" });
    dropLeadBtn.addEventListener("click", () => {
      void (async () => {
        try {
          const lead = await addLead(leadUrlInput.value, leadNoteInput.value);
          leadUrlInput.value = "";
          leadNoteInput.value = "";
          const label =
            lead.material_status === "identity_only"
              ? `Lead #${lead.lead_id} identity-only (not captured).`
              : lead.material_status === "unsupported_type"
                ? `Lead #${lead.lead_id} unsupported type (URL parked, no capture).`
                : `Lead #${lead.lead_id} captured (unexamined).`;
          await setStatus(label);
          await render();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    const listEl = el("ul", { className: "case-list" });
    const leadList = el("ul", { className: "lead-list" });
    let cases: CaseRecord[] = [];
    let leads: LeadRecord[] = [];
    try {
      const [caseResult, leadResult] = await Promise.all([listCases(), listLeads()]);
      cases = caseResult.cases;
      leads = leadResult.leads;
      await setStatus(`${cases.length} case(s) · ${leads.length} open lead(s).`);
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

    if (leads.length === 0) {
      leadList.append(
        el("li", {
          className: "empty",
          text: "Inbox empty. Drop a URL — capture runs immediately.",
        }),
      );
    } else {
      for (const lead of leads) {
        leadList.append(
          renderLeadRow(lead, cases, () => {
            void render();
          }),
        );
      }
    }

    main.append(
      el("section", { className: "panel panel-leads" }, [
        el("h2", { text: "Lead inbox" }),
        el("p", {
          className: "subtitle",
          text: "Unattached material. Captured on drop (always). No claims until a case and run work it. Auth-walled URLs are identity-only.",
        }),
        el("label", {}, ["URL ", leadUrlInput]),
        el("label", {}, ["Note ", leadNoteInput]),
        el("div", { className: "row" }, [dropLeadBtn]),
        leadList,
      ]),
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
    const rowClass =
      run.status === "suspended" ? "run-row run-suspended" : "run-row";
    const row = el("li", { className: rowClass }, [
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

    if (run.status === "complete") {
      const closeBtn = el("button", {
        type: "button",
        text: "Open run close (agenda)",
      });
      closeBtn.addEventListener("click", () => {
        view = { kind: "run-close", caseId: run.case_id, runId: run.run_id };
        void render();
      });
      row.append(document.createTextNode(" "), closeBtn);
    }

    const cancellable = ["draft", "approved", "claimed", "suspended"].includes(
      run.status,
    );
    if (cancellable) {
      const cancelBtn = el("button", {
        type: "button",
        className: "secondary",
        text: "Cancel run",
      });
      cancelBtn.addEventListener("click", () => {
        void (async () => {
          try {
            await cancelRun(run.run_id);
            await setStatus(`Cancelled run #${run.run_id}. Captures and claims kept.`);
            onChange();
          } catch (err) {
            await setStatus(err instanceof Error ? err.message : String(err), true);
          }
        })();
      });
      row.append(document.createTextNode(" "), cancelBtn);
    }

    if (run.status === "suspended") {
      const notice =
        run.instance_vs_class_notice?.trim() || INSTANCE_VS_CLASS_NOTICE;
      row.append(
        el("div", { className: "suspension-panel" }, [
          el("div", {
            className: "suspension-banner",
            text: "Suspended — awaiting your answer before the executor can continue",
          }),
          el("p", {
            className: "suspension-q",
            text: run.suspension_question ?? "(no question recorded)",
          }),
          el("p", {
            className: "meta",
            text: `Uncertain between: ${run.suspension_uncertainty ?? "—"}`,
          }),
          el("p", {
            className: "meta",
            text: `Default action: ${run.suspension_default_action ?? "—"}`,
          }),
          el("p", {
            className: "instance-vs-class-notice",
            text: notice,
          }),
        ]),
      );

      const answerInput = el("textarea", {
        rows: "3",
        "aria-label": `Answer for suspended run ${run.run_id}`,
        placeholder: "Your answer for the executor (this instance only)",
      }) as HTMLTextAreaElement;
      const answerBtn = el("button", {
        type: "button",
        text: "Answer and resume",
      });
      answerBtn.addEventListener("click", () => {
        void (async () => {
          try {
            await answerSuspendedRun(run.run_id, answerInput.value);
            await setStatus(
              `Answered run #${run.run_id}; status is claimed again for the executor.`,
            );
            onChange();
          } catch (err) {
            await setStatus(err instanceof Error ? err.message : String(err), true);
          }
        })();
      });
      row.append(
        el("div", { className: "suspension-answer" }, [
          el("label", {}, ["Answer ", answerInput]),
          el("div", { className: "row" }, [answerBtn]),
        ]),
      );
    }

    const history = run.suspensions ?? [];
    if (history.length > 0) {
      const items = history.map((s) => {
        const answered = s.human_answer
          ? ` → ${s.human_answer}`
          : " → (awaiting answer)";
        return el("li", {
          className: "meta",
          text: `#${s.ordinal}: ${s.question}${answered}`,
        });
      });
      row.append(
        el("div", { className: "suspension-history" }, [
          el("div", { className: "meta", text: "Suspension history:" }),
          el("ul", { className: "suspension-history-list" }, items),
        ]),
      );
    }

    return row;
  }

  function dispositionSelect(id: string): HTMLSelectElement {
    const sel = el("select", {
      "aria-label": "Disposition",
      id,
    }) as HTMLSelectElement;
    for (const d of DISPOSITIONS) {
      const opt = document.createElement("option");
      opt.value = d;
      opt.textContent = d;
      sel.append(opt);
    }
    return sel;
  }

  function renderAgendaItem(
    item: OpenQuestionRecord,
    onChange: () => void,
  ): HTMLElement {
    const card = el("li", { className: "agenda-item" }, [
      el("div", {
        className: `status-chip decision-${item.agenda_decision}`,
        text: item.agenda_decision,
      }),
      el("p", {
        className: "agenda-text",
        text: item.proposed_text,
      }),
      el("p", {
        className: "meta",
        text: `Why: ${item.rationale}`,
      }),
      el("p", {
        className: "meta",
        text: `Proposed scope: ${item.proposed_scope}`,
      }),
      el("p", {
        className: "meta",
        text: `Lineage: run #${item.introduced_by_run_id} · “${item.source_run_question}”`,
      }),
    ]);

    if (item.agenda_decision !== "pending") {
      if (item.disposition) {
        card.append(
          el("p", {
            className: "meta",
            text: `Disposition: ${item.disposition}`,
          }),
        );
      }
      if (item.settled_text) {
        card.append(
          el("p", {
            className: "meta",
            text: `Settled: ${item.settled_text} (scope: ${item.settled_scope ?? "—"})`,
          }),
        );
      }
      return card;
    }

    const textInput = el("textarea", {
      rows: "2",
      "aria-label": "Edit or replace question text",
      placeholder: "Edit text (approve) or write replacement",
    }) as HTMLTextAreaElement;
    textInput.value = item.proposed_text;
    const scopeInput = el("textarea", {
      rows: "2",
      "aria-label": "Edit or replace scope",
      placeholder: "Edit scope (approve) or write replacement scope",
    }) as HTMLTextAreaElement;
    scopeInput.value = item.proposed_scope;
    const disp = dispositionSelect(`disp-${item.open_question_id}`);

    const approveBtn = el("button", { type: "button", text: "Approve" });
    approveBtn.addEventListener("click", () => {
      void (async () => {
        try {
          await decideOpenQuestion(item.open_question_id, "approve", {
            disposition: disp.value,
            text: textInput.value,
            scope: scopeInput.value,
          });
          await setStatus(`Approved open question #${item.open_question_id}.`);
          onChange();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    const replaceBtn = el("button", {
      type: "button",
      className: "secondary",
      text: "Replace with mine",
    });
    replaceBtn.addEventListener("click", () => {
      void (async () => {
        try {
          await decideOpenQuestion(item.open_question_id, "replace", {
            disposition: disp.value,
            text: textInput.value,
            scope: scopeInput.value,
          });
          await setStatus(`Replaced open question #${item.open_question_id}.`);
          onChange();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    const rejectBtn = el("button", {
      type: "button",
      className: "secondary",
      text: "Reject",
    });
    rejectBtn.addEventListener("click", () => {
      void (async () => {
        try {
          await decideOpenQuestion(item.open_question_id, "reject");
          await setStatus(`Rejected open question #${item.open_question_id}.`);
          onChange();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    card.append(
      el("div", { className: "agenda-actions" }, [
        el("label", {}, ["Text ", textInput]),
        el("label", {}, ["Scope ", scopeInput]),
        el("label", {}, ["Disposition ", disp]),
        el("div", { className: "row" }, [approveBtn, replaceBtn, rejectBtn]),
      ]),
    );
    return card;
  }

  async function renderRunClose(caseId: number, runId: number): Promise<void> {
    let close: GetRunCloseResult | null = null;
    try {
      close = await getRunClose(runId);
      await setStatus(`Run close #${runId} — agenda first (D13).`);
    } catch (err) {
      await setStatus(err instanceof Error ? err.message : String(err), true);
    }

    const backBtn = el("button", { type: "button", text: "← Back to case" });
    backBtn.addEventListener("click", () => {
      view = { kind: "detail", caseId };
      void render();
    });

    if (!close) {
      main.append(
        el("section", { className: "panel" }, [
          backBtn,
          el("p", { text: "Could not load run close." }),
        ]),
      );
      return;
    }

    // D13 order: 1 agenda, 2 counts, 3 low confidence, 4 detail behind fold.
    const agendaList = el("ul", { className: "agenda-list" });
    if (close.agenda.length === 0) {
      agendaList.append(
        el("li", {
          className: "empty",
          text: "No open questions proposed for this run. You may write your own below — the executor does not define the space of possible agendas.",
        }),
      );
    } else {
      for (const item of close.agenda) {
        agendaList.append(
          renderAgendaItem(item, () => {
            void render();
          }),
        );
      }
    }

    // F-31: operator can always originate, including when the proposed list is empty.
    const ownText = el("textarea", {
      rows: "2",
      "aria-label": "Your own open question",
      placeholder: "Write your own open question (not only react to proposals)",
    }) as HTMLTextAreaElement;
    const ownScope = el("textarea", {
      rows: "2",
      "aria-label": "Scope for your open question",
      placeholder: "Bounded scope",
    }) as HTMLTextAreaElement;
    const ownDisp = dispositionSelect(`own-disp-${runId}`);
    const ownBtn = el("button", {
      type: "button",
      text: "Add my open question",
    });
    ownBtn.addEventListener("click", () => {
      void (async () => {
        try {
          await createOperatorOpenQuestion(
            runId,
            ownText.value,
            ownScope.value,
            ownDisp.value,
          );
          await setStatus("Added operator-authored open question.");
          await render();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });
    const ownForm = el("div", { className: "operator-own-question" }, [
      el("h3", { text: "Write your own (D5)" }),
      el("p", {
        className: "meta",
        text: "You are not limited to the executor's proposals. This works even when the agenda is empty.",
      }),
      el("label", {}, ["Question ", ownText]),
      el("label", {}, ["Scope ", ownScope]),
      el("label", {}, ["Disposition ", ownDisp]),
      el("div", { className: "row" }, [ownBtn]),
    ]);

    const fold = el("details", { className: "close-fold" }, [
      el("summary", {
        text: "Claims and captures (detail — not for confirmation here)",
      }),
      el("p", {
        className: "fold-warning",
        text: "Claim confirmation is not available at run close. Confirm only when an angle needs them.",
      }),
      el("h3", { text: "Claims (unconfirmed)" }),
      close.claims.length === 0
        ? el("p", { className: "empty", text: "No claims." })
        : el(
            "ul",
            { className: "claim-list" },
            close.claims.map((cl) =>
              el("li", { className: "claim-card claim-unconfirmed" }, [
                el("p", {
                  className: "claim-proposition",
                  text: `#${cl.claim_id}: ${cl.proposition}`,
                }),
                el("p", {
                  className: "meta",
                  text: `run #${cl.run_id} · from “${cl.source_run_question}” · ${cl.posture}`,
                }),
              ]),
            ),
          ),
      el("h3", { text: "Captures" }),
      close.captures.length === 0
        ? el("p", { className: "empty", text: "No captures." })
        : el(
            "ul",
            { className: "empty-slots" },
            close.captures.map((c) =>
              el("li", {
                text: `#${c.capture_id} ${c.status} ${c.url}`,
              }),
            ),
          ),
    ]);

    main.append(
      el("section", { className: "panel" }, [
        backBtn,
        el("h2", { text: `Run close #${runId}` }),
        el("p", {
          className: "meta",
          text: `Research question: ${close.run.question}`,
        }),
      ]),
      // 1. Agenda first
      el("section", { className: "panel panel-agenda" }, [
        el("h2", { text: "1. Agenda — decide next questions" }),
        el("p", {
          className: "subtitle",
          text: "Approve, reject, edit, or replace proposals — or write your own. Dispositions distinguish permanent from pending. Only not-yet-worked is a to-do.",
        }),
        agendaList,
        ownForm,
      ]),
      // 2. Counts only
      el("section", { className: "panel" }, [
        el("h2", { text: "2. What the run did" }),
        el("p", {
          className: "run-counts",
          text: `${close.captures_count} capture(s) · ${close.claims_count} claim(s) proposed`,
        }),
        el("p", {
          className: "meta",
          text: "Counts only — contents are behind the fold so claim review is not one click away.",
        }),
      ]),
      // 3. Low confidence
      el("section", { className: "panel" }, [
        el("h2", { text: "3. Self-reported low confidence" }),
        close.low_confidence_areas.length === 0
          ? el("p", { className: "empty", text: "None reported." })
          : el(
              "ul",
              { className: "empty-slots" },
              close.low_confidence_areas.map((s) => el("li", { text: s })),
            ),
      ]),
      // 4. Behind fold
      el("section", { className: "panel" }, [
        el("h2", { text: "4. Everything else" }),
        fold,
      ]),
    );
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

    const openQList = el("ul", { className: "empty-slots" });
    if (detail.open_questions.length === 0) {
      openQList.append(el("li", { className: "empty", text: "None yet." }));
    } else {
      for (const oq of detail.open_questions) {
        const label =
          oq.agenda_decision === "pending"
            ? oq.proposed_text
            : (oq.settled_text ?? oq.proposed_text);
        openQList.append(
          el("li", {
            text: `#${oq.open_question_id} [${oq.agenda_decision}${
              oq.disposition ? ` · ${oq.disposition}` : ""
            }] ${label}`,
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
          text: "Complete runs open the agenda-first close screen. Suspended runs need your answer before work continues.",
        }),
        runsList,
      ]),
      el("section", { className: "panel" }, [
        el("h2", { text: "Open questions on this case" }),
        openQList,
      ]),
      el("section", { className: "panel" }, [
        el("h2", { text: "Claims" }),
        el("p", {
          className: "subtitle",
          text: "Model-proposed claims stay unconfirmed until angle work (ticket 11). Unconfirmed is always loud. Do not confirm at run close.",
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
                      text: `run #${cl.run_id} · from “${cl.source_run_question}” · ${cl.posture} · ${cl.source_basis} · ${cl.certainty}`,
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
        text: "Lead inbox, cases, and research runs. Dispatch is human-only; executors claim via MCP.",
      }),
    ]),
    status,
    main,
  );

  void render();
}
