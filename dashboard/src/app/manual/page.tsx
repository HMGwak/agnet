export default function ManualPage() {
    return (
        <div className="max-w-3xl mx-auto py-8 px-4">
            <div className="mb-8">
                <h1 className="text-3xl font-bold text-gray-900 mb-2">사용자 매뉴얼</h1>
                <p className="text-gray-500 text-sm">AI Dev Automation Dashboard — User Manual</p>
            </div>

            {/* 시스템 개요 */}
            <section className="mb-8">
                <h2 className="text-xl font-semibold text-gray-800 border-b pb-2 mb-4">📌 시스템 개요</h2>
                <p className="text-gray-700 leading-relaxed">
                    이 대시보드는 AI 에이전트가 코드 변경을 자동으로 <strong>계획 → 구현 → 테스트 → 리뷰</strong>하는
                    시스템입니다. 자연어로 Task를 입력하면 AI 파이프라인이 나머지를 처리합니다.
                </p>
                <div className="mt-3 bg-gray-50 rounded-lg p-4 text-sm text-gray-600 font-mono">
                    <div>백엔드: http://localhost:8001</div>
                    <div>대시보드: http://localhost:3000</div>
                </div>
            </section>

            {/* Step 1: 리포지토리 등록 */}
            <section className="mb-8">
                <h2 className="text-xl font-semibold text-gray-800 border-b pb-2 mb-4">
                    1️⃣ 리포지토리 등록
                </h2>
                <ol className="list-decimal list-inside space-y-2 text-gray-700">
                    <li>
                        사이드바에서 <strong>Repos</strong>를 클릭한다.
                    </li>
                    <li>
                        오른쪽 상단 <strong>Register Repo</strong> 버튼을 클릭한다.
                    </li>
                    <li>
                        <strong>Name</strong>(짧은 이름)과 <strong>Path</strong>(로컬 Git 저장소의 절대 경로)를 입력한다.
                        <div className="mt-1 bg-yellow-50 border border-yellow-200 rounded px-3 py-2 text-sm text-yellow-800">
                            ⚠️ Path는 Git 저장소의 루트 경로여야 합니다. 워크스페이스 하위 폴더 경로를 입력하면 안 됩니다.
                        </div>
                    </li>
                    <li>
                        <strong>Register</strong> 버튼을 클릭한다.
                    </li>
                </ol>
            </section>

            {/* Step 2: Task 추가 */}
            <section className="mb-8">
                <h2 className="text-xl font-semibold text-gray-800 border-b pb-2 mb-4">
                    2️⃣ Task 추가 (가장 중요)
                </h2>
                <ol className="list-decimal list-inside space-y-2 text-gray-700">
                    <li>
                        사이드바에서 <strong>Tasks</strong> → 리포지토리 이름을 클릭한다.
                    </li>
                    <li>
                        오른쪽 상단 <strong>+ Add Task</strong> 버튼을 클릭한다.
                    </li>
                    <li>
                        Task 입력란에 수행할 작업을 구체적으로 입력한다.
                        <div className="mt-1 text-sm bg-gray-50 rounded px-3 py-2 text-gray-600 italic">
                            예: "블록을 깨면 파워업 아이템이 떨어지는 기능 추가. 멀티볼(공 3개), 바 확장, 슬로우볼 3종류. 멀티볼 제외 나머지는 바에 10번 튀기면 효과 소멸."
                        </div>
                    </li>
                    <li>
                        워크스페이스 선택:
                        <ul className="list-disc list-inside ml-4 mt-2 space-y-1 text-sm">
                            <li>
                                <strong>기존 코드에 기능 추가</strong>: <span className="text-blue-700 font-medium">Existing workspace</span>를 선택하고 목록에서 해당 workspace를 고른다. 이미 작성된 코드 위에서 AI가 작업한다.
                            </li>
                            <li>
                                <strong>완전히 새로운 기능</strong>: <span className="text-blue-700 font-medium">Create new workspace</span>를 선택한다.
                            </li>
                        </ul>
                        <div className="mt-2 bg-red-50 border border-red-200 rounded px-3 py-2 text-sm text-red-800">
                            ❌ 기존 코드가 있는 workspace에 기능을 추가할 때 새 workspace를 만들면 안 됩니다.
                            AI가 이전 코드를 보지 못하고 처음부터 다시 만들게 됩니다.
                        </div>
                    </li>
                    <li>
                        <strong>Create Task</strong>를 클릭한다. AI가 추가 질문을 할 수 있으며, 답변 후 <strong>Update Draft</strong>를 클릭한다.
                    </li>
                </ol>
            </section>

            {/* Step 3: Task 보드 */}
            <section className="mb-8">
                <h2 className="text-xl font-semibold text-gray-800 border-b pb-2 mb-4">
                    3️⃣ Task 보드 컬럼 설명
                </h2>
                <div className="overflow-hidden rounded-lg border border-gray-200">
                    <table className="min-w-full divide-y divide-gray-200 text-sm">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-4 py-3 text-left font-semibold text-gray-700">컬럼</th>
                                <th className="px-4 py-3 text-left font-semibold text-gray-700">의미</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 bg-white">
                            {[
                                ["Queued", "AI가 처리를 시작 전 대기 중"],
                                ["Working", "AI 파이프라인 실행 중 (Plan → Critique → Implement → Test → Review)"],
                                ["Needs Approval", "파이프라인 완료. 사람의 병합 승인 필요. Approve & Merge 클릭"],
                                ["Needs Attention", "AI가 문제를 발견하여 후속 지시가 필요. 카드 클릭 후 Next Action 입력"],
                                ["Cancelled", "수동으로 취소된 Task"],
                                ["Done", "병합 완료됨"],
                            ].map(([col, desc]) => (
                                <tr key={col}>
                                    <td className="px-4 py-3 font-medium text-gray-900 whitespace-nowrap">{col}</td>
                                    <td className="px-4 py-3 text-gray-600">{desc}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </section>

            {/* Step 4: Needs Attention 처리 */}
            <section className="mb-8">
                <h2 className="text-xl font-semibold text-gray-800 border-b pb-2 mb-4">
                    4️⃣ Needs Attention 처리 방법
                </h2>
                <ol className="list-decimal list-inside space-y-2 text-gray-700">
                    <li>Needs Attention 컬럼의 Task 카드를 클릭한다.</li>
                    <li>
                        모달에서 <strong>Step History</strong> 사이드바의 마지막 Step(보통 REVIEW 또는 TEST)을 클릭한다.
                    </li>
                    <li>
                        <strong>Step Logs</strong>에서 VERDICT와 DETAILS(오류 원인)을 읽는다.
                    </li>
                    <li>
                        화면 하단 <strong>Next Action</strong> 텍스트박스에 구체적인 수정 지시를 입력한다.
                        <div className="mt-1 text-sm bg-gray-50 rounded px-3 py-2 text-gray-600 italic">
                            예: "일시정지(pause) 상태일 때 공이 패들 중앙으로 이동하는 버그 수정. game.js의 movePaddle 함수에서 mode가 paused일 때 ball.x를 변경하지 않도록 수정."
                        </div>
                    </li>
                    <li>
                        <strong>Send Command & Requeue</strong> 버튼을 클릭한다.
                    </li>
                </ol>
                <div className="mt-3 bg-yellow-50 border border-yellow-200 rounded px-3 py-2 text-sm text-yellow-800">
                    ⚠️ Next Action 박스를 비워두고 Requeue하면 AI가 같은 실수를 반복합니다. 반드시 구체적으로 입력하세요.
                </div>
            </section>

            {/* Step 5: 파이프라인 단계 */}
            <section className="mb-8">
                <h2 className="text-xl font-semibold text-gray-800 border-b pb-2 mb-4">
                    5️⃣ AI 파이프라인 단계 (Step History)
                </h2>
                <div className="flex flex-wrap gap-2 text-sm">
                    {[
                        ["PLAN", "구현 계획 수립", "blue"],
                        ["CRITIQUE", "계획 타당성 검토", "purple"],
                        ["IMPLEMENT", "코드 작성", "green"],
                        ["TEST", "정적 검증 및 확인", "orange"],
                        ["REVIEW", "병합 준비 최종 검토", "red"],
                    ].map(([step, desc, _color]) => (
                        <div key={step} className="flex-shrink-0 border border-gray-200 rounded-lg p-3 bg-white w-40">
                            <div className="font-semibold text-gray-800 mb-1">{step}</div>
                            <div className="text-gray-500 text-xs">{desc}</div>
                        </div>
                    ))}
                </div>
            </section>

            {/* 자주 발생하는 오류 */}
            <section className="mb-8">
                <h2 className="text-xl font-semibold text-gray-800 border-b pb-2 mb-4">
                    🔧 자주 발생하는 오류
                </h2>
                <div className="space-y-4">
                    {[
                        {
                            title: "read-only workspace / 파일 변경 없이 구현 완료",
                            cause: "Windows에서 Codex 0.111.0 샌드박스 버그",
                            fix: "backend/app/config.py에서 CODEX_WINDOWS_UNSANDBOXED_WORKAROUND = True 설정 후 서버 재시작",
                        },
                        {
                            title: "Reviewer blocked merge readiness (NEEDS_ATTENTION)",
                            cause: "코드 기능 버그 발견",
                            fix: "Step 9 REVIEW 로그의 DETAILS 항목을 읽고 Next Action에 구체적 수정 지시 후 Requeue",
                        },
                        {
                            title: "대시보드가 빈 화면 / API 404",
                            cause: "백엔드 서버 종료됨",
                            fix: "./start.bat 재실행. project/logs/latest/backend.err.log 확인",
                        },
                    ].map((e) => (
                        <div key={e.title} className="bg-white border border-gray-200 rounded-lg p-4">
                            <div className="font-medium text-gray-900 mb-1">❗ {e.title}</div>
                            <div className="text-sm text-gray-600">
                                <span className="font-medium">원인:</span> {e.cause}
                            </div>
                            <div className="text-sm text-gray-600">
                                <span className="font-medium">해결:</span> {e.fix}
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            <footer className="text-xs text-gray-400 border-t pt-4">
                AI Dev Automation Dashboard — 버전 참고: backend/app/config.py
            </footer>
        </div>
    );
}
