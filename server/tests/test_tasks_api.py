from __future__ import annotations

from fastapi.testclient import TestClient

from server.tests.support import app


def test_task_capsule_core_api_lifecycle() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={
                "title": "Task Capsule 后端闭环",
                "userGoal": "实现任务胶囊核心 API",
                "activeAgent": "codex",
            },
        )
        assert created.status_code == 200
        task_detail = created.json()
        task_id = task_detail["task"]["id"]
        initial_last_event_at = task_detail["task"]["lastEventAt"]

        active_tasks = client.get("/api/tasks", params={"status": "active"})
        assert active_tasks.status_code == 200
        assert any(task["id"] == task_id and task["status"] == "open" for task in active_tasks.json())

        appended = client.post(
            f"/api/tasks/{task_id}/events",
            json={
                "type": "agent_action",
                "summary": "补齐 Task Capsule route",
                "payload": {"files": ["server/app/routes/tasks.py"]},
            },
        )
        assert appended.status_code == 200
        event_payload = appended.json()
        assert event_payload["summary"] == "补齐 Task Capsule route"

        refreshed = client.get(f"/api/tasks/{task_id}")
        assert refreshed.status_code == 200
        refreshed_detail = refreshed.json()
        assert refreshed_detail["task"]["lastEventAt"] == event_payload["createdAt"]
        assert refreshed_detail["task"]["lastEventAt"] != initial_last_event_at

        event_id = event_payload["id"]
        assert client.patch(f"/api/tasks/{task_id}/events/{event_id}", json={"summary": "不允许修改"}).status_code == 404
        assert client.delete(f"/api/tasks/{task_id}/events/{event_id}").status_code == 404

        patched_state = client.patch(
            f"/api/tasks/{task_id}/state",
            json={
                "currentGoal": "完成后端核心 API 和测试",
                "done": ["确认模型存在"],
                "inProgress": ["编写 route"],
                "nextSteps": ["运行 pytest"],
                "openQuestions": ["是否需要前端入口"],
                "decisions": ["事件保持 append-only"],
                "risks": ["关闭任务不能自动写入 KnowledgeItem"],
                "filesTouched": ["server/app/routes/tasks.py"],
            },
        )
        assert patched_state.status_code == 200
        assert patched_state.json()["nextSteps"] == ["运行 pytest"]

        detail_after_state = client.get(f"/api/tasks/{task_id}").json()
        assert detail_after_state["state"]["nextSteps"] == ["运行 pytest"]

        checkpoint = client.post(
            f"/api/tasks/{task_id}/checkpoints",
            json={"title": "核心 API 已完成", "summary": "任务状态、事件和检查点 API 已连通"},
        )
        assert checkpoint.status_code == 200
        checkpoint_payload = checkpoint.json()
        assert checkpoint_payload["taskSessionId"] == task_id
        assert checkpoint_payload["stateSnapshot"]["nextSteps"] == ["运行 pytest"]

        detail_after_checkpoint = client.get(f"/api/tasks/{task_id}").json()
        assert any(item["id"] == checkpoint_payload["id"] for item in detail_after_checkpoint["checkpoints"])

        closed = client.post(f"/api/tasks/{task_id}/close")
        assert closed.status_code == 200
        assert closed.json()["task"]["status"] == "closed"

        assert client.patch(f"/api/tasks/{task_id}/state", json={"nextSteps": ["不应写入"]}).status_code == 409
        assert client.post(
            f"/api/tasks/{task_id}/events",
            json={"type": "agent_action", "summary": "不应追加"},
        ).status_code == 409
        assert client.post(
            f"/api/tasks/{task_id}/checkpoints",
            json={"title": "不应创建", "summary": "终态不可变"},
        ).status_code == 409

        active_after_close = client.get("/api/tasks", params={"status": "active"}).json()
        assert all(task["id"] != task_id for task in active_after_close)

        workbench = client.get("/api/review/workbench", params={"proposalStatus": "pending"})
        assert workbench.status_code == 200
        task_proposal = next(item for item in workbench.json()["proposals"] if item["taskSessionId"] == task_id)
        assert task_proposal["status"] == "pending"
        assert task_proposal["knowledgeItemId"] is None
        assert task_proposal["sourceItemId"] is None

