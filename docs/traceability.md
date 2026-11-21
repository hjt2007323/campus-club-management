# 需求追溯矩阵与开发任务

需求和验收编号沿用 v1.0。运行证据见[验收记录](acceptance.md)。

| 需求 | 模块 | 接口或实现 | 验收编号 |
|---|---|---|---|
| CLUB-01 | 社团 | POST /clubs | T01 |
| CLUB-02 | 社团 | POST /clubs/{id}/review | T02、B01、B15 |
| CLUB-03 | 社团 | GET /clubs | T03 |
| CLUB-04、CLUB-05 | 社团 | POST /clubs/{id}/annual-reviews、POST /annual-reviews/{id}/decision | T04 |
| ACT-01、ACT-03 | 活动 | POST /activities、PATCH /activities/{id} | T05、T07、B01 |
| ACT-02、AI-01 | 活动策划 | POST /clubs/{id}/ai-plan | T06、B13、B14、E2E-03 |
| ACT-04 | 活动 | POST /activities/{id}/submit、POST /activities/{id}/review | T08 |
| ACT-05 | 活动 | GET /activities | T09 |
| ACT-06、ACT-07 | 活动 | PUT 或 DELETE /activities/{id}/registration、GET /activities/{id}/registrations | T10、T11、B02、B08 |
| ACT-08 | 活动 | POST /activities/{id}/attendance、POST /activities/{id}/complete | T12、B09 |
| VEN-01、VEN-02 | 场地 | POST 或 GET /venues、PATCH /venues/{id} | T13 |
| VEN-03 至 VEN-05 | 场地 | POST /reservations、POST /reservations/{id}/review | T14、T15、B03、B04 |
| VEN-06 | 场地 | GET /activities/{id}/venue-options、GET /reservations/{id}/alternatives | T16、B05、B06 |
| VEN-06、VEN-07 | 场地 | POST /venue-blocks、GET /venue-blocks/{id}/coordination、POST /venue-blocks/{id}/coordinate | T17、B07、E2E-02 |
| CREDIT-01 | 学分 | PUT /activities/{id}/credit-rule | T18 |
| CREDIT-02 至 CREDIT-04 | 学分 | POST /activities/{id}/complete、GET /me/credits | T19、T20、B10、B11 |
| EVAL-01 至 EVAL-04 | 评价 | POST 或 GET /activities/{id}/evaluations | T21、T22、B12 |
| STAT-01 至 STAT-05 | 统计 | GET /statistics | T23 |
| AI-02 | 跨模块 | AI 接口返回草案，活动写入经独立接口人工确认 | B13、E2E-01、E2E-03 |
| NFR-01、NFR-05 | 交互与异常 | Web 表单反馈、请求校验、上游和数据库错误处理 | 浏览器实测、B13、B14 |
| NFR-02、NFR-03 | 数据 | SQLite 持久化、联合键及预约事务 | D03、B03、B08、B09、B11 |
| NFR-04 | 权限 | 服务端身份、角色和社团归属校验 | B01、B15 |
| NFR-06 至 NFR-08 | 工程 | 分层、Pytest、GET /health、README | D01 至 D06 |

## 开发任务

| 工作 | 当前进度 |
|---|---|
| 可运行骨架，社团申请审核，草案与 DeepSeek | 已实现并验证 |
| 活动审批、报名、签到，场地预约与冲突检测 | 已实现并验证 |
| 活动完成、学分、评价、统计、社团年审 | 已实现并验证 |
| 征用登记、原时段候选筛选、管理员确认 | 已实现并验证，可手工协调 |
| 多预约批量推荐、TRAE 实际使用及取证 | 已完成，专项复验 8 项通过，开发截图已归档 |
| 两份报告、Gitee 链接和提交编号 | 报告草稿已附，仓库已在本地初始化，Gitee 交付待完成 |
