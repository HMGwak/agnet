/**
 * LlmGuide — LLM/AI 에이전트 전용 설명 블록
 *
 * 이 컴포넌트는 일반 사용자 화면에는 보이지 않지만,
 * DOM을 파싱하는 LLM(예: browser_subagent, read_browser_page)이
 * 대시보드 조작 방법을 파악할 수 있도록 구조화된 한국어 설명을 제공합니다.
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
            {/* ================================================================
          AI DEV AUTOMATION DASHBOARD — LLM 조작 가이드 (한국어)
          이 블록은 DOM 파싱용입니다. 화면에는 렌더링되지 않습니다.
          ================================================================ */}

            <section data-guide="system-overview">
                <h1>AI Dev Automation Dashboard — 시스템 개요</h1>
                <p>
                    이 대시보드는 AI 에이전트가 코드 변경을 자동으로 계획·구현·테스트·리뷰하는
                    시스템입니다. 사용자는 자연어로 Task를 제출하고, AI 파이프라인이 나머지를 처리합니다.
                </p>
                <p>
                    백엔드는 http://localhost:8001 에서, 대시보드는 http://localhost:3000 에서 실행됩니다.
                </p>
            </section>

            <section data-guide="navigation">
                <h2>주요 화면 및 URL</h2>
                <ul>
                    <li>
                        <strong>리포지토리 관리</strong>: /repos — Git 프로젝트를 등록하거나 확인합니다.
                    </li>
                    <li>
                        <strong>Task 보드</strong>: /tasks?repo_id=숫자 — 특정 리포지토리의 Task를 관리합니다.
                        예: /tasks?repo_id=2
                    </li>
                </ul>
            </section>

            <section data-guide="repo-registration">
                <h2>리포지토리 등록 방법</h2>
                <ol>
                    <li>/repos 페이지로 이동한다.</li>
                    <li>오른쪽 상단의 "Register Repo" 또는 "+ Add Repo" 버튼을 클릭한다.</li>
                    <li>
                        Name(이름)과 Path(절대 경로)를 입력한다.
                        Path는 반드시 기존에 존재하는 Git 저장소의 경로여야 한다. 예: D:\Projects\my-app
                    </li>
                    <li>"Register" 버튼을 클릭한다.</li>
                </ol>
                <p>주의: 워크스페이스 하위 폴더 경로가 아닌 실제 Git 루트 경로를 입력해야 한다.</p>
            </section>

            <section data-guide="task-creation">
                <h2>Task 추가 방법 (가장 중요)</h2>
                <ol>
                    <li>/tasks?repo_id=숫자 페이지로 이동한다.</li>
                    <li>오른쪽 상단의 "+ Add Task" 버튼을 클릭한다.</li>
                    <li>
                        Task 입력란에 수행할 작업을 구체적으로 한국어 또는 영어로 입력한다.
                        예: "블록을 깨면 아이템이 떨어지는 기능 추가. 멀티볼(3개), 바 확장, 슬로우볼 3종류."
                    </li>
                    <li>
                        워크스페이스 선택 옵션이 나타난다:
                        <ul>
                            <li>
                                기존 워크스페이스에 기능을 추가할 때는 반드시 "Existing workspace"를 선택하고
                                목록에서 해당 workspace를 선택한다. 이미 작성된 코드 위에서 작업이 계속된다.
                            </li>
                            <li>
                                완전히 새로운 기능을 시작할 때만 "Create new workspace"를 선택한다.
                            </li>
                        </ul>
                    </li>
                    <li>"Create Task" 버튼을 클릭한다.</li>
                    <li>AI 에이전트가 추가 질문을 할 수 있다. 답변 후 "Update Draft"를 클릭한다.</li>
                </ol>
                <p>
                    절대 하지 말아야 할 것: 기존 코드가 있는 workspace에 기능을 추가할 때
                    새 workspace를 생성하면 안 된다. 기존 코드가 보이지 않아 처음부터 다시 만들게 된다.
                </p>
            </section>

            <section data-guide="task-board-columns">
                <h2>Task 보드 컬럼 설명</h2>
                <ul>
                    <li><strong>Queued</strong>: Task가 대기 중이다.</li>
                    <li>
                        <strong>Working</strong>: AI 파이프라인이 실행 중이다.
                        내부 단계: Plan → Critique → Implement → Test → Review
                    </li>
                    <li><strong>Needs Approval</strong>: 파이프라인이 완료됐고, 사람의 병합 승인이 필요하다.</li>
                    <li>
                        <strong>Needs Attention</strong>: 에이전트가 문제를 발견했고 후속 지시가 필요하다.
                        Task 카드를 클릭해서 상세 오류를 확인하고 Next Action을 작성한다.
                    </li>
                    <li><strong>Cancelled</strong>: 취소된 Task다.</li>
                    <li><strong>Done</strong>: 병합 완료된 Task다.</li>
                </ul>
            </section>

            <section data-guide="needs-attention-handling">
                <h2>Needs Attention 처리 방법</h2>
                <ol>
                    <li>Needs Attention 컬럼의 Task 카드를 클릭한다.</li>
                    <li>모달에서 Step History를 확인한다. 마지막 Step(보통 REVIEW 또는 TEST)을 클릭한다.</li>
                    <li>Step Logs에서 오류 원인을 읽는다.</li>
                    <li>
                        화면 하단 "Next Action" 텍스트박스에 구체적인 수정 지시를 입력한다.
                        예: "게임을 일시정지할 때 공이 패들로 이동하는 버그를 수정해줘. game.js의
                        movePaddle 함수에서 paused 상태일 때 ball.x를 변경하지 않도록 수정."
                    </li>
                    <li>"Send Command &amp; Requeue" 버튼을 클릭한다.</li>
                    <li>Task가 다시 Working으로 이동하면 파이프라인이 재시작된 것이다.</li>
                </ol>
                <p>
                    주의: Next Action 텍스트박스를 비워두고 Requeue하면 에이전트가 문맥 없이 재시작되어
                    같은 실수를 반복할 수 있다. 반드시 구체적인 지시를 입력한다.
                </p>
            </section>

            <section data-guide="step-history">
                <h2>Step History (단계별 이력) 읽는 법</h2>
                <p>Task 상세 모달을 열면 Step History 사이드바에 아래 단계들이 표시된다:</p>
                <ul>
                    <li><strong>PLAN</strong>: 구현 계획 수립</li>
                    <li><strong>CRITIQUE</strong>: 계획 타당성 검토</li>
                    <li><strong>IMPLEMENT</strong>: 실제 코드 작성</li>
                    <li><strong>TEST</strong>: 정적 검증 및 동작 확인</li>
                    <li><strong>REVIEW</strong>: 병합 준비 상태 최종 검토</li>
                </ul>
                <p>
                    각 Step을 클릭하면 해당 단계의 로그와 Artifacts(Plan captured, Diff captured) 정보가 나타난다.
                    오류가 생긴 단계의 Step Logs에 VERDICT와 DETAILS가 기록된다.
                </p>
            </section>

            <section data-guide="common-errors">
                <h2>자주 발생하는 오류와 해결법</h2>
                <ul>
                    <li>
                        <strong>read-only workspace / Implementation completed without creating any file changes</strong>:
                        Windows 환경에서 Codex 샌드박스 버그. backend/app/config.py 에서
                        CODEX_WINDOWS_UNSANDBOXED_WORKAROUND = True 로 설정 후 서버 재시작.
                    </li>
                    <li>
                        <strong>Reviewer blocked merge readiness (NEEDS_ATTENTION)</strong>:
                        코드 기능 버그 발견. Step 9 REVIEW의 DETAILS를 읽고 Next Action에 정확한 수정 지시 입력 후 Requeue.
                    </li>
                    <li>
                        <strong>대시보드가 비어있음 / Task가 보이지 않음</strong>:
                        서버가 재시작되어 포트가 바뀌었을 수 있다. ./start.bat 을 다시 실행한다.
                    </li>
                </ul>
            </section>

            <section data-guide="workspace-note">
                <h2>워크스페이스 경로 참고</h2>
                <p>
                    각 Task의 실제 파일은 아래 경로에 생성된다:
                    project/workspaces/repo-숫자-리포이름/workspace-숫자-task이름/
                    예: D:\Python\agent\project\workspaces\repo-2-test-alkaorid\workspace-4-arkanoid-game
                </p>
                <p>
                    이 경로는 Task 상세 모달의 Workspace 섹션에서 확인할 수 있다.
                </p>
            </section>
        </div>
    );
}
