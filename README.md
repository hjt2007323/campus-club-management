# 高校社团活动全流程管理系统

需求基线 v1.0 · 课程原型

## 本地启动

在项目目录打开 PowerShell。使用 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install --index-url https://pypi.org/simple -r requirements.txt
$env:CAMPUS_STUDENT_TOKEN = [guid]::NewGuid().ToString('N')
$env:CAMPUS_ADMIN_TOKEN = [guid]::NewGuid().ToString('N')
$participantToken = [guid]::NewGuid().ToString('N')
$env:CAMPUS_STUDENT_TOKENS = @{ participant = $participantToken } | ConvertTo-Json -Compress
.venv/Scripts/python.exe -m uvicorn app.main:app --log-level info
```

打开 [系统主页](http://127.0.0.1:8000/) 或 [接口文档](http://127.0.0.1:8000/docs)。用对应令牌切换学生、管理员和参与者账号。学生提交社团申请后，管理员审核通过，该学生即可作为自己社团的负责人。额外学生可通过 `CAMPUS_STUDENT_TOKENS` 添加，键为稳定账号名，值为唯一令牌。请妥善保存账号令牌，防止其他人操作演示数据。

生成策划前，在运行服务的 PowerShell 会话中预先配置 `DEEPSEEK_API_KEY`。可用 `DEEPSEEK_MODEL` 指定模型，默认为 `deepseek-flash`。未配置密钥时仍可填写和人工保存活动草稿。项目默认在当前目录写入 `campus.db`，可用 `DATABASE_URL` 设定其他 SQLite 文件。

## 原型演示

在项目目录运行 `python -m app.demo`，打开 [演示页面](http://127.0.0.1:8765/)。脚本通过业务接口向独立的临时 SQLite 数据库写入 2 个社团、3 场活动和 4 个场地，退出时清理，不影响普通启动使用的 `campus.db`。

- 用 `demo-admin` 登录，在「场地 → 替代场地协调」选择「校级考试临时征用」，查看两场活动的自动建议并确认。在「统计」查询已写入的业务数据。
- 用 `demo-student` 登录，在「学分」查询 Python 入门工作坊的 1 学分。真实 AI 生成需要服务端配置 DeepSeek 密钥，演示数据本身不调用模型。

## 从空数据库演示

- **活动生命周期**。先用学生账号申请社团，换管理员账号审核。学生填写策划或生成草案，人工确认后保存，再填写原定时间、学期和活动类型并提交审批。管理员通过后切换参与者账号报名。按活动时段登记签到，结束后由管理员确认完成，再查学分、评价和统计。现场演示可排一个几分钟后开始的短活动。系统用浏览器本地时间录入，接口使用带时区的时间。
- **场地协调**。管理员建立多个场地，两个已审批的活动尝试预约同一教室的重叠时段。第二次申请会提示占用，可用候选筛选改选其他场地。场地被征用后，在协调面板保留原定时段，查看批量建议，可调整后由管理员确认。批量匹配专项见验收记录。
- **AI 策划**。输入校园活动构想，使用 DeepSeek 生成结构化草案，在表单中改写标题或流程后点击人工确认并保存。生成动作本身不会创建活动。运行服务时，日志可记录成功请求的模型、响应编号和用量。

默认学分为每位符合条件的学生 1 分，管理员可在活动完成前另设数值。报名在活动开始时关闭，签到在活动开始到结束之间开放。

## 运行测试

```powershell
.venv/Scripts/python.exe -m pytest -q
```

单独复验真实 API 时使用下列命令。测试通过 DeepSeek 发送一条固定的校园编程赛描述，真实调用可能计费。

```powershell
$env:RUN_DEEPSEEK_LIVE = '1'
.venv/Scripts/python.exe -m pytest -q -k deepseek_live -o log_cli=true --log-cli-level=INFO
Remove-Item Env:RUN_DEEPSEEK_LIVE
```

各测试使用隔离的临时数据库。默认回归会跳过真实 API 项，TRAE 匹配专项单独执行。

- [需求追溯矩阵与开发任务](docs/traceability.md)
- [本阶段验收记录](docs/acceptance.md)
- [需求分析报告草稿](docs/requirements-report.md)
- [系统设计报告草稿](docs/design-report.md)
- [TRAE 开发任务及留存时点](docs/trae-task.md)
