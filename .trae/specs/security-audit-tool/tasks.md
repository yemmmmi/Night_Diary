# Tasks

- [ ] Task 1: 创建审计引擎核心框架
  - [ ] 创建 `server/app/tools/__init__.py`
  - [ ] 创建 `server/app/tools/security_audit.py`，定义 `Finding` 数据类、`Severity` 枚举、`Auditor` 基类
  - [ ] 实现 `AuditReport` 类和报告生成器（支持 JSON 和 Markdown 输出）
  - [ ] 定义四组审计器注册机制

- [ ] Task 2: 实现认证与访问控制审计器
  - [ ] 扫描 `server/app/api/v1/` 下所有路由文件，提取端点定义（HTTP 方法、路径、依赖项）
  - [ ] 检测 `/server/app/main.py` 中直接注册的端点（如 `/shutdown`）
  - [ ] 分析每个端点：是否有认证中间件、是否执行写操作（POST/PUT/DELETE）
  - [ ] 生成发现：无认证保护的写操作端点、IDOR 风险端点

- [ ] Task 3: 实现注入向量审计器
  - [ ] 扫描 `server/app/` 下所有 `.py` 文件，检测 SQL 字符串拼接模式（f-string 含 `SELECT`/`INSERT`/`UPDATE`/`DELETE`/`ALTER`）
  - [ ] 检测 `subprocess.run`/`os.system`/`os.popen` 调用，分析参数是否包含用户可控输入
  - [ ] 检测 `open()`/`Path()` 文件操作中路径是否由用户输入拼接
  - [ ] 生成发现：SQL 注入、命令注入、路径遍历风险点

- [ ] Task 4: 实现外部交互审计器
  - [ ] 扫描 `httpx`/`requests` 客户端调用，分析 URL 参数来源
  - [ ] 检测 `model_service.py` 中 `validate_model_connection` 的 SSRF 风险（用户可控 base_url 直接用于出站请求）
  - [ ] 检测 API Key 是否在出站请求中明文传输
  - [ ] 生成发现：SSRF、敏感数据外发风险

- [ ] Task 5: 实现敏感数据处理审计器
  - [ ] 扫描 `server/app/` 下所有 `.py` 文件，检测硬编码凭证（API Key、密码、密钥字符串）
  - [ ] 重点检查 `security.py` 中 `_resolve_secret` 的默认密钥硬编码问题
  - [ ] 检测 `logger.info/error/debug` 调用中是否记录用户日记内容或 API Key
  - [ ] 检测弱加密实践（MD5、SHA1、硬编码密钥、可预测密钥派生）
  - [ ] 生成发现：硬编码凭证、日志泄露、弱加密

- [ ] Task 6: 实现 CLI 入口脚本
  - [ ] 创建 `server/scripts/run_security_audit.py`
  - [ ] 支持 `--format json|markdown` 输出格式选项
  - [ ] 支持 `--output <file>` 指定输出文件路径
  - [ ] 支持 `--severity medium|high|critical` 过滤最低严重度
  - [ ] 串联所有审计器执行并生成最终报告

# Task Dependencies
- Task 2-5 依赖于 Task 1（审计引擎核心框架）
- Task 2-5 之间无依赖，可并行开发
- Task 6 依赖于 Task 1-5