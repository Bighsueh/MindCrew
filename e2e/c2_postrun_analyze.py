"""Phase 42 C2 live 收工後分析（在 backend 容器內執行）。
用法（容器內）：python c2_postrun_analyze.py <project_id> <label>
輸出：定義階段特殊閘的最終判定、選定區成員、forced_closure 兜底物、設計題目配對、
first_diamond_output(v2) 結業鏈、redis 選定區 section。
"""
import asyncio
import json
import sys

from uuid import UUID


async def main(pid_str: str, label: str):
    pid = UUID(pid_str)
    print(f"\n================ C2 POST-RUN [{label}] project={pid_str} ================")

    # 1) 最終 canvas 上的特殊閘判定（live 資料）
    from app.canvas.artifact_gate import (
        check_artifact_gate, _selection_members, _is_problem_statement,
        format_gate_rejection_zh,
    )
    for sp in ("2.6", "2.7"):
        g = await check_artifact_gate(pid, sp)
        print(f"\n-- artifact_gate({sp}) --")
        print(f"   passed={g.passed} counts={g.counts} requirements={g.requirements} missing={g.missing}")
        print(f"   reasons_zh={list(g.reasons_zh)}")
        print(f"   ui_message={format_gate_rejection_zh(g)!r}")

    # 2) 選定區成員 + forced 兜底物
    from app.canvas.analyzer import get_spatial_analyzer
    analysis = await get_spatial_analyzer().analyze(pid)
    notes = list(analysis.notes)
    members = await _selection_members(pid, notes)
    print(f"\n-- 選定區成員（任一動態 section 帶內便條）：{len(members)} 張 --")
    for m in members:
        txt = (getattr(m, "text", None) or getattr(m, "content", "") or "")[:48]
        print(f"   id={getattr(m,'id','?')} kind={getattr(m,'kind','?')} tbf={getattr(m,'time_box_forced',False)} "
              f"cites={getattr(m,'cites',None)} is_PS={_is_problem_statement(m)} text={txt!r}")

    forced = [n for n in notes if getattr(n, "time_box_forced", False)]
    print(f"\n-- forced_closure 兜底理由便條（time_box_forced=True）：{len(forced)} 張 --")
    for n in forced:
        print(f"   id={getattr(n,'id','?')} cites={getattr(n,'cites',None)} text={(getattr(n,'text',None) or getattr(n,'content',''))!r}")

    # 3) redis 選定區 section
    from app.canvas.sections import list_sections
    secs = await list_sections(pid)
    print(f"\n-- redis sections：{len(secs)} 條 --")
    for s in secs:
        print(f"   {s}")

    # 4) 設計題目（hmw）配對
    hmws = []
    from app.canvas.text_templates import validate_template
    for n in notes:
        t = getattr(n, "text", None) or getattr(n, "content", "") or ""
        if validate_template(t, "hmw").passed:
            hmws.append(n)
    print(f"\n-- 設計題目（hmw 模板通過）：{len(hmws)} 張 --")
    member_ids = {str(getattr(m, "id", "")) for m in members if _is_problem_statement(m)}
    for h in hmws:
        cites = getattr(h, "cites", None) or ()
        paired = any(c in member_ids for c in cites)
        print(f"   id={getattr(h,'id','?')} cites={list(cites)} pairsChosenPS={paired} text={(getattr(h,'text',None) or getattr(h,'content',''))[:48]!r}")

    # 5) first_diamond_output（v2 結業鏈）
    from app.db.session import async_session_factory
    from app.db.models.project import Project
    from sqlalchemy import select
    async with async_session_factory() as session:
        proj = (await session.execute(select(Project).where(Project.id == pid))).scalar_one_or_none()
        out = getattr(proj, "first_diamond_output", None) if proj else None
        stage = getattr(proj, "current_stage", None) if proj else None
        print(f"\n-- project.current_stage={stage} --")
        print(f"-- first_diamond_output（JSONB）--")
        if out is None:
            print("   <NULL — 結業匯報尚未寫入>")
        else:
            print(json.dumps(out, ensure_ascii=False, indent=2)[:2400])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "?"))
