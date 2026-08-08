import {
  addLead,
  addQuotationToShelf,
  answerSuspendedRun,
  approveRendition,
  approveRun,
  recordPublication,
  rejectRendition,
  attachLead,
  attestCoverage,
  cancelRun,
  chooseAngle,
  createAngle,
  createCase,
  createOperatorOpenQuestion,
  createPublicQuestion,
  createRun,
  decideOpenQuestion,
  DEFAULT_CAPTURE_BUDGET,
  dismissAngle,
  disposeLead,
  getCase,
  getRunClose,
  linkClaimToAngle,
  linkClaimToPublicQuestion,
  listCases,
  listLeads,
  promoteLead,
  summariseLead,
  updateRendition,
  type AngleRecord,
  type CaseRecord,
  type ClaimRecord,
  type GetCaseResult,
  type GetRunCloseResult,
  type LeadRecord,
  type LinkClaimDimensions,
  type OpenQuestionRecord,
  type PublicQuestionRecord,
  type RenditionRecord,
  type RunRecord,
} from "./api.ts";

const SOURCE_BASIS = [
  "contemporaneous_record",
  "contemporaneous_report",
  "direct_participant_recollection",
  "later_retrospective_claim",
  "scholarly_interpretation",
  "technical_inference",
  "desk_inference",
  "other",
] as const;
const CORROBORATION = [
  "unassessed",
  "single_source",
  "multi_source_dependent",
  "independently_corroborated",
  "contradicted",
] as const;
const CERTAINTY = [
  "unassessed",
  "established",
  "probable",
  "contested",
  "speculative",
  "unknown",
] as const;
const POSTURE = [
  "factual_assertion",
  "interpretation",
  "participant_account",
  "allegation",
  "disputed_assertion",
  "research_lead",
  "pattern_candidate",
] as const;
const PUBLICATION_RISK = [
  "unknown",
  "living_private",
  "public_official_official_capacity",
  "public_figure",
  "deceased",
  "institution",
  "not_applicable",
] as const;

/** D9 / F-29 — must appear on every suspended run panel. */
export const INSTANCE_VS_CLASS_NOTICE =
  "This answer resolves this run instance only. If the same uncertainty keeps recurring, amend the relevant rubric separately.";

const DISPOSITIONS = [
  "not-yet-worked",
  "unresolved-awaiting-external-development",
  "unresolved-likely-permanent",
] as const;

function selectOptions(
  values: readonly string[],
  selected?: string,
): HTMLSelectElement {
  const sel = document.createElement("select");
  for (const v of values) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    if (selected !== undefined && v === selected) opt.selected = true;
    sel.append(opt);
  }
  return sel;
}

