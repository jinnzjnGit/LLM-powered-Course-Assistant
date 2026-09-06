# Python 编程基础课程学习助手

用于《AI大模型应用与工程实践》的本地个人/小组实训案例。支持PDF解析与OCR、BM25检索、带出处问答、最近3轮上下文、章节总结、练习测验、学习记录和复习计划。

Streamlit Community Cloud 部署时会读取根目录的 `packages.txt`，安装 OCR/OpenCV 所需的 Linux `libgl1` 与 `libglib2.0-0t64` 系统库。

本实例共用一份学习数据库，未实现登录和跨学生隔离。请每人或每组独立运行；AI批改仅供练习参考。

## 当前电脑启动

启动时优先使用8501端口；如果被占用，会自动在8502～8510中选择空闲端口。请打开启动窗口中显示的实际地址。已经打开的学习助手仍可继续使用，无需重复启动。

推荐双击本目录的 `start.cmd`，或在 PowerShell 中运行 ` .\start.cmd`。这个入口直接启动 Python，不依赖 PowerShell 脚本执行权限。保持启动窗口打开；关闭窗口或重启电脑后需要重新启动。

若终端在其他目录，先执行：

```powershell
cd 'D:\3工作\AI大模型应用与工程实践\python课程学习助手'
.\start.cmd
```

在本目录的PowerShell中运行：

```powershell
.\start.ps1
```

或直接运行：

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

本次已修复本机虚拟环境的解释器路径。不要将`.venv`复制给其他电脑。

## 新电脑安装

安装Python 3.12，在本目录执行：

```powershell
.\setup.ps1
# 如果python不在PATH，指定实际解释器路径：
.\setup.ps1 -Python 'C:\实际安装目录\python.exe'
```

脚本建立或更新`.venv`，安装固定版本依赖，仅在不存在时复制`.env.example`为`.env`。填写密钥、服务地址和服务商当前支持的模型ID，然后运行`start.ps1`。现有`.env`不会被覆盖。PowerShell若阻止脚本，可在学校允许的环境使用下述手动命令，无须修改系统执行策略：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 仅在没有.env时执行复制，避免覆盖已有配置。
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe scripts/check_environment.py
```

`requirements.txt`是本次验证的直接依赖版本；`requirements-lock.txt`记录Windows/Python 3.12完整环境。没有在全新电脑重新联网安装验证，发放前应在一台学生机试装。配置检查不验证远程模型权限或额度。

## 使用顺序

1. 上传PDF：最多5份，每份20MB、100页以内。同名文件先重命名。
2. 在“资料答疑”检查提取文字，输入含知识点关键词的问题，先检索再生成答案。
3. 在“章节总结”选择文件和页码；主要模型输入超过30000字符时缩小范围。
4. 在“练习测验”生成试卷、填写并提交，再批改简答题和保存记录。切换出题选项不会修改已生成试卷；修改答案后必须重新提交和批改。
5. 在“学习记录”查看错题，在“复习计划”根据已保存记录生成计划。

上传资料仅保留在当前会话；关闭会话后需要重新上传。练习记录与复习计划保存在`data/learning.db`。首次启动旧数据库会自动备份到`data/backups/`并添加新列，原记录保留。备份恢复应在停止应用后进行。

模型不可用时，PDF解析、BM25检索和离线测试仍然可用。扫描页OCR可能较慢，代码缩进和公式应对照原PDF人工检查。引用编号校验不等于事实正确性校验。

## 检查与测试

```powershell
.\.venv\Scripts\python.exe scripts/check_environment.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试使用临时数据库和模拟模型返回，不消耗API费用，不改动真实学习记录。集成测试需要应用依赖；依赖不完整时会跳过，并不能算完成集成验收。

## 代码与教学说明

- [优化说明](docs/优化说明.md)：结构、修复、迁移、验证和能力边界。
- [18周教学使用建议](docs/18周教学使用建议.md)：分周任务、分层要求和考核证据。
- `learning_assistant/`：业务模块与界面；`prompts/`：独立提示词；`tests/`：回归测试。

当前使用BM25，没有语义向量检索；AI功能为任务化调用，没有自主工具执行循环。课程中的向量检索实验需要另补教学示例。班级共享部署需要先增加可靠认证、数据隔离、并发与成本控制，不能直接开放此本地版本。