def test_open_task_handoff_contains_next_steps() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={"title": "Handoff open task", "userGoal": "完成 handoff 协议", "activeAgent": "codex"},
        ).json()
        task_id = created["task"]["id"]

        client.patch(
            f"/api/tasks/{task_id}/state",
            json={
                "currentGoal": "交接给下一个执行者",
                "done": ["完成核心任务 API"],
                "inProgress": ["编写 handoff service"],
                "nextSteps": ["运行 handoff 后端测试"],
                "openQuestions": ["是否需要前端入口"],
                "constraints": ["不启动本地服务"],
                "decisions": ["GET 预览，POST 持久化"],
                "risks": ["closed task 默认拒绝 handoff"],
                "filesTouched": ["server/app/tasks/handoff.py"],
            },
        )
        client.post(
            f"/api/tasks/{task_id}/events",
            json={"type": "file_change", "summary": "新增 handoff service", "sourceRef": "server/app/tasks/handoff.py"},
        )
        checkpoint = client.post(
            f"/api/tasks/{task_id}/checkpoints",
            json={"title": "handoff checkpoint", "summary": "handoff 协议字段已确定"},
        ).json()

        response = client.get(f"/api/tasks/{task_id}/handoff", params={"format": "json"})
        assert response.status_code == 200
        handoff = response.json()
        pack = handoff["pack"]

        assert pack["taskId"] == task_id
        assert pack["status"] == "open"
        assert pack["freshness"]["state"] == "fresh"
        assert pack["userGoal"] == "完成 handoff 协议"
        assert pack["currentGoal"] == "交接给下一个执行者"
        assert pack["done"] == ["完成核心任务 API"]
        assert pack["inProgress"] == ["编写 handoff service"]
        assert pack["nextSteps"] == ["运行 handoff 后端测试"]
        assert pack["openQuestions"] == ["是否需要前端入口"]
        assert pack["constraints"] == ["不启动本地服务"]
        assert pack["decisions"] == ["GET 预览，POST 持久化"]
        assert pack["risks"] == ["closed task 默认拒绝 handoff"]
        assert pack["filesTouched"] == ["server/app/tasks/handoff.py"]
        assert pack["nextRecommendedActions"][0]["label"] == "continue_next_step"
        assert "note --task-id" in pack["nextRecommendedActions"][0]["command"]
        assert any(ref["id"] == checkpoint["id"] for ref in pack["checkpointRefs"])
        assert any(ref["sourceRef"] == "server/app/tasks/handoff.py" for ref in pack["sourceRefs"])
        assert "运行 handoff 后端测试" in handoff["content"]

        markdown_response = client.get(f"/api/tasks/{task_id}/handoff", params={"format": "markdown"})
        assert markdown_response.status_code == 200
        assert "建议下一步" in markdown_response.json()["content"]

def test_closed_task_handoff_is_rejected_by_default() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={"title": "Closed handoff default", "userGoal": "验证 closed 默认拒绝"},
        ).json()
        task_id = created["task"]["id"]

        assert client.post(f"/api/tasks/{task_id}/close").status_code == 200

        response = client.get(f"/api/tasks/{task_id}/handoff", params={"format": "markdown"})
        assert response.status_code == 409

def test_include_closed_allows_closed_task_handoff() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={"title": "Closed handoff include", "userGoal": "显式允许 closed handoff"},
        ).json()
        task_id = created["task"]["id"]
        client.post(f"/api/tasks/{task_id}/close")

        response = client.get(
            f"/api/tasks/{task_id}/handoff",
            params={"format": "json", "includeClosed": "true"},
        )
        assert response.status_code == 200
        assert response.json()["pack"]["status"] == "closed"

def test_expired_task_handoff_contains_stale_warning() -> None:
    from datetime import timedelta

    from sqlmodel import Session, select

    from server.app.database import engine
    from server.app.models import TaskSession, utc_now

    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={"title": "Expired handoff", "userGoal": "验证过期 handoff 警告"},
        ).json()
        task_id = created["task"]["id"]

        with Session(engine) as session:
            task = session.get(TaskSession, task_id)
            assert task
            task.status = "expired"
            task.updated_at = utc_now() - timedelta(days=2)
            task.expires_at = utc_now() - timedelta(minutes=1)
            session.add(task)
            session.commit()

        response = client.get(f"/api/tasks/{task_id}/handoff", params={"format": "markdown"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["pack"]["freshness"]["state"] == "expired"
        assert payload["content"].startswith("> 过期提醒：")

def test_create_handoff_records_handoff_created_event() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={"title": "Persist handoff", "userGoal": "POST handoff 写事件"},
        ).json()
        task_id = created["task"]["id"]

        response = client.post(f"/api/tasks/{task_id}/handoff", params={"format": "markdown"})
        assert response.status_code == 200
        handoff = response.json()
        assert handoff["id"]
        assert handoff["format"] == "markdown"

        detail = client.get(f"/api/tasks/{task_id}").json()
        handoff_event = next(event for event in detail["events"] if event["type"] == "handoff_created")
        assert handoff_event["payload"]["handoffPackId"] == handoff["id"]
        assert handoff_event["payload"]["format"] == "markdown"