function readDimensionsFrom(
  sourceBasis: HTMLSelectElement,
  corroboration: HTMLSelectElement,
  certainty: HTMLSelectElement,
  posture: HTMLSelectElement,
  publicationRisk: HTMLSelectElement,
  qualification: HTMLInputElement | HTMLTextAreaElement,
): LinkClaimDimensions {
  return {
    source_basis: sourceBasis.value,
    corroboration: corroboration.value,
    certainty: certainty.value,
    posture: posture.value,
    publication_risk: publicationRisk.value,
    qualification: qualification.value,
  };
}

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
      el("div", {
        className: "meta",
        text: `scope: ${run.scope}${
          run.coverage_dimension != null && run.coverage_dimension !== ""
            ? ` · ${run.coverage_dimension}`
            : ""
        }${
          run.capture_budget != null
            ? ` · budget ${run.captures_used ?? 0}/${run.capture_budget}`
            : ""
        }`,
      }),
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
    const cov = detail.coverage;
    const coverageList = el("ul", { className: "coverage-list" });
    for (const stage of cov.stages) {
      const item = el("li", { className: `coverage-stage reading-${stage.reading}` }, [
        el("span", {
          className: `status-chip coverage-chip reading-${stage.reading}`,
          text: stage.reading,
        }),
        el("strong", { text: ` ${stage.label}` }),
        el("div", {
          className: "meta",
          text: stage.signals.join(" · ") || "—",
        }),
      ]);
      if (stage.note) {
        item.append(el("p", { className: "coverage-note", text: stage.note }));
      }
      coverageList.append(item);
    }
    const foundationGate = el("p", {
      className: cov.official_foundation_complete
        ? "coverage-gate open"
        : "coverage-gate blocked",
      text: cov.official_foundation_complete
        ? "Official foundation reads complete — angle work is not blocked by the gauge."
        : "Official foundation incomplete — angle work will be refused until this reads complete (worked + operator attestation, no unexamined captures).",
    });

    const ofStage = cov.stages.find((s) => s.stage === "official_foundation");
    const deepStage = cov.stages.find((s) => s.stage === "deep_context");
    const unexaminedCaps = detail.captures.filter((c) => c.status === "unexamined");
    /** Explicit selection only (F-32) — never auto-mark-all. */
    const examinedChecks = new Map<number, HTMLInputElement>();
    const examineList = el("ul", { className: "examine-list" });
    if (unexaminedCaps.length === 0) {
      examineList.append(
        el("li", {
          className: "meta",
          text: "No unexamined captures — attestation does not need a look report.",
        }),
      );
    } else {
      examineList.append(
        el("li", {
          className: "meta",
          text: "Unexamined captures — check only those you looked at and found nothing worth claiming (required before attest):",
        }),
      );
      for (const cap of unexaminedCaps) {
        const cb = el("input", {
          type: "checkbox",
          "aria-label": `Examined capture ${cap.capture_id}`,
        }) as HTMLInputElement;
        examinedChecks.set(cap.capture_id, cb);
        examineList.append(
          el("li", { className: "examine-item" }, [
            cb,
            document.createTextNode(
              ` #${cap.capture_id} ${cap.status} ${cap.url}`,
            ),
          ]),
        );
      }
    }

    function selectedExaminedIds(): number[] {
      const ids: number[] = [];
      for (const [id, cb] of examinedChecks) {
        if (cb.checked) ids.push(id);
      }
      return ids;
    }

    const attestRow = el("div", { className: "attest-actions" });
    const pqStage = cov.stages.find((s) => s.stage === "public_question");
    const edStage = cov.stages.find((s) => s.stage === "editorial_development");
    const attestableWorked = [
      ofStage,
      deepStage,
      pqStage,
      edStage,
    ].filter((s) => s?.reading === "worked");
    if (attestableWorked.length > 0) {
      attestRow.append(examineList);
    }
    const attestButtons: Array<{ stage: string; label: string }> = [
      { stage: "official_foundation", label: "Attest official foundation complete" },
      { stage: "deep_context", label: "Attest deep context complete" },
      { stage: "public_question", label: "Attest public question complete" },
      {
        stage: "editorial_development",
        label: "Attest editorial development complete",
      },
    ];
    for (const { stage, label } of attestButtons) {
      const stageReading = cov.stages.find((s) => s.stage === stage);
      if (stageReading?.reading !== "worked") continue;
      const btn = el("button", {
        type: "button",
        className: stage === "official_foundation" ? "" : "secondary",
        text: label,
      });
      btn.addEventListener("click", () => {
        void (async () => {
          try {
            const r = await attestCoverage(caseId, stage, {
              examinedCaptureIds: selectedExaminedIds(),
            });
            await setStatus(
              `Attested ${stage} → ${r.reading}` +
                (r.captures_marked_examined
                  ? ` (marked ${r.captures_marked_examined} examined).`
                  : "."),
            );
            await render();
          } catch (err) {
            await setStatus(err instanceof Error ? err.message : String(err), true);
          }
        })();
      });
      attestRow.append(el("div", { className: "row" }, [btn]));
    }

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
    const dimSelect = el("select", {
      "aria-label": "Coverage dimension for this run",
    }) as HTMLSelectElement;
    for (const [id, label] of [
      ["official_foundation", "Official foundation"],
      ["public_question", "The public question"],
      ["deep_context", "Deep context"],
      ["story_intelligence", "Story intelligence"],
      ["editorial_development", "Editorial development"],
      ["composition", "Composition"],
    ] as const) {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = label;
      dimSelect.append(opt);
    }
    // F-53 / F-44 shape: service has capture_budget; form must expose what the
    // operator spends. Default matches backend DEFAULT_CAPTURE_BUDGET.
    const budgetInput = el("input", {
      type: "number",
      min: "1",
      step: "1",
      value: String(DEFAULT_CAPTURE_BUDGET),
      "aria-label": "Capture budget for this run",
    }) as HTMLInputElement;

    const dispatchBtn = el("button", {
      type: "button",
      text: "Create run (draft)",
    });
    dispatchBtn.addEventListener("click", () => {
      void (async () => {
        try {
          const budgetRaw = budgetInput.value.trim();
          const budget = budgetRaw === "" ? DEFAULT_CAPTURE_BUDGET : Number(budgetRaw);
          if (!Number.isFinite(budget) || budget < 1 || !Number.isInteger(budget)) {
            await setStatus(
              "Capture budget must be a whole number ≥ 1 (backend refuses otherwise).",
              true,
            );
            return;
          }
          const run = await createRun(
            caseId,
            questionInput.value,
            scopeInput.value,
            dimSelect.value,
            budget,
          );
          questionInput.value = "";
          scopeInput.value = "";
          budgetInput.value = String(DEFAULT_CAPTURE_BUDGET);
          await setStatus(
            `Created run #${run.run_id} as draft (${run.coverage_dimension}, budget ${run.capture_budget ?? budget}).`,
          );
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
      el("section", { className: "panel panel-coverage" }, [
        el("h2", { text: "Coverage gauge" }),
        el("p", { className: "subtitle", text: cov.banner }),
        foundationGate,
        coverageList,
        attestRow,
      ]),
      el("section", { className: "panel" }, [
        el("h2", { text: "Dispatch research run" }),
        el("p", {
          className: "subtitle",
          text: "Creates a draft. Set the coverage dimension this run targets and the capture budget (operator only — D8: the executor cannot overspend because it is not the one spending). Approve to make it claimable.",
        }),
        el("label", {}, ["Question ", questionInput]),
        el("label", {}, ["Scope ", scopeInput]),
        el("label", {}, ["Coverage dimension ", dimSelect]),
        el("label", {}, [
          "Capture budget ",
          budgetInput,
          el("span", {
            className: "meta",
            text: ` (default ${DEFAULT_CAPTURE_BUDGET}; minimum 1)`,
          }),
        ]),
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
          text: "Model-proposed claims stay unconfirmed until linked into an angle. Linking is confirmation at use (ADR 2). Unconfirmed is always loud.",
        }),
        detail.claims.length === 0
          ? el("p", { className: "empty", text: "No claims yet." })
          : el(
              "ul",
              { className: "claim-list" },
              detail.claims.map((cl) => claimCard(cl)),
            ),
      ]),
      buildAngleRoomPanel(caseId, detail, () => {
        void render();
      }),
      el("section", { className: "panel" }, [
        el("h2", { text: "Captures on this case" }),
        detail.captures.length === 0
          ? el("p", { className: "empty", text: "No captures yet." })
          : el(
              "ul",
              { className: "empty-slots" },
              detail.captures.map((cap) =>
                el("li", {
                  text: `#${cap.capture_id} ${cap.status} ${cap.url}`,
                }),
              ),
            ),
      ]),
      el("section", { className: "panel" }, [
        el("h2", { text: "Renditions" }),
        el("p", {
          className: "subtitle",
          text: "Threads proposed by the executor. Clear exact content before publish — edit first if needed; approval binds the ordered text as reviewed.",
        }),
        detail.renditions.length === 0
          ? el("p", { className: "empty", text: "No renditions yet." })
          : el(
              "div",
              { className: "rendition-list" },
              detail.renditions.map((ren) =>
                renditionCard(ren, () => {
                  void render();
                }),
              ),
            ),
      ]),
    );
  }

  function renditionStandingLabel(ren: RenditionRecord): string {
    if (ren.approval_stands) {
      return "approval stands (content matches clearance)";
    }
    if (ren.approval_invalidation) {
      return `approval invalidated — ${ren.approval_invalidation.detail}`;
    }
    if (ren.status === "cleared") {
      return "cleared status but standing unknown";
    }
    return "not cleared";
  }

  function renditionCard(ren: RenditionRecord, refresh: () => void): HTMLElement {
    const editable = ren.status === "draft" || ren.status === "cleared";
    const standing = el("p", {
      className: ren.approval_stands
        ? "meta approval-stands"
        : ren.approval_invalidation
          ? "meta approval-invalidated"
          : "meta",
      text: renditionStandingLabel(ren),
    });
    const header = el("div", { className: "rendition-header" }, [
      el("h3", {
        text: `#${ren.rendition_id} · ${ren.platform}/${ren.format} · ${ren.status}`,
      }),
      el("p", {
        className: "meta",
        text: `angle #${ren.angle_id} · run #${ren.run_id} · rubric ${ren.rubric_version} · ${ren.created_at}`,
      }),
      standing,
    ]);

    const bodyAreas: HTMLTextAreaElement[] = [];
    const unitEditors =
      ren.units.length === 0
        ? el("p", { className: "empty", text: "No units." })
        : el(
            "ol",
            { className: "rendition-thread" },
            ren.units.map((u) => {
              const area = document.createElement("textarea");
              area.className = "rendition-unit-edit";
              area.rows = 4;
              area.value = u.body;
              area.disabled = !editable;
              bodyAreas.push(area);
              return el("li", { className: "rendition-unit" }, [
                area,
                el("p", {
                  className: "meta",
                  text:
                    u.claim_ids.length === 0
                      ? "cites no claims"
                      : `cites claim(s): ${u.claim_ids.join(", ")}`,
                }),
              ]);
            }),
          );

    const actions = el("div", { className: "row gap" });
    if (editable) {
      const saveBtn = el("button", {
        type: "button",
        text: "Save unit text",
      }) as HTMLButtonElement;
      saveBtn.addEventListener("click", () => {
        void (async () => {
          try {
            await updateRendition(
              ren.rendition_id,
              ren.units.map((u, i) => ({
                body: bodyAreas[i]?.value ?? u.body,
                claim_ids: u.claim_ids,
              })),
            );
            await setStatus(`Saved units on rendition #${ren.rendition_id}.`);
            refresh();
          } catch (err) {
            await setStatus(
              err instanceof Error ? err.message : String(err),
              true,
            );
          }
        })();
      });
      const clearBtn = el("button", {
        type: "button",
        text: ren.approval_stands
          ? "Re-clear current text"
          : "Clear exact content",
      }) as HTMLButtonElement;
      clearBtn.addEventListener("click", () => {
        void (async () => {
          try {
            // Persist editor text first so clearance binds what the operator sees.
            const dirty = ren.units.some(
              (u, i) => (bodyAreas[i]?.value ?? u.body) !== u.body,
            );
            if (dirty) {
              await updateRendition(
                ren.rendition_id,
                ren.units.map((u, i) => ({
                  body: bodyAreas[i]?.value ?? u.body,
                  claim_ids: u.claim_ids,
                })),
              );
            }
            const cleared = await approveRendition(ren.rendition_id);
            await setStatus(
              `Cleared rendition #${cleared.rendition_id} (approval #${cleared.current_approval_id}).`,
            );
            refresh();
          } catch (err) {
            await setStatus(
              err instanceof Error ? err.message : String(err),
              true,
            );
          }
        })();
      });
      actions.append(saveBtn, clearBtn);

      const rejectBtn = el("button", {
        type: "button",
        text: "Reject rendition",
      }) as HTMLButtonElement;
      rejectBtn.addEventListener("click", () => {
        void (async () => {
          try {
            await rejectRendition(ren.rendition_id);
            await setStatus(`Rejected rendition #${ren.rendition_id}.`);
            refresh();
          } catch (err) {
            await setStatus(
              err instanceof Error ? err.message : String(err),
              true,
            );
          }
        })();
      });
      actions.append(rejectBtn);
    }

    const history =
      (ren.approvals?.length ?? 0) === 0
        ? el("p", { className: "meta", text: "No clearance records yet." })
        : el(
            "ul",
            { className: "approval-history" },
            (ren.approvals ?? []).map((a) =>
              el("li", {
                className: "meta",
                text: `clearance #${a.sequence} by ${a.actor} at ${a.approved_at} (${a.units.length} unit(s))`,
              }),
            ),
          );

    // Publication: operator posts manually, then pastes back what actually went out.
    // Never invent external_post_id or canonical_url — empty fields the operator must fill.
    let pubBlock: HTMLElement;
    if (ren.publication != null) {
      pubBlock = el("div", { className: "publication-record" }, [
        el("p", {
          className: "meta",
          text: `Publication #${ren.publication.publication_id} authorized by clearance #${ren.publication.approval_id} · recorded ${ren.publication.recorded_at} by ${ren.publication.actor}`,
        }),
        el(
          "ul",
          { className: "empty-slots" },
          ren.publication.units.map((u) =>
            el("li", {
              text: `ord ${u.unit_ordinal}: ${u.platform} ${u.external_post_id} · ${u.canonical_url} · ${u.published_at} · ${u.verification_state}`,
            }),
          ),
        ),
      ]);
    } else if (ren.approval_stands && ren.status !== "published") {
      const defaultPublishedAt = new Date().toISOString();
      type PubFields = {
        externalId: HTMLInputElement;
        url: HTMLInputElement;
        publishedAt: HTMLInputElement;
        verification: HTMLSelectElement;
      };
      const fields: PubFields[] = [];
      const rows = el(
        "ol",
        { className: "publication-paste-form" },
        ren.units.map((u) => {
          const externalId = el("input", {
            type: "text",
            placeholder: "External post id (required — paste from platform)",
            "aria-label": `Unit ${u.ordinal} external post id`,
            autocomplete: "off",
          }) as HTMLInputElement;
          externalId.value = "";
          const url = el("input", {
            type: "url",
            placeholder: "Canonical URL (required — paste actual link)",
            "aria-label": `Unit ${u.ordinal} canonical URL`,
            autocomplete: "off",
          }) as HTMLInputElement;
          url.value = "";
          const publishedAt = el("input", {
            type: "text",
            "aria-label": `Unit ${u.ordinal} published time`,
          }) as HTMLInputElement;
          publishedAt.value = defaultPublishedAt;
          const verification = el("select", {
            "aria-label": `Unit ${u.ordinal} verification state`,
          }) as HTMLSelectElement;
          for (const v of ["unverified", "verified", "failed"] as const) {
            const opt = document.createElement("option");
            opt.value = v;
            opt.textContent = v;
            if (v === "unverified") opt.selected = true;
            verification.append(opt);
          }
          fields.push({ externalId, url, publishedAt, verification });
          return el("li", { className: "publication-unit-fields" }, [
            el("p", {
              className: "meta",
              text: `Unit ${u.ordinal} — paste what actually went out (not invented)`,
            }),
            el("label", { text: "External post id" }),
            externalId,
            el("label", { text: "Canonical URL" }),
            url,
            el("label", { text: "Published time (ISO-8601, editable)" }),
            publishedAt,
            el("label", { text: "Verification state" }),
            verification,
          ]);
        }),
      );
      const submitBtn = el("button", {
        type: "button",
        text: "Record publication (complete set required)",
      }) as HTMLButtonElement;
      submitBtn.addEventListener("click", () => {
        void (async () => {
          try {
            for (let i = 0; i < fields.length; i++) {
              const f = fields[i]!;
              if (!f.externalId.value.trim() || !f.url.value.trim()) {
                await setStatus(
                  `Unit ${ren.units[i]!.ordinal}: external post id and canonical URL are required. Paste what the platform actually assigned — do not invent them.`,
                  true,
                );
                return;
              }
              if (!f.publishedAt.value.trim()) {
                await setStatus(
                  `Unit ${ren.units[i]!.ordinal}: published time is required.`,
                  true,
                );
                return;
              }
            }
            // Complete set only — every cleared unit must be recorded. Partial
            // threads (3 of 4 posted) are F-64: new rendition, not a partial set.
            const published = await recordPublication(
              ren.rendition_id,
              ren.units.map((u, i) => ({
                ordinal: u.ordinal,
                platform: ren.platform,
                external_post_id: fields[i]!.externalId.value.trim(),
                canonical_url: fields[i]!.url.value.trim(),
                published_at: fields[i]!.publishedAt.value.trim(),
                verification_state: fields[i]!.verification.value,
              })),
            );
            await setStatus(
              `Recorded publication for #${published.rendition_id} under approval #${published.publication?.approval_id}.`,
            );
            refresh();
          } catch (err) {
            await setStatus(
              err instanceof Error ? err.message : String(err),
              true,
            );
          }
        })();
      });
      pubBlock = el("div", { className: "publication-form" }, [
        el("p", {
          className: "subtitle",
          text: "Post manually on the platform, then paste back the real post id, URL, and time for every unit. Empty id/URL fields are required — the form will not invent them. Complete set only.",
        }),
        rows,
        submitBtn,
      ]);
    } else {
      pubBlock = el("p", {
        className: "meta",
        text: ren.approval_stands
          ? "No publication recorded."
          : "Clearance must stand before publication can be recorded.",
      });
    }

    return el("article", { className: "rendition-card" }, [
      header,
      unitEditors,
      actions,
      el("h4", { text: "Clearance history" }),
      history,
      el("h4", { text: "Publication" }),
      pubBlock,
    ]);
  }

  function claimCard(cl: ClaimRecord): HTMLElement {
    const isUnconfirmed = cl.confirmation_status === "unconfirmed";
    const confirmMeta =
      cl.confirmed_at != null && cl.confirmed_at !== ""
        ? ` · confirmed ${cl.confirmed_at}`
        : "";
    return el(
      "li",
      {
        className: isUnconfirmed ? "claim-card claim-unconfirmed" : "claim-card",
      },
      [
        el("div", { className: "claim-banner" }, [
          el("span", {
            className: "claim-status-badge",
            text: isUnconfirmed
              ? "⚠ UNCONFIRMED — model-proposed, not human-reviewed"
              : "CONFIRMED",
          }),
        ]),
        el("p", {
          className: "claim-proposition",
          text: `#${cl.claim_id}: ${cl.proposition}`,
        }),
        el("p", {
          className: "meta",
          text: `run #${cl.run_id} · from “${cl.source_run_question}” · ${cl.posture} · ${cl.source_basis} · ${cl.certainty} · ${cl.publication_risk}${confirmMeta}`,
        }),
      ],
    );
  }

  function buildAngleRoomPanel(
    caseId: number,
    detail: GetCaseResult,
    refresh: () => void,
  ): HTMLElement {
    const foundationOk = detail.coverage.official_foundation_complete;
    const gateNote = foundationOk
      ? "Official foundation complete — Angle Room is open."
      : "Official foundation incomplete — every angle/confirmation path will refuse until it reads complete.";

    // --- Create angle ---
    const angleTitle = el("input", {
      type: "text",
      placeholder: "Angle title",
      "aria-label": "Angle title",
    }) as HTMLInputElement;
    const angleSummary = el("textarea", {
      placeholder: "Summary (optional)",
      "aria-label": "Angle summary",
      rows: "2",
    }) as HTMLTextAreaElement;
    const createAngleBtn = el("button", {
      type: "button",
      text: "Create angle",
    });
    createAngleBtn.addEventListener("click", () => {
      void (async () => {
        try {
          const a = await createAngle(
            caseId,
            angleTitle.value,
            angleSummary.value,
          );
          await setStatus(`Created angle #${a.angle_id} (${a.status}).`);
          refresh();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    // --- Public question ---
    const pqText = el("input", {
      type: "text",
      placeholder: "What are people asking?",
      "aria-label": "Public question text",
    }) as HTMLInputElement;
    const pqVersion = el("input", {
      type: "text",
      placeholder: "Circulating version",
      "aria-label": "Circulating version",
    }) as HTMLInputElement;
    const pqWhere = el("input", {
      type: "text",
      placeholder: "Where asked",
      "aria-label": "Where asked",
    }) as HTMLInputElement;
    const pqOrigin = el("input", {
      type: "text",
      placeholder: "Origin",
      "aria-label": "Origin",
    }) as HTMLInputElement;
    const pqBtn = el("button", {
      type: "button",
      text: "Record public question",
    });
    pqBtn.addEventListener("click", () => {
      void (async () => {
        try {
          const pq = await createPublicQuestion(caseId, {
            question_text: pqText.value,
            circulating_version: pqVersion.value,
            where_asked: pqWhere.value,
            origin: pqOrigin.value,
          });
          await setStatus(`Recorded public question #${pq.public_question_id}.`);
          refresh();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    const angleList =
      detail.angles.length === 0
        ? el("p", { className: "empty", text: "No angles yet." })
        : el(
            "ul",
            { className: "angle-list" },
            detail.angles.map((ang) =>
              angleCard(ang, detail.claims, foundationOk, refresh),
            ),
          );

    const pqList =
      detail.public_questions.length === 0
        ? el("p", {
            className: "empty",
            text: "No public questions recorded.",
          })
        : el(
            "ul",
            { className: "angle-list" },
            detail.public_questions.map((q) =>
              publicQuestionCard(q, detail.claims, foundationOk, refresh),
            ),
          );

    const shelfList =
      detail.quotation_shelf.length === 0
        ? el("p", {
            className: "empty",
            text: "Shelf is empty. Select a quote binding with speaker and attribution.",
          })
        : el(
            "ul",
            { className: "quotation-shelf" },
            detail.quotation_shelf.map((item) =>
              el("li", {
                className: "quotation-item",
                text: `${item.speaker} (${item.attribution_frame}): “${item.quoted_text}” · claim #${item.claim_id} · ${item.locator}`,
              }),
            ),
          );

    // Add-to-shelf form: pick a claim binding + speaker + frame
    const shelfClaimSelect = document.createElement("select");
    shelfClaimSelect.setAttribute("aria-label", "Claim for quotation shelf");
    const claimsWithQuotes = detail.claims.filter(
      (c) => c.quote_bindings.length > 0,
    );
    if (claimsWithQuotes.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No claims with quote bindings";
      shelfClaimSelect.append(opt);
      shelfClaimSelect.disabled = true;
    } else {
      for (const c of claimsWithQuotes) {
        for (const qb of c.quote_bindings) {
          const opt = document.createElement("option");
          opt.value = `${c.claim_id}|${qb.capture_id}|${qb.locator}|${qb.quoted_text}`;
          opt.textContent = `#${c.claim_id} ${qb.locator}: ${qb.quoted_text.slice(0, 50)}`;
          shelfClaimSelect.append(opt);
        }
      }
    }
    const shelfSpeaker = el("input", {
      type: "text",
      placeholder: "Speaker",
      "aria-label": "Speaker",
    }) as HTMLInputElement;
    const shelfFrame = el("input", {
      type: "text",
      placeholder: "Attribution frame",
      "aria-label": "Attribution frame",
    }) as HTMLInputElement;
    const shelfSb = selectOptions(SOURCE_BASIS, "contemporaneous_report");
    const shelfCor = selectOptions(CORROBORATION, "single_source");
    const shelfCert = selectOptions(CERTAINTY, "probable");
    const shelfPos = selectOptions(POSTURE, "factual_assertion");
    const shelfPr = selectOptions(PUBLICATION_RISK, "not_applicable");
    const shelfQual = el("input", {
      type: "text",
      placeholder: "Qualification if needed",
      "aria-label": "Qualification for shelf confirm",
    }) as HTMLInputElement;
    const shelfBtn = el("button", {
      type: "button",
      text: "Add to quotation shelf",
    });
    shelfBtn.disabled = shelfClaimSelect.disabled || !foundationOk;
    shelfBtn.addEventListener("click", () => {
      void (async () => {
        const raw = shelfClaimSelect.value;
        if (!raw) return;
        const [claimIdS, capIdS, locator, ...textParts] = raw.split("|");
        const quoted_text = textParts.join("|");
        const claimId = Number(claimIdS);
        const capture_id = Number(capIdS);
        const cl = detail.claims.find((c) => c.claim_id === claimId);
        try {
          const dims =
            cl?.confirmation_status === "confirmed"
              ? null
              : readDimensionsFrom(
                  shelfSb,
                  shelfCor,
                  shelfCert,
                  shelfPos,
                  shelfPr,
                  shelfQual,
                );
          const item = await addQuotationToShelf({
            case_id: caseId,
            claim_id: claimId,
            capture_id,
            locator,
            quoted_text,
            speaker: shelfSpeaker.value,
            attribution_frame: shelfFrame.value,
            dimensions: dims,
          });
          await setStatus(
            `Added shelf entry #${item.shelf_entry_id}: ${item.speaker}.`,
          );
          refresh();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    return el("section", { className: "panel panel-angle-room" }, [
      el("h2", { text: "Angle Room" }),
      el("p", { className: "subtitle", text: gateNote }),
      el("h3", { text: "Angles" }),
      angleList,
      el("div", { className: "angle-create" }, [
        el("h3", { text: "Create angle" }),
        el("label", {}, ["Title ", angleTitle]),
        el("label", {}, ["Summary ", angleSummary]),
        el("div", { className: "row" }, [createAngleBtn]),
      ]),
      el("h3", { text: "Public questions" }),
      el("p", {
        className: "subtitle",
        text: "Discourse observations — not claims. Must link ≥1 claim to count as worked coverage (VISION §7).",
      }),
      pqList,
      el("div", { className: "public-question-create" }, [
        el("label", {}, ["Question ", pqText]),
        el("label", {}, ["Circulating version ", pqVersion]),
        el("label", {}, ["Where asked ", pqWhere]),
        el("label", {}, ["Origin ", pqOrigin]),
        el("div", { className: "row" }, [pqBtn]),
      ]),
      el("h3", { text: "Quotation shelf" }),
      el("p", {
        className: "subtitle",
        text: "Operator selects the strongest quotations — not an automatic dump of every binding.",
      }),
      shelfList,
      el("div", { className: "shelf-add" }, [
        el("label", {}, ["Binding ", shelfClaimSelect]),
        el("label", {}, ["Speaker ", shelfSpeaker]),
        el("label", {}, ["Attribution frame ", shelfFrame]),
        el("div", { className: "dimension-grid" }, [
          el("label", {}, ["Source basis ", shelfSb]),
          el("label", {}, ["Corroboration ", shelfCor]),
          el("label", {}, ["Certainty ", shelfCert]),
          el("label", {}, ["Posture ", shelfPos]),
          el("label", {}, ["Publication risk ", shelfPr]),
          el("label", {}, ["Qualification ", shelfQual]),
        ]),
        el("div", { className: "row" }, [shelfBtn]),
      ]),
    ]);
  }

  function publicQuestionCard(
    q: PublicQuestionRecord,
    claims: ClaimRecord[],
    foundationOk: boolean,
    refresh: () => void,
  ): HTMLElement {
    const claimSelect = document.createElement("select");
    claimSelect.setAttribute(
      "aria-label",
      `Claim to link to public question ${q.public_question_id}`,
    );
    const unlinked = claims.filter((c) => !q.claim_ids.includes(c.claim_id));
    if (unlinked.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No unlinked claims";
      claimSelect.append(opt);
      claimSelect.disabled = true;
    } else {
      for (const c of unlinked) {
        const opt = document.createElement("option");
        opt.value = String(c.claim_id);
        opt.textContent = `#${c.claim_id} ${c.confirmation_status}: ${c.proposition.slice(0, 50)}`;
        claimSelect.append(opt);
      }
    }
    const sb = selectOptions(SOURCE_BASIS, "contemporaneous_report");
    const cor = selectOptions(CORROBORATION, "single_source");
    const cert = selectOptions(CERTAINTY, "probable");
    const pos = selectOptions(POSTURE, "factual_assertion");
    const pr = selectOptions(PUBLICATION_RISK, "not_applicable");
    const qual = el("input", {
      type: "text",
      placeholder: "Qualification if needed",
      "aria-label": "Qualification",
    }) as HTMLInputElement;
    const prefill = () => {
      const id = Number(claimSelect.value);
      const cl = claims.find((c) => c.claim_id === id);
      if (!cl) return;
      sb.value = cl.source_basis;
      cor.value = cl.corroboration;
      cert.value = cl.certainty;
      pos.value = cl.posture;
      pr.value = cl.publication_risk;
      qual.value = cl.qualification;
    };
    claimSelect.addEventListener("change", prefill);
    if (!claimSelect.disabled) prefill();

    const linkBtn = el("button", {
      type: "button",
      text: "Link claim (confirm)",
    });
    linkBtn.disabled = claimSelect.disabled || !foundationOk;
    linkBtn.addEventListener("click", () => {
      void (async () => {
        const claimId = Number(claimSelect.value);
        if (!Number.isFinite(claimId) || claimId <= 0) return;
        const cl = claims.find((c) => c.claim_id === claimId);
        try {
          const dims =
            cl?.confirmation_status === "confirmed"
              ? null
              : readDimensionsFrom(sb, cor, cert, pos, pr, qual);
          await linkClaimToPublicQuestion(q.public_question_id, claimId, dims);
          await setStatus(
            `Linked claim #${claimId} to public question #${q.public_question_id}.`,
          );
          refresh();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    return el("li", { className: "angle-card" }, [
      el("strong", {
        text: `#${q.public_question_id}: ${q.question_text}`,
      }),
      el("p", {
        className: "meta",
        text: `version “${q.circulating_version}” · ${q.where_asked} · from ${q.origin} · claims: [${q.claim_ids.join(", ")}]`,
      }),
      el("div", { className: "angle-actions" }, [
        el("label", {}, ["Claim ", claimSelect]),
        el("div", { className: "dimension-grid" }, [
          el("label", {}, ["Source basis ", sb]),
          el("label", {}, ["Corroboration ", cor]),
          el("label", {}, ["Certainty ", cert]),
          el("label", {}, ["Posture ", pos]),
          el("label", {}, ["Publication risk ", pr]),
          el("label", {}, ["Qualification ", qual]),
        ]),
        el("div", { className: "row" }, [linkBtn]),
      ]),
    ]);
  }

  function angleCard(
    ang: AngleRecord,
    claims: ClaimRecord[],
    foundationOk: boolean,
    refresh: () => void,
  ): HTMLElement {
    const statusChip = el("span", {
      className: `status-chip angle-status-${ang.status}`,
      text: ang.status,
    });
    const body: (Node | string)[] = [
      el("div", { className: "angle-header" }, [
        el("strong", { text: `#${ang.angle_id}: ${ang.title}` }),
        statusChip,
      ]),
      el("p", {
        className: "meta",
        text:
          ang.summary.trim() === ""
            ? `claims: [${ang.claim_ids.join(", ")}]`
            : `${ang.summary} · claims: [${ang.claim_ids.join(", ")}]`,
      }),
    ];

    if (ang.status === "dismissed") {
      body.push(
        el("p", {
          className: "dismissal-reason",
          text: `Dismissed${ang.dismissed_at ? ` ${ang.dismissed_at}` : ""}: ${ang.dismissal_reason ?? ""}`,
        }),
      );
      return el("li", { className: "angle-card angle-dismissed" }, body);
    }

    // Link claim + confirm dimensions
    const claimSelect = document.createElement("select");
    claimSelect.setAttribute("aria-label", `Claim to link to angle ${ang.angle_id}`);
    const unlinked = claims.filter((c) => !ang.claim_ids.includes(c.claim_id));
    if (unlinked.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No unlinked claims";
      claimSelect.append(opt);
      claimSelect.disabled = true;
    } else {
      for (const c of unlinked) {
        const opt = document.createElement("option");
        opt.value = String(c.claim_id);
        opt.textContent = `#${c.claim_id} ${c.confirmation_status}: ${c.proposition.slice(0, 60)}`;
        claimSelect.append(opt);
      }
    }

    const sb = selectOptions(SOURCE_BASIS, "contemporaneous_report");
    const cor = selectOptions(CORROBORATION, "single_source");
    const cert = selectOptions(CERTAINTY, "probable");
    const pos = selectOptions(POSTURE, "factual_assertion");
    const pr = selectOptions(PUBLICATION_RISK, "not_applicable");
    const qual = el("input", {
      type: "text",
      placeholder: "Qualification (if required by posture)",
      "aria-label": "Qualification",
    }) as HTMLInputElement;

    // Prefill from selected claim when selection changes
    const prefillFromClaim = () => {
      const id = Number(claimSelect.value);
      const cl = claims.find((c) => c.claim_id === id);
      if (!cl) return;
      sb.value = cl.source_basis;
      cor.value = cl.corroboration;
      cert.value = cl.certainty;
      pos.value = cl.posture;
      pr.value = cl.publication_risk;
      qual.value = cl.qualification;
    };
    claimSelect.addEventListener("change", prefillFromClaim);
    if (!claimSelect.disabled) prefillFromClaim();

    const linkBtn = el("button", {
      type: "button",
      text: "Link claim (confirm dimensions)",
    });
    linkBtn.disabled = claimSelect.disabled || !foundationOk;
    linkBtn.addEventListener("click", () => {
      void (async () => {
        const claimId = Number(claimSelect.value);
        if (!Number.isFinite(claimId) || claimId <= 0) return;
        const cl = claims.find((c) => c.claim_id === claimId);
        try {
          const dims =
            cl?.confirmation_status === "confirmed"
              ? null
              : readDimensionsFrom(sb, cor, cert, pos, pr, qual);
          const updated = await linkClaimToAngle(ang.angle_id, claimId, dims);
          await setStatus(
            `Linked claim #${claimId} to angle #${updated.angle_id}` +
              (cl?.confirmation_status === "unconfirmed"
                ? " (claim confirmed)."
                : "."),
          );
          refresh();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    const chooseBtn = el("button", { type: "button", text: "Choose this angle" });
    chooseBtn.disabled = !foundationOk || ang.status === "chosen";
    chooseBtn.addEventListener("click", () => {
      void (async () => {
        try {
          const r = await chooseAngle(ang.angle_id);
          await setStatus(`Chose angle #${r.angle_id}.`);
          refresh();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    const dismissReason = el("input", {
      type: "text",
      placeholder: "Dismissal reason (required)",
      "aria-label": "Dismissal reason",
    }) as HTMLInputElement;
    const dismissBtn = el("button", {
      type: "button",
      text: "Dismiss angle",
    });
    dismissBtn.disabled = !foundationOk;
    dismissBtn.addEventListener("click", () => {
      void (async () => {
        try {
          const r = await dismissAngle(ang.angle_id, dismissReason.value);
          await setStatus(
            `Dismissed angle #${r.angle_id}: ${r.dismissal_reason ?? ""}`,
          );
          refresh();
        } catch (err) {
          await setStatus(err instanceof Error ? err.message : String(err), true);
        }
      })();
    });

    body.push(
      el("div", { className: "angle-actions" }, [
        el("label", {}, ["Claim ", claimSelect]),
        el("div", { className: "dimension-grid" }, [
          el("label", {}, ["Source basis ", sb]),
          el("label", {}, ["Corroboration ", cor]),
          el("label", {}, ["Certainty ", cert]),
          el("label", {}, ["Posture ", pos]),
          el("label", {}, ["Publication risk ", pr]),
          el("label", {}, ["Qualification ", qual]),
        ]),
        el("div", { className: "row" }, [linkBtn, chooseBtn]),
        el("div", { className: "row" }, [dismissReason, dismissBtn]),
      ]),
    );

    return el(
      "li",
      {
        className:
          ang.status === "chosen" ? "angle-card angle-chosen" : "angle-card",
      },
      body,
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
