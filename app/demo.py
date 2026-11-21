"""Run a disposable local demo populated through the business API."""

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

from .main import create_app
from .times import current_time


def main():
    parser = argparse.ArgumentParser(description="启动本地课程演示")
    parser.add_argument("--port", type=int, default=8765)
    port = parser.parse_args().port
    os.environ.update(
        CAMPUS_ADMIN_TOKEN="demo-admin",
        CAMPUS_STUDENT_TOKEN="demo-student",
        CAMPUS_STUDENT_TOKENS=json.dumps({
            "network-club": "demo-network",
            **{f"sample-{i:02}": f"demo-club-{i:02}" for i in range(1, 19)},
        }),
    )
    with TemporaryDirectory(prefix="campus-demo-") as directory:
        path = Path(directory, "demo.db").as_posix()
        app = create_app(f"sqlite:///{path}")
        seed(app)
        print(f"Demo: http://127.0.0.1:{port}  |  demo-admin / demo-student", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=port)


def seed(app):
    today = datetime.now(UTC).replace(tzinfo=None, second=0, microsecond=0)
    past = today - timedelta(days=2)
    future = today + timedelta(days=2)
    clock = past - timedelta(hours=1)
    app.dependency_overrides[current_time] = lambda: clock

    with TestClient(app) as client:
        def call(path, body=None, token="demo-admin", method="POST"):
            response = client.request(method, path, json=body, headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
            return response.json()

        def club(name, actor):
            number = call("/clubs", {"name": name}, actor)["id"]
            call(f"/clubs/{number}/review", {"status": "approved"})
            return number

        def venue(name, equipment, capacity=40):
            return call("/venues", {"name": name, "capacity": capacity, "equipment": equipment})["id"]

        def activity(club_id, actor, title, equipment, time, category="实践", source=None):
            summary = "课程演示数据"
            if source:
                summary += f"。选题参考 {source}，校内举办安排为模拟。"
            plan = dict(title=title, summary=summary, goals=["完成一次校园实践"],
                        agenda=["活动介绍", "分组实践"], participants=20, duration_minutes=60,
                        venue_capacity=20, equipment=equipment, notes=[])
            number = call("/activities", {"club_id": club_id, "confirmed": True, "plan": plan}, actor)["id"]
            call(f"/activities/{number}/submit", {
                "starts_at": time.replace(tzinfo=UTC).isoformat(),
                "ends_at": (time + timedelta(hours=1)).replace(tzinfo=UTC).isoformat(),
                "semester": f"{today.year} 演示学期", "category": category,
            }, actor)
            call(f"/activities/{number}/review", {"status": "approved"})
            return number

        def reserve(number, room, actor):
            booking = call("/reservations", {"activity_id": number, "venue_id": room}, actor)["id"]
            call(f"/reservations/{booking}/review", {"status": "approved"})

        owner, other = "demo-student", "demo-network"
        programming, network = club("编程社", owner), club("网络技术社", other)
        original_a = venue("原投影教室", ["投影"])
        original_b = venue("原网络教室", ["网络"])
        combined = venue("投影网络教室", ["投影", "网络"])
        spare = venue("备用投影教室", ["投影"])
        historical = activity(programming, owner, "Python 入门工作坊", ["投影"], past)
        reserve(historical, original_a, owner)
        call(f"/activities/{historical}/registration", token=owner, method="PUT")
        clock = past + timedelta(minutes=15)
        call(f"/activities/{historical}/attendance", {"student_id": "student"})
        clock = today
        call(f"/activities/{historical}/complete")
        call(f"/activities/{historical}/evaluations", {"rating": 5, "comment": "分组练习对初学者很有帮助。"}, owner)

        samples = (
            ("校园数据分析挑战", "竞赛", "Kaggle Meta Kaggle Hackathon", programming, owner),
            ("校园游戏创作接力", "竞赛", "GitHub Game Off", programming, owner),
            ("校园开放数据实践", "工作坊", "NASA Space Apps Challenge", network, other),
            ("校园数据可视化工坊", "工作坊", "Hacklytics", programming, owner),
            ("信息安全基础讲座", "讲座", None, network, other),
            ("社团迎新交流会", "交流", None, programming, owner),
            ("开源协作分享会", "讲座", None, programming, owner),
            ("校园网络设备体验", "交流", None, network, other),
        )
        for offset, (title, category, source, club_id, actor) in enumerate(samples, start=1):
            starts = future + timedelta(days=offset + 1)
            sample = activity(club_id, actor, title, ["投影"], starts, category, source)
            if offset <= 4:
                reserve(sample, spare, actor)
                call(f"/activities/{sample}/registration", token=owner, method="PUT")

        first = activity(programming, owner, "校园编程分享会", ["投影"], future)
        second = activity(network, other, "网络实验体验课", ["网络"], future)
        bookable = activity(programming, owner, "网页设计入门课", ["投影"], future + timedelta(days=1))
        reserve(first, original_a, owner)
        reserve(second, original_b, other)
        venue_groups = [
            ("普通教室", 12, 50, ["白板"]),
            ("实验教室", 6, 32, ["实验台"]),
            ("舞台", 6, 160, ["舞台灯光", "舞台音响"]),
            ("报告厅", 6, 180, ["讲台", "无线麦克风"]),
            ("会议室", 6, 24, ["会议白板"]),
        ]
        rooms = []
        for kind, count, capacity, equipment in venue_groups:
            for room_number in range(1, count + 1):
                room_id = venue(f"{kind} {room_number:02d}", equipment, capacity)
                rooms.append((room_id, equipment))

        names = ("摄影", "辩论", "戏剧", "志愿服务", "书法", "科普", "音乐", "机器人", "心理健康",
                 "英语交流", "舞蹈", "创客", "环保", "职业发展", "读书", "设计", "演讲", "校园媒体")
        sessions = (("入门体验", "工作坊"), ("案例分享", "讲座"), ("小组实践", "实践"),
                    ("社团交流", "交流"), ("成果展演", "展演"), ("专题报告", "讲座"))
        for club_index, name in enumerate(names, start=1):
            actor = f"demo-club-{club_index:02}"
            club_id = club(f"{name}社", actor)
            for session_index, (topic, category) in enumerate(sessions):
                room, equipment = rooms[(2 * (club_index - 1) + session_index) % len(rooms)]
                if topic == "成果展演":
                    room, equipment = rooms[18 + (club_index - 1) % 6]
                elif topic == "专题报告":
                    room, equipment = rooms[24 + (club_index - 1) % 6]
                starts = future + timedelta(days=12 + (club_index - 1) * len(sessions) + session_index)
                sample = activity(club_id, actor, f"{name}社 · {topic}", equipment, starts, category)
                reserve(sample, room, actor)
                if club_index <= 15 and session_index < 3:
                    call(f"/activities/{sample}/registration", token=actor, method="PUT")
        block = call("/venue-blocks", {
            "venue_ids": [original_a, original_b], "reason": "校级考试临时征用",
            "starts_at": future.replace(tzinfo=UTC).isoformat(),
            "ends_at": (future + timedelta(hours=1)).replace(tzinfo=UTC).isoformat(),
        })
        preview = call(f"/venue-blocks/{block['id']}/coordination", method="GET")
        suggested = {item["reservation_id"]: item["venue_id"] for item in preview["suggested_assignments"]}
        expected = dict(zip(block["affected_reservation_ids"], (spare, combined)))
        if suggested != expected:
            raise RuntimeError("演示协调建议与预期不符")
        stats = call("/statistics", method="GET")
        options = call(f"/activities/{bookable}/venue-options", token=owner, method="GET")
        if spare not in {room["id"] for room in options}:
            raise RuntimeError("演示活动没有可预约的备用投影教室")
        clubs = call("/clubs", method="GET")
        venues = call("/venues", method="GET")
        if (len(clubs), stats["activity_count"], len(venues), stats["registrations"], stats["credit_total"]) != (20, 120, 40, 50, 1):
            raise RuntimeError("演示数据库统计与预期不符")

    app.dependency_overrides.clear()


if __name__ == "__main__":
    main()

