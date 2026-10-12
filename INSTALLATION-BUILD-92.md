# Provider, model and localhost selectors — build 92

OpenCode chat has separate Provider and Model selectors. Provider groups are model developers supplied through OpenCode Go; every group keeps the existing Go credential and endpoint. Independent direct API connections are not implied. Both lists sort A–Z without putting available models first. Distinct model IDs with the same display name remain separate, with prices and IDs visible. Selection is saved per conversation and applies to the next message without changing the task session/project.

The session menu has spaced actions and an X in the corner. Changed files replaces Review changes and appears only inside a saved task, with a short explanation.

CLI · localhost is an active, persistent selection in the session list and chat connection selector. Health comes from the actual local OpenCode engine. All sessions currently come from that configured engine; no cloud execution mode is fabricated.

Qoder's original model picker and the Offline model dropdown are alphabetized. Existing IDs, prices, comparable variants and permissions are preserved.

Signed output: /sdcard/Download/Qoder-Share-Sessions-92.apk. Existing sessions and account credentials are retained.

Live execution verification found volatile project-only registration. Model definitions are now persisted while retaining existing global settings, then applied through the global config endpoint so task instances can resolve the same models shown in the catalogue. A live Go-backed CLI request returned READY.
