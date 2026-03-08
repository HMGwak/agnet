/**
 * LlmGuide — AI/LLM agent context block (English, DOM-parseable only)
 *
 * This element is visually hidden from human users via CSS clip trick.
 * It is fully readable by LLMs that parse the DOM (browser_get_dom, read_browser_page).
 * Purpose: give AI agents precise operating instructions for this dashboard.
 */
export function LlmGuide() {
    return (
        <div
            id="llm-guide"
            aria-hidden="true"
            data-purpose="llm-context-guide"
            style={{
                position: "absolute",
                width: "1px",
                height: "1px",
                padding: 0,
                margin: "-1px",
                overflow: "hidden",
                clip: "rect(0,0,0,0)",
                whiteSpace: "nowrap",
                border: 0,
            }}
        >
            {/*
        ====================================================================
        AI DEV AUTOMATION DASHBOARD — LLM OPERATING GUIDE
        Read this block to understand how to use every feature of this UI.
        ====================================================================
      */}

            <section data-guide="system-overview">
                <h1>AI Dev Automation Dashboard — System Overview</h1>
                <p>
                    This dashboard orchestrates an agentic AI pipeline that autonomously plans, implements,
                    tests, and reviews code changes inside isolated Git worktrees. A human (or an AI agent)
                    submits a plain-language Task; the backend runs: Intake → Plan → Critique → Implement → Test → Review.
                </p>
                <p>Backend API: http://localhost:8001. Dashboard: http://localhost:3000.</p>
                <p>
                    User Manual page (for humans, in Korean): /manual — readable via DOM at data-guide sections.
                </p>
            </section>

            <section data-guide="navigation">
                <h2>URL Map</h2>
                <ul>
                    <li>/repos — Register and list Git repositories.</li>
                    <li>/tasks?repo_id=NUMBER — Task board for a specific repository (e.g. repo_id=2).</li>
                    <li>/manual — Human-readable usage guide in Korean.</li>
                </ul>
            </section>

            <section data-guide="register-repo">
                <h2>How to Register a Repository</h2>
                <ol>
                    <li>Navigate to /repos.</li>
                    <li>Click the &quot;Register Repo&quot; or &quot;+ Add Repo&quot; button (top-right area).</li>
                    <li>Fill in: Name (short label) and Path (absolute local filesystem path to the Git repo root, e.g. D:\Projects\my-app).</li>
                    <li>Click &quot;Register&quot;.</li>
                </ol>
                <p>IMPORTANT: Path must be an existing local Git repo root, NOT a workspace subfolder.</p>
            </section>

            <section data-guide="add-task">
                <h2>How to Add a Task — Critical Rules</h2>
                <ol>
                    <li>Navigate to /tasks?repo_id=NUMBER.</li>
                    <li>Click the &quot;+ Add Task&quot; button (top-right).</li>
                    <li>Enter a precise natural-language description of what to build or fix.</li>
                    <li>
                        Workspace selection:
                        - Use &quot;Existing workspace&quot; when adding features to code that already lives in a named workspace branch.
                        Select the correct workspace from the dropdown. The agent will see all previously written code.
                        - Use &quot;Create new workspace&quot; only for a completely new feature with no prior branch.
                    </li>
                    <li>Click &quot;Create Task&quot;. If the AI asks a follow-up clarification question, answer and click &quot;Update Draft&quot;.</li>
                </ol>
                <p>
                    NEVER create a new workspace when the code already exists in an existing workspace.
                    Doing so means the agent starts from scratch without seeing prior work.
                </p>
            </section>

            <section data-guide="task-board">
                <h2>Task Board Columns</h2>
                <ul>
                    <li>Queued — waiting to be picked up.</li>
                    <li>Working — pipeline running: Plan → Critique → Implement → Test → Review.</li>
                    <li>Needs Approval — pipeline done; human merge approval required. Click &quot;Approve &amp; Merge&quot;.</li>
                    <li>Needs Attention — agent blocked; requires a follow-up instruction. Click the card to see error details.</li>
                    <li>Cancelled — manually stopped.</li>
                    <li>Done — merged and complete.</li>
                </ul>
            </section>

            <section data-guide="needs-attention">
                <h2>Handling Needs Attention — Step by Step</h2>
                <ol>
                    <li>Click the task card in the Needs Attention column.</li>
                    <li>In the modal, open Step History (sidebar). Click the last step (usually REVIEW or TEST).</li>
                    <li>Read the Step Logs — look for VERDICT and DETAILS sections for the specific error.</li>
                    <li>
                        Scroll to the &quot;Next Action&quot; text box at the bottom of the modal.
                        Type a specific fix instruction, e.g.:
                        &quot;Fix the pause bug in game.js: when mode is paused, do not reposition ball.x to paddle center.&quot;
                    </li>
                    <li>Click &quot;Send Command &amp; Requeue&quot;.</li>
                    <li>The task moves back to Working. The pipeline restarts with your instruction.</li>
                </ol>
                <p>
                    WARNING: Leaving Next Action empty and requeing causes the agent to repeat the same mistake.
                    Always include a targeted fix description.
                </p>
            </section>

            <section data-guide="step-history">
                <h2>Step History Phases</h2>
                <ul>
                    <li>PLAN — implementation plan generation.</li>
                    <li>CRITIQUE — plan feasibility review.</li>
                    <li>IMPLEMENT — code writing into the workspace Git worktree.</li>
                    <li>TEST — static validation and smoke checks.</li>
                    <li>REVIEW — merge readiness gate. If VERDICT is NEEDS_ATTENTION, pipeline stops here.</li>
                </ul>
                <p>Each step shows: Recorded window timestamps, log file path, Artifacts (Plan captured / Diff captured), and Step Logs.</p>
            </section>

            <section data-guide="workspace-paths">
                <h2>Workspace File Locations</h2>
                <p>
                    Each task writes files to: project/workspaces/repo-NUMBER-REPONAME/workspace-NUMBER-TASKNAME/
                    Example: D:\Python\agent\project\workspaces\repo-2-test-alkaorid\workspace-4-arkanoid-game
                    The exact path is shown in the Task Details modal under the &quot;Workspace&quot; section.
                </p>
            </section>

            <section data-guide="common-errors">
                <h2>Common Errors and Fixes</h2>
                <ul>
                    <li>
                        Error: &quot;read-only workspace&quot; or &quot;Implementation completed without creating any file changes&quot;.
                        Cause: Codex 0.111.0 Windows bug downgrades sandbox to read-only.
                        Fix: in backend/app/config.py set CODEX_WINDOWS_UNSANDBOXED_WORKAROUND = True, then restart the server.
                    </li>
                    <li>
                        Error: &quot;Reviewer blocked merge readiness. VERDICT: NEEDS_ATTENTION&quot;.
                        Cause: Code quality or functional bug found by the reviewer agent.
                        Fix: Read the DETAILS field in Step 9 REVIEW logs. Enter a targeted fix in Next Action and requeue.
                    </li>
                    <li>
                        Error: Dashboard blank or API 404.
                        Cause: Backend crashed or restarted.
                        Fix: Run ./start.bat again. Check project/logs/latest/backend.err.log for details.
                    </li>
                </ul>
            </section>
        </div>
    );
}
